from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Callable  # noqa: UP035

import httpx
import pytest
from sqlalchemy import select

from sortipy.adapters.http_resilience import ResilienceConfig, ResilientClient
from sortipy.adapters.lastfm import LastFmFetcher, RecentTracksResponse
from sortipy.common.config import LastFmConfig
from sortipy.domain.data_integration import sync_play_events
from sortipy.domain.model import (
    Artist,
    ArtistRole,
    PlayEvent,
    Provider,
    Recording,
    ReleaseSet,
    User,
)
from tests.helpers.play_events import FakePlayEventSource

if TYPE_CHECKING:
    from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyIngestUnitOfWork


def _make_client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[ResilienceConfig], ResilientClient]:
    async def async_handler(request: httpx.Request) -> httpx.Response:
        return handler(request)

    def factory(resilience: ResilienceConfig) -> ResilientClient:
        client = ResilientClient(resilience)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(async_handler))  # noqa: SLF001  # type: ignore[reportPrivateUsage]
        return client

    return factory


@pytest.mark.integration
@pytest.mark.parametrize("recent_tracks_payload", range(4), indirect=True)
def test_sync_play_events_persists_payload(
    sqlite_unit_of_work: Callable[[], SqlAlchemyIngestUnitOfWork],
    recent_tracks_payload: RecentTracksResponse,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=recent_tracks_payload.model_dump(by_alias=True))

    total_expected = len(_extract_names(recent_tracks_payload))

    fetcher = LastFmFetcher(
        config=LastFmConfig(api_key="demo", user_name="demo-user"),
        client_factory=_make_client_factory(handler),
    )
    result = sync_play_events(
        fetcher=fetcher,
        unit_of_work_factory=sqlite_unit_of_work,
        batch_size=5,
        max_events=total_expected,
    )

    assert result.stored == total_expected
    assert result.fetched >= total_expected
    assert result.now_playing is None

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(PlayEvent)).scalars().all()
        names = [event.track.recording.title for event in persisted if event.track is not None]
        names.sort()
    expected_names = sorted(_extract_names(recent_tracks_payload))
    assert names == expected_names


def _extract_names(payload: RecentTracksResponse) -> list[str]:
    return [track.name for track in payload.recenttracks.track if track.date is not None]


def _make_play_event(
    *,
    track_name: str,
    artist_name: str,
    release_title: str,
    timestamp: datetime,
) -> PlayEvent:
    artist = Artist(name=artist_name)
    release_set = ReleaseSet(title=f"{artist_name} Collection")
    release = release_set.create_release(title=release_title)
    recording = Recording(title=track_name)
    track = release.add_track(recording)

    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)

    user = User(display_name="Test User")
    return user.log_play(
        played_at=timestamp,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )


@pytest.mark.integration
def test_sync_play_events_stores_tracks_with_same_name_different_artists(
    sqlite_unit_of_work: Callable[[], SqlAlchemyIngestUnitOfWork],
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
            contribution.artist.name
            for event in persisted
            for contribution in event.recording.contributions
            if contribution.role == ArtistRole.PRIMARY
        }
        track_names = {event.recording.title for event in persisted}

    assert len(persisted) == 2
    assert artist_names == {"First Artist", "Second Artist"}
    assert track_names == {"Common Title"}
