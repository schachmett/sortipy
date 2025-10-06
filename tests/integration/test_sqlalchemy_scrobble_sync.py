from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, Iterator, Sequence  # noqa: UP035

import httpx
import pytest
from sqlalchemy import create_engine, select

from sortipy.adapters.lastfm import HttpLastFmScrobbleSource, RecentTracksResponse
from sortipy.common.unit_of_work import SqlAlchemyUnitOfWork, startup
from sortipy.domain.data_integration import SyncRequest, SyncScrobbles
from sortipy.domain.types import Album, Artist, Scrobble, Track
from tests.support.scrobbles import FakeScrobbleSource


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


def _make_scrobble(
    *,
    track_name: str,
    artist_name: str,
    album_name: str,
    timestamp: datetime,
) -> Scrobble:
    artist = Artist(name=artist_name)
    album = Album(name=album_name, artist=artist)
    track = Track(name=track_name, artist=artist, album=album)
    artist.tracks.append(track)
    artist.albums.append(album)
    album.add_track(track)
    scrobble = Scrobble(timestamp=timestamp, track=track)
    track.add_scrobble(scrobble)
    return scrobble


def test_sync_scrobbles_stores_tracks_with_same_name_different_artists(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    first = _make_scrobble(
        track_name="Common Title",
        artist_name="First Artist",
        album_name="First Album",
        timestamp=base_time,
    )
    second = _make_scrobble(
        track_name="Common Title",
        artist_name="Second Artist",
        album_name="Second Album",
        timestamp=base_time + timedelta(seconds=30),
    )

    service = SyncScrobbles(
        source=FakeScrobbleSource([[first, second]]),
        unit_of_work=sqlite_unit_of_work,
    )

    result = service.run(SyncRequest(limit=5))

    assert result.stored == 2

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(Scrobble)).scalars().all()
        artist_names = {scrobble.track.artist.name for scrobble in persisted}
        track_names = {scrobble.track.name for scrobble in persisted}

    assert len(persisted) == 2
    assert artist_names == {"First Artist", "Second Artist"}
    assert track_names == {"Common Title"}
