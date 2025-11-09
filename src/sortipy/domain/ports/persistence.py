"""Ports for persisting domain aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.types import (
    Artist,
    CanonicalEntity,
    Label,
    Namespace,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    Track,
)

if TYPE_CHECKING:
    from datetime import datetime


@runtime_checkable
class Repository[TEntity](Protocol):
    """Minimal repository contract for a persistent aggregate store."""

    def add(self, entity: TEntity) -> None: ...


@runtime_checkable
class PlayEventRepository(Repository[PlayEvent], Protocol):
    """Persistence contract for play events."""

    def exists(self, timestamp: datetime) -> bool: ...

    def latest_timestamp(self) -> datetime | None: ...


@runtime_checkable
class CanonicalEntityRepository[TCanonical: CanonicalEntity](Repository[TCanonical], Protocol):
    """Repository contract for canonical catalog aggregates."""

    def get_by_external_id(self, namespace: Namespace, value: str) -> TCanonical | None: ...


@runtime_checkable
class ArtistRepository(CanonicalEntityRepository[Artist], Protocol):
    """Repository contract for artists."""


@runtime_checkable
class ReleaseSetRepository(CanonicalEntityRepository[ReleaseSet], Protocol):
    """Repository contract for release sets."""


@runtime_checkable
class ReleaseRepository(CanonicalEntityRepository[Release], Protocol):
    """Repository contract for releases."""


@runtime_checkable
class RecordingRepository(CanonicalEntityRepository[Recording], Protocol):
    """Repository contract for recordings."""


@runtime_checkable
class TrackRepository(CanonicalEntityRepository[Track], Protocol):
    """Repository contract for tracks."""


@runtime_checkable
class LabelRepository(CanonicalEntityRepository[Label], Protocol):
    """Repository contract for labels."""
