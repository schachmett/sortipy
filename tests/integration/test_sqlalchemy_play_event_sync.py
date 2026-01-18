from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select

from sortipy.adapters.http_resilience import ResilientClient
from sortipy.adapters.lastfm import LastFmClient, RecentTracksResponse, fetch_play_events
from sortipy.config import CacheConfig, LastFmConfig, RateLimit, ResilienceConfig
from sortipy.config.lastfm import LASTFM_BASE_URL, LASTFM_TIMEOUT_SECONDS
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
    from collections.abc import Callable

    from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
    from sortipy.domain.ports.fetching import PlayEventFetchResult


def _make_lastfm_config() -> LastFmConfig:
    resilience = ResilienceConfig(
        name="lastfm",
        base_url=LASTFM_BASE_URL,
        timeout_seconds=LASTFM_TIMEOUT_SECONDS,
        ratelimit=RateLimit(max_calls=4, per_seconds=1.0),
        cache=CacheConfig(backend="memory"),
    )
    return LastFmConfig(api_key="demo", user_name="demo-user", resilience=resilience)


def _make_client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[ResilienceConfig], ResilientClient]:
    async def async_handler(request: httpx.Request) -> httpx.Response:
        return handler(request)

    def factory(resilience: ResilienceConfig) -> ResilientClient:
        client = ResilientClient(resilience)
        client._client = httpx.AsyncClient(  # noqa: SLF001  # type: ignore[reportPrivateUsage]
            transport=httpx.MockTransport(async_handler),
        )
        return client

    return factory


@pytest.mark.integration
@pytest.mark.parametrize("recent_tracks_payload", range(4), indirect=True)
def test_sync_play_events_persists_payload(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
    recent_tracks_payload: RecentTracksResponse,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json=recent_tracks_payload.model_dump(by_alias=True),
        )

    total_expected = len(_extract_names(recent_tracks_payload))

    user = User(display_name="Last.fm")
    with sqlite_unit_of_work() as uow:
        uow.repositories.users.add(user)
        uow.commit()

    config = _make_lastfm_config()
    client = LastFmClient(config=config, client_factory=_make_client_factory(handler))

    def fetcher(
        *,
        user: User,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        return fetch_play_events(
            config=config,
            client=client,
            user=user,
            batch_size=batch_size,
            since=since,
            until=until,
            max_events=max_events,
        )

    result = sync_play_events(
        fetcher=fetcher,
        user=user,
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
    user: User | None = None,
) -> PlayEvent:
    artist = Artist(name=artist_name)
    release_set = ReleaseSet(title=f"{artist_name} Collection")
    release = release_set.create_release(title=release_title)
    recording = Recording(title=track_name)
    track = release.add_track(recording)

    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)

    owner = user or User(display_name="Test User")
    return owner.log_play(
        played_at=timestamp,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )


@pytest.mark.integration
def test_sync_play_events_stores_tracks_with_same_name_different_artists(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    user = User(display_name="Test User")
    with sqlite_unit_of_work() as uow:
        uow.repositories.users.add(user)
        uow.commit()

    first = _make_play_event(
        track_name="Common Title",
        artist_name="First Artist",
        release_title="First Release",
        timestamp=base_time,
        user=user,
    )
    second = _make_play_event(
        track_name="Common Title",
        artist_name="Second Artist",
        release_title="Second Release",
        timestamp=base_time + timedelta(seconds=30),
        user=user,
    )

    result = sync_play_events(
        fetcher=FakePlayEventSource([[first, second]]),
        user=user,
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
