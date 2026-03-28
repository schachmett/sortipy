from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select

from sortipy.adapters.http_resilience import ResilientClient
from sortipy.adapters.lastfm import fetch_play_events
from sortipy.adapters.lastfm.client import LastFmClient
from sortipy.adapters.lastfm.translator import parse_play_event
from sortipy.application import PlayEventIngestRequest, ingest_play_events
from sortipy.config.lastfm import (
    LASTFM_BASE_URL,
    LASTFM_TIMEOUT_SECONDS,
    CacheConfig,
    LastFmConfig,
    RateLimit,
    ResilienceConfig,
)
from sortipy.domain.model import (
    Artist,
    ArtistRole,
    PlayEvent,
    Provider,
    Recording,
    Release,
    ReleaseSet,
    User,
)
from tests.helpers.play_events import FakePlayEventSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.adapters.lastfm.client import RecentTracksResponse
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
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(async_handler))
        return client

    return factory


@pytest.mark.integration
@pytest.mark.parametrize("recent_tracks_payload", range(4), indirect=True)
def test_reconcile_play_events_persists_payload(
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

    result = ingest_play_events(
        request=PlayEventIngestRequest(batch_size=5, max_events=total_expected),
        fetcher=fetcher,
        user=user,
        unit_of_work_factory=sqlite_unit_of_work,
        source=Provider.LASTFM,
    )

    assert result.stored_events == total_expected
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


def _make_lastfm_payload(
    *,
    track_name: str,
    artist_name: str,
    artist_url: str,
    album_title: str,
    album_mbid: str,
    track_url: str,
    timestamp: datetime,
) -> dict[str, object]:
    return {
        "artist": {
            "#text": artist_name,
            "url": artist_url,
            "mbid": None,
        },
        "streamable": "0",
        "image": [],
        "mbid": None,
        "album": {
            "#text": album_title,
            "mbid": album_mbid,
        },
        "name": track_name,
        "url": track_url,
        "date": {
            "uts": str(int(timestamp.timestamp())),
            "#text": timestamp.strftime("%d %b %Y, %H:%M"),
        },
    }


@pytest.mark.integration
def test_reconcile_play_events_stores_tracks_with_same_name_different_artists(
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

    result = ingest_play_events(
        request=PlayEventIngestRequest(batch_size=5),
        fetcher=FakePlayEventSource([[first, second]]),
        user=user,
        unit_of_work_factory=sqlite_unit_of_work,
        source=Provider.LASTFM,
    )

    assert result.stored_events == 2

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


@pytest.mark.integration
def test_reconcile_play_events_does_not_split_release_set_on_track_artist_mismatch(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    user = User(display_name="Last.fm")
    with sqlite_unit_of_work() as uow:
        uow.repositories.users.add(user)
        uow.commit()

    base_time = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
    bowie_track = parse_play_event(
        _make_lastfm_payload(
            track_name="Sound and Vision - 2017 Remaster",
            artist_name="David Bowie",
            artist_url="https://www.last.fm/music/David+Bowie",
            album_title="Best of Bowie",
            album_mbid="0603828a-4dfe-4608-8193-4e3a94b8baf0",
            track_url="https://www.last.fm/music/David+Bowie/_/Sound+and+Vision+-+2017+Remaster",
            timestamp=base_time,
        ),
        user=user,
    )
    under_pressure = parse_play_event(
        _make_lastfm_payload(
            track_name="Under Pressure - Remastered 2011",
            artist_name="Queen",
            artist_url="https://www.last.fm/music/Queen",
            album_title="Best of Bowie",
            album_mbid="0603828a-4dfe-4608-8193-4e3a94b8baf0",
            track_url="https://www.last.fm/music/Queen/_/Under+Pressure+-+Remastered+2011",
            timestamp=base_time + timedelta(minutes=1),
        ),
        user=user,
    )

    result = ingest_play_events(
        request=PlayEventIngestRequest(batch_size=5, max_events=2),
        fetcher=FakePlayEventSource([[bowie_track, under_pressure]]),
        user=user,
        unit_of_work_factory=sqlite_unit_of_work,
        source=Provider.LASTFM,
    )

    assert result.stored_events == 2

    with sqlite_unit_of_work() as uow:
        release_sets = uow.session.execute(select(ReleaseSet)).scalars().all()
        releases = uow.session.execute(select(Release)).scalars().all()
        recordings = uow.session.execute(select(Recording)).scalars().all()
        assert len(release_sets) == 1
        assert len(releases) == 1

        release_set = release_sets[0]
        release = releases[0]
        assert release_set.title == "Best of Bowie"
        assert release.release_set is release_set
        assert release_set.contributions == ()
        assert len(release.tracks) == 2

        artists_by_recording = {
            recording.title: {contribution.artist.name for contribution in recording.contributions}
            for recording in recordings
        }
        assert artists_by_recording["Sound and Vision - 2017 Remaster"] == {"David Bowie"}
        assert artists_by_recording["Under Pressure - Remastered 2011"] == {"Queen"}
