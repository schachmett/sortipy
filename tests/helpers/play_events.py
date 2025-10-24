"""Reusable fakes and helpers for play-event related tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sortipy.domain.data_integration import (
    FetchPlayEventsResult,
    PlayEventRepository,
    PlayEventSource,
    PlayEventUnitOfWork,
)
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

if TYPE_CHECKING:
    from collections.abc import Iterable


def make_play_event(
    name: str = "Example Track",
    *,
    timestamp: datetime | None = None,
) -> PlayEvent:
    """Create a play event with minimal associated domain entities."""

    artist = Artist(name="Example Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release = Release(title="Example Release", release_set=release_set)
    recording = Recording(title=name)
    track = Track(release=release, recording=recording)

    release_set.releases.append(release)
    release_set.artists.append(
        ReleaseSetArtist(release_set=release_set, artist=artist, role=ArtistRole.PRIMARY)
    )
    if release_set not in artist.release_sets:
        artist.release_sets.append(release_set)

    release.tracks.append(track)
    recording.tracks.append(track)
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )
    if recording not in artist.recordings:
        artist.recordings.append(recording)

    event_time = timestamp or datetime.now(tz=UTC)
    event = PlayEvent(
        played_at=event_time, source=Provider.LASTFM, recording=recording, track=track
    )

    recording.play_events.append(event)
    track.play_events.append(event)
    return event


class FakePlayEventSource(PlayEventSource):
    """In-memory implementation of the play-event source port for testing."""

    def __init__(
        self,
        batches: Iterable[Iterable[PlayEvent]],
        *,
        now_playing: PlayEvent | None = None,
    ) -> None:
        self._batches: list[list[PlayEvent]] = [list(batch) for batch in batches]
        if not self._batches:
            self._batches = [[]]
        self._now_playing = now_playing
        self.calls: list[dict[str, object]] = []

    def fetch_recent(
        self,
        *,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> FetchPlayEventsResult:
        self.calls.append(
            {
                "batch_size": batch_size,
                "since": since,
                "until": until,
                "max_events": max_events,
            }
        )

        collected: list[PlayEvent] = []
        remaining = max_events
        for batch in self._batches:
            for event in batch:
                if since and event.played_at <= since:
                    continue
                if until and event.played_at > until:
                    continue
                collected.append(event)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return FetchPlayEventsResult(
                            events=list(collected),
                            now_playing=self._now_playing,
                        )

        return FetchPlayEventsResult(
            events=list(collected),
            now_playing=self._now_playing,
        )


class FakePlayEventRepository(PlayEventRepository):
    """Simple in-memory repository for play events."""

    def __init__(self, initial: Iterable[PlayEvent] | None = None) -> None:
        self.items: list[PlayEvent] = list(initial or [])

    def add(self, event: PlayEvent) -> None:
        self.items.append(event)

    def exists(self, timestamp: datetime) -> bool:
        return any(item.played_at == timestamp for item in self.items)

    def latest_timestamp(self) -> datetime | None:
        if not self.items:
            return None
        return max(item.played_at for item in self.items)


class FakePlayEventUnitOfWork(PlayEventUnitOfWork):
    """Unit of work capturing play-event persistence interactions."""

    def __init__(self, repository: FakePlayEventRepository) -> None:
        self.play_events: PlayEventRepository = repository
        self.committed = False
        self.rollback_called = False

    def __enter__(self) -> FakePlayEventUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if exc_type is not None:
            self.rollback()
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rollback_called = True


__all__ = [
    "FakePlayEventRepository",
    "FakePlayEventSource",
    "FakePlayEventUnitOfWork",
    "make_play_event",
]
