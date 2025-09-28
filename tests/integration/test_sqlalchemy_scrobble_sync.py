from __future__ import annotations

from typing import Callable, Iterator, Sequence  # noqa: UP035

import httpx
import pytest
from sqlalchemy import create_engine, select

from sortipy.adapters.lastfm import HttpLastFmScrobbleSource, RecentTracksResponse
from sortipy.common.unit_of_work import SqlAlchemyUnitOfWork, startup
from sortipy.domain.data_integration import SyncRequest, SyncScrobbles
from sortipy.domain.types import Scrobble


@pytest.fixture
def sqlite_unit_of_work(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[], SqlAlchemyUnitOfWork]]:
    import sortipy.common.unit_of_work as uow_module

    test_uri = "sqlite+pysqlite:///:memory:"
    engine = create_engine(test_uri, future=True)
    old_engine = uow_module.ENGINE
    monkeypatch.setenv("DATABASE_URI", test_uri)
    uow_module.ENGINE = engine
    startup()

    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork()

    yield factory

    engine.dispose()
    uow_module.ENGINE = old_engine


def test_sync_scrobbles_persists_payload(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
    recent_tracks_payloads: Sequence[RecentTracksResponse],
) -> None:
    responses = list(recent_tracks_payloads[:2])

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        index = min(max(page - 1, 0), len(responses) - 1)
        payload = responses[index]
        return httpx.Response(status_code=200, json=payload)

    total_expected = sum(len(_extract_names(payload)) for payload in responses)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(api_key="demo", user_name="demo-user", client=client)
        service = SyncScrobbles(source=source, unit_of_work=sqlite_unit_of_work)
        result = service.run(SyncRequest(limit=5, max_pages=2))
    finally:
        client.close()

    assert result.stored == total_expected
    assert result.pages_processed == 2
    assert result.now_playing is None

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(Scrobble)).scalars().all()
        names = sorted(scrobble.track.name for scrobble in persisted)
    expected_names = sorted(
        name for payload in responses for name in _extract_names(payload)
    )
    assert names == expected_names


def _extract_names(payload: RecentTracksResponse) -> list[str]:
    return [item["name"] for item in payload["recenttracks"]["track"] if "date" in item]
