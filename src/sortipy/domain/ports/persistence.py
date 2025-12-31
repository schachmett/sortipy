"""Ports for persisting domain aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.model import (
    Artist,
    ExternallyIdentifiable,
    Label,
    Namespace,
    PlayEvent,
    Provider,
    Recording,
    Release,
    ReleaseSet,
    User,
)

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


@runtime_checkable
class Repository[TEntity](Protocol):
    """Minimal repository contract for a persistent aggregate store."""

    def add(self, entity: TEntity) -> None: ...


@runtime_checkable
class PlayEventRepository(Repository[PlayEvent], Protocol):
    """Persistence contract for play events."""

    def exists(self, *, user_id: UUID, source: Provider, played_at: datetime) -> bool: ...

    def latest_timestamp(self) -> datetime | None: ...


@runtime_checkable
class CanonicalEntityRepository[TCanonical: ExternallyIdentifiable](
    Repository[TCanonical], Protocol
):
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
class LabelRepository(CanonicalEntityRepository[Label], Protocol):
    """Repository contract for labels."""


@runtime_checkable
class UserRepository(Repository[User], Protocol):
    """Repository contract for users."""
