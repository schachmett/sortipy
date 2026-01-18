"""Reusable fakes and helpers for play-event related tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    EntityType,
    IdentifiedEntity,
    Namespace,
    PlayEvent,
    Provider,
    Recording,
    Release,
    ReleaseSet,
    User,
)
from sortipy.domain.ports.fetching import PlayEventFetcher, PlayEventFetchResult

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.domain.ingest_pipeline.context import NormalizationData


def make_play_event(
    name: str = "Example Track",
    *,
    timestamp: datetime | None = None,
) -> PlayEvent:
    """Create a play event with minimal associated domain entities."""

    artist = Artist(name="Example Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release = release_set.create_release(title="Example Release")
    recording = Recording(title=name)
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)
    track = release.add_track(recording)

    event_time = timestamp or datetime.now(tz=UTC)
    user = User(display_name="Example User")
    return user.log_play(
        played_at=event_time,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )


class FakePlayEventSource(PlayEventFetcher):
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

    def __call__(
        self,
        *,
        user: User,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        self.calls.append(
            {
                "user": user,
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
                        return PlayEventFetchResult(
                            events=list(collected),
                            now_playing=self._now_playing,
                        )
        return PlayEventFetchResult(events=list(collected), now_playing=self._now_playing)


class FakePlayEventRepository:
    """Simple in-memory repository for play events."""

    def __init__(self, initial: Iterable[PlayEvent] | None = None) -> None:
        self.items: list[PlayEvent] = list(initial or [])

    def add(self, entity: PlayEvent) -> None:
        self.items.append(entity)

    def exists(self, event: PlayEvent) -> bool:
        return any(
            item.user.id == event.user.id
            and item.source == event.source
            and item.played_at == event.played_at
            for item in self.items
        )

    def latest_timestamp(self) -> datetime | None:
        if not self.items:
            return None
        return max(item.played_at for item in self.items)


if TYPE_CHECKING:
    from sortipy.domain.ports.persistence import PlayEventRepository

    _check_repo: PlayEventRepository = FakePlayEventRepository()


class _NullCanonicalRepository[TCanonical]:
    def add(self, entity: TCanonical) -> None:
        _ = entity

    def get_by_external_id(self, namespace: Namespace, value: str) -> TCanonical | None:
        _ = (namespace, value)
        return None


class _NullSidecarRepository:
    def save(
        self,
        entity: IdentifiedEntity,
        data: NormalizationData[IdentifiedEntity],
    ) -> None:  # pragma: no cover - trivial
        _ = (entity, data)

    def find_by_keys(
        self,
        entity_type: EntityType,
        keys: tuple[tuple[object, ...], ...],
    ) -> dict[tuple[object, ...], IdentifiedEntity]:
        _ = (entity_type, keys)
        return {}


@dataclass(slots=True)
class _FakePlayEventRepositories:
    play_events: FakePlayEventRepository
    artists: _NullCanonicalRepository[Artist]
    release_sets: _NullCanonicalRepository[ReleaseSet]
    releases: _NullCanonicalRepository[Release]
    recordings: _NullCanonicalRepository[Recording]
    normalization_sidecars: _NullSidecarRepository


class FakeIngestUnitOfWork:
    """Unit of work capturing play-event persistence interactions."""

    def __init__(self, repository: FakePlayEventRepository) -> None:
        self.repositories = _FakePlayEventRepositories(
            play_events=repository,
            artists=_NullCanonicalRepository[Artist](),
            release_sets=_NullCanonicalRepository[ReleaseSet](),
            releases=_NullCanonicalRepository[Release](),
            recordings=_NullCanonicalRepository[Recording](),
            normalization_sidecars=_NullSidecarRepository(),
        )
        self.committed = False
        self.rollback_called = False

    def __enter__(self) -> FakeIngestUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> Literal[False]:
        if exc_type is not None:
            self.rollback()
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rollback_called = True


if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.ingest_ports import PlayEventSyncUnitOfWork

    _uow_check: PlayEventSyncUnitOfWork = FakeIngestUnitOfWork(_check_repo)
