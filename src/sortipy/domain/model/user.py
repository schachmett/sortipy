"""User-facing entities (not canonical/resolvable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from . import _internal as internal
from .enums import EntityType, Provider
from .provenance import ProvenanceTrackedMixin

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from .associations import ReleaseTrack
    from .entity import IdentifiedEntity
    from .music import Recording, Release


@dataclass(eq=False, kw_only=True)
class User(ProvenanceTrackedMixin):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.USER

    display_name: str
    email: str | None = None

    # Optional denormalized external handles
    spotify_user_id: str | None = None
    lastfm_user: str | None = None

    _library_items: list[LibraryItem] = field(default_factory=list["LibraryItem"], repr=False)
    _play_events: list[PlayEvent] = field(default_factory=list["PlayEvent"], repr=False)

    @property
    def library_items(self) -> tuple[LibraryItem, ...]:
        return tuple(self._library_items)

    @property
    def play_events(self) -> tuple[PlayEvent, ...]:
        return tuple(self._play_events)

    def save_entity(
        self,
        entity: IdentifiedEntity,
        *,
        source: Provider | None = None,
        saved_at: datetime | None = None,
    ) -> LibraryItem:
        return self.save_reference(
            target_type=entity.entity_type,
            target_id=entity.resolved_id,
            target=entity,
            source=source,
            saved_at=saved_at,
        )

    def save_reference(
        self,
        *,
        target_type: EntityType,
        target_id: UUID,
        target: IdentifiedEntity | None = None,
        source: Provider | None = None,
        saved_at: datetime | None = None,
    ) -> LibraryItem:
        item = LibraryItem(
            _user=self,
            _target_type=target_type,
            _target_id=target_id,
            _target=target,
            source=source,
            saved_at=saved_at,
        )
        self._library_items.append(item)
        return item

    def remove_library_item(self, item: LibraryItem) -> None:
        if item.user is not self:
            raise ValueError("library item not owned by this user")
        self._library_items.remove(item)

    def rehydrate_library_item(self, item: LibraryItem) -> None:
        """Attach a library item to this user instance.

        Used by persistence adapters to re-bind detached items when crossing
        session boundaries. This keeps the domain invariant intact: a library
        item must always belong to its owning user.
        """
        if item.user is not self:
            if item.user.id != self.id:
                raise ValueError("library item belongs to a different user")
            internal.set_library_item_user(item, self)
        if item not in self._library_items:
            self._library_items.append(item)

    def log_play(
        self,
        *,
        played_at: datetime,
        source: Provider,
        recording: Recording,
        track: ReleaseTrack | None = None,
        duration_ms: int | None = None,
    ) -> PlayEvent:
        if track is not None and track.recording is not recording:
            raise ValueError("track.recording must match recording")
        event = PlayEvent(
            played_at=played_at,
            source=source,
            _user=self,
            _track=track,
            _recording_ref=None if track is not None else recording,
            duration_ms=duration_ms,
        )
        self._play_events.append(event)
        return event

    def remove_play_event(self, event: PlayEvent) -> None:
        if event.user is not self:
            raise ValueError("play event not owned by this user")
        self._play_events.remove(event)

    def rehydrate_play_event(self, event: PlayEvent) -> None:
        """Attach a play event to this user instance.

        Used by persistence adapters to re-bind detached events when crossing
        session boundaries. This keeps the domain invariant intact: a play
        event must always belong to its owning user.
        """
        if event.user is not self:
            if event.user.id != self.id:
                raise ValueError("play event belongs to a different user")
            internal.set_play_event_user(event, self)
        if event not in self._play_events:
            self._play_events.append(event)

    def link_play_to_track(self, event: PlayEvent, track: ReleaseTrack) -> None:
        if event.user is not self:
            raise ValueError("play event not owned by this user")
        if event.track is track:
            return
        if event.track is not None:
            raise ValueError("play event already linked to a track")
        if event.recording_ref is None:
            raise ValueError("play event has no recording_ref to replace")
        if track.recording is not event.recording_ref:
            raise ValueError("track.recording must match play event recording")
        internal.set_play_event_track(event, track)
        internal.set_play_event_recording_ref(event, None)

    def move_play_event_to(self, event: PlayEvent, recording: Recording) -> None:
        if event.user is not self:
            raise ValueError("play event not owned by this user")
        if event.track is not None:
            raise ValueError("play event is already linked to a track")
        if event.recording_ref is recording:
            return
        internal.set_play_event_recording_ref(event, recording)


@dataclass(eq=False, kw_only=True)
class LibraryItem(ProvenanceTrackedMixin):
    """User saved items (artists, releases, recordings, etc.).

    Storage uses (entity_type, entity_id) as polymorphic reference.
    Optional in-memory `entity` can be hydrated for navigation.
    """

    ENTITY_TYPE: ClassVar[EntityType] = EntityType.LIBRARY_ITEM

    _user: User = field(repr=False)

    _target_type: EntityType
    _target_id: UUID
    _target: IdentifiedEntity | None = None  # optional in-memory convenience

    source: Provider | None = None
    saved_at: datetime | None = None

    @property
    def user(self) -> User:
        return self._user

    @property
    def target_type(self) -> EntityType:
        return self._target_type

    @property
    def target_id(self) -> UUID:
        return self._target_id

    @property
    def target(self) -> IdentifiedEntity | None:
        return self._target

    def require_target(self) -> IdentifiedEntity:
        if self._target is None:
            raise ValueError("library item target is not hydrated")
        return self._target

    def __post_init__(self) -> None:
        # Validate target shape; ownership is managed by User commands.
        if self._target is not None and self._target.resolved_id != self._target_id:
            raise ValueError("target_id must match target.resolved_id")


@dataclass(eq=False, kw_only=True)
class PlayEvent(ProvenanceTrackedMixin):
    """A listener consuming something at a point in time.

    XOR:
      - either track is set (=> recording derived from track.recording)
      - or recording_ref is set directly (fallback if release unknown)
    """

    ENTITY_TYPE: ClassVar[EntityType] = EntityType.PLAY_EVENT

    played_at: datetime
    source: Provider

    _user: User = field(repr=False)

    # XOR fields:
    _track: ReleaseTrack | None = field(default=None, repr=False)
    _recording_ref: Recording | None = field(default=None, repr=False)

    duration_ms: int | None = None

    @property
    def user(self) -> User:
        return self._user

    @property
    def track(self) -> ReleaseTrack | None:
        return self._track

    @property
    def recording_ref(self) -> Recording | None:
        return self._recording_ref

    def __post_init__(self) -> None:
        if (self._track is None) == (self._recording_ref is None):
            raise ValueError("PlayEvent requires exactly one of track or recording_ref")

    @property
    def recording(self) -> Recording:
        if self._track is not None:
            return self._track.recording
        if self._recording_ref is not None:
            return self._recording_ref
        raise ValueError("PlayEvent requires exactly one of track or recording_ref")

    @property
    def release(self) -> Release | None:
        return self._track.release if self._track is not None else None
