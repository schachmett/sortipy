from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, Iterator, Sequence  # noqa: UP035

import httpx
import pytest
from sqlalchemy import create_engine, select

from sortipy.adapters.lastfm import HttpLastFmPlayEventSource, RecentTracksResponse
from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork, startup
from sortipy.domain.data_integration import sync_play_events
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    PlayEvent,
    Provider,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)
from tests.helpers.play_events import FakePlayEventSource


@pytest.fixture
def sqlite_unit_of_work(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[], SqlAlchemyUnitOfWork]]:
    import sortipy.adapters.sqlalchemy.unit_of_work as uow_module

    test_uri = "sqlite+pysqlite:///:memory:"
    engine = create_engine(test_uri, future=True)
    was_started = uow_module.is_started()
    old_engine = uow_module.configured_engine()
    monkeypatch.setenv("DATABASE_URI", test_uri)
    startup(engine=engine, database_uri=test_uri, force=True)

    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork()

    yield factory

    engine.dispose()
    if was_started and old_engine is not None:
        startup(engine=old_engine, force=True)
    else:
        uow_module.shutdown()


def test_sync_play_events_persists_payload(
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
        source = HttpLastFmPlayEventSource(api_key="demo", user_name="demo-user", client=client)
        result = sync_play_events(
            fetcher=source,
            unit_of_work_factory=sqlite_unit_of_work,
            batch_size=5,
            max_events=total_expected,
        )
    finally:
        client.close()

    assert result.stored == total_expected
    assert result.fetched >= total_expected
    assert result.now_playing is None

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(PlayEvent)).scalars().all()
        names = [event.track.recording.title for event in persisted if event.track is not None]
        names.sort()
    expected_names = sorted(name for payload in responses for name in _extract_names(payload))
    assert names == expected_names


def _extract_names(payload: RecentTracksResponse) -> list[str]:
    return [item["name"] for item in payload["recenttracks"]["track"] if "date" in item]


def _make_play_event(
    *,
    track_name: str,
    artist_name: str,
    release_title: str,
    timestamp: datetime,
) -> PlayEvent:
    artist = Artist(name=artist_name)
    release_set = ReleaseSet(title=f"{artist_name} Collection")
    release = Release(title=release_title, release_set=release_set)
    recording = Recording(title=track_name)
    track = Track(release=release, recording=recording)

    release_set.releases.append(release)
    release_set.artists.append(
        ReleaseSetArtist(
            release_set=release_set,
            artist=artist,
            role=ArtistRole.PRIMARY,
        )
    )
    artist.release_sets.append(release_set)

    release.tracks.append(track)
    recording.tracks.append(track)
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )
    artist.recordings.append(recording)

    play_event = PlayEvent(
        played_at=timestamp,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )
    recording.play_events.append(play_event)
    track.play_events.append(play_event)
    return play_event


def test_sync_play_events_stores_tracks_with_same_name_different_artists(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    first = _make_play_event(
        track_name="Common Title",
        artist_name="First Artist",
        release_title="First Release",
        timestamp=base_time,
    )
    second = _make_play_event(
        track_name="Common Title",
        artist_name="Second Artist",
        release_title="Second Release",
        timestamp=base_time + timedelta(seconds=30),
    )

    result = sync_play_events(
        fetcher=FakePlayEventSource([[first, second]]),
        unit_of_work_factory=sqlite_unit_of_work,
        batch_size=5,
    )

    assert result.stored == 2

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(PlayEvent)).scalars().all()
        artist_names = {
            link.artist.name
            for event in persisted
            for link in event.recording.artists
            if link.role == ArtistRole.PRIMARY
        }
        track_names = {event.recording.title for event in persisted}

    assert len(persisted) == 2
    assert artist_names == {"First Artist", "Second Artist"}
    assert track_names == {"Common Title"}
