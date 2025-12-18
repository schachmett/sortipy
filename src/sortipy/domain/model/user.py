"""User-facing entities (not canonical/resolvable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from sortipy.domain.model.base import Entity, IngestedEntity
from sortipy.domain.model.enums import EntityType, Provider

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sortipy.domain.model.associations import ReleaseTrack
    from sortipy.domain.model.base import CanonicalEntity
    from sortipy.domain.model.music import Recording, Release


@dataclass(eq=False, kw_only=True)
class User(Entity, IngestedEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.USER

    display_name: str
    email: str | None = None

    # Optional denormalized external handles
    spotify_user_id: str | None = None
    lastfm_user: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    _library_items: list[LibraryItem] = field(default_factory=list["LibraryItem"], repr=False)

    @property
    def library_items(self) -> tuple[LibraryItem, ...]:
        return tuple(self._library_items)

    def _attach_library_item(self, item: LibraryItem) -> None:
        self._library_items.append(item)

    def _detach_library_item(self, item: LibraryItem) -> None:
        self._library_items.remove(item)


@dataclass(eq=False, kw_only=True)
class LibraryItem(Entity, IngestedEntity):
    """User saved items (artists, releases, recordings, etc.).

    Storage uses (entity_type, entity_id) as polymorphic reference.
    Optional in-memory `entity` can be hydrated for navigation.
    """

    ENTITY_TYPE: ClassVar[EntityType] = EntityType.LIBRARY_ITEM

    user: User = field(repr=False)

    target_type: EntityType
    target_id: UUID
    target: CanonicalEntity | None = None  # optional in-memory convenience

    source: Provider | None = None
    saved_at: datetime | None = None

    def __post_init__(self) -> None:
        # Keep user graph consistent without ORM.
        self.user._attach_library_item(self)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001


@dataclass(eq=False, kw_only=True)
class PlayEvent(Entity, IngestedEntity):
    """A listener consuming something at a point in time.

    XOR:
      - either track is set (=> recording derived from track.recording)
      - or recording_ref is set directly (fallback if release unknown)
    """

    ENTITY_TYPE: ClassVar[EntityType] = EntityType.PLAY_EVENT

    played_at: datetime
    source: Provider

    user: User = field(repr=False)

    # XOR fields:
    track: ReleaseTrack | None = field(default=None, repr=False)
    recording_ref: Recording | None = field(default=None, repr=False)

    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if (self.track is None) == (self.recording_ref is None):
            raise ValueError("PlayEvent requires exactly one of track or recording_ref")
        # Maintain recording backref
        self.recording._attach_play_event(self)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    @property
    def recording(self) -> Recording:
        if self.track is not None:
            return self.track.recording
        if self.recording_ref is not None:
            return self.recording_ref
        raise ValueError("PlayEvent requires exactly one of track or recording_ref")

    @property
    def release(self) -> Release | None:
        return self.track.release if self.track is not None else None

    def detach(self) -> None:
        """Explicit cleanup hook if you remove the event from the domain graph."""
        self.recording._detach_play_event(self)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
