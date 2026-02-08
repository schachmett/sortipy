"""External identifiers owned by typed references.

Important: ExternalID points to (owner_type, owner_id), not to a concrete FK.
Domain attaches ExternalIDs to the *resolved id* of canonical entities.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

from .entity import Entity
from .enums import ExternalNamespace, Provider

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from .enums import EntityType


type Namespace = str | ExternalNamespace


_NAMESPACE_PROVIDERS: Final[dict[Namespace, Provider]] = {
    ExternalNamespace.MUSICBRAINZ_ARTIST: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_RELEASE: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_RECORDING: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_LABEL: Provider.MUSICBRAINZ,
    ExternalNamespace.SPOTIFY_ARTIST: Provider.SPOTIFY,
    ExternalNamespace.SPOTIFY_ALBUM: Provider.SPOTIFY,
    ExternalNamespace.SPOTIFY_TRACK: Provider.SPOTIFY,
    ExternalNamespace.LASTFM_ARTIST: Provider.LASTFM,
    ExternalNamespace.LASTFM_RECORDING: Provider.LASTFM,
    ExternalNamespace.USER_SPOTIFY: Provider.SPOTIFY,
    ExternalNamespace.USER_LASTFM: Provider.LASTFM,
    ExternalNamespace.RECORDING_ISRC: Provider.MUSICBRAINZ,
    ExternalNamespace.RELEASE_EAN: Provider.SPOTIFY,
    ExternalNamespace.RELEASE_UPC: Provider.SPOTIFY,
    ExternalNamespace.LABEL_CATALOG_NUMBER: Provider.MUSICBRAINZ,
    ExternalNamespace.LABEL_BARCODE: Provider.MUSICBRAINZ,
}


def provider_for(namespace: Namespace) -> Provider | None:
    return _NAMESPACE_PROVIDERS.get(namespace)


@dataclass(eq=False, kw_only=True)
class ExternalID:
    namespace: Namespace
    value: str

    _owner_type: EntityType
    _owner_id: UUID

    provider: Provider | None = None
    created_at: datetime | None = None

    @property
    def owner_type(self) -> EntityType:
        return self._owner_type

    @property
    def owner_id(self) -> UUID:
        return self._owner_id


class ExternalIdCollection(Protocol):
    """Read-only access to owned external IDs."""

    @property
    def external_ids(self) -> tuple[ExternalID, ...]: ...


class ExternallyIdentifiable(ExternalIdCollection, Protocol):
    """An entity that owns external IDs."""

    def add_external_id(
        self,
        namespace: Namespace,
        value: str,
        *,
        provider: Provider | None = None,
        replace: bool = False,
    ) -> None: ...

    @property
    def external_ids_by_namespace(self) -> dict[Namespace, ExternalID]: ...


@dataclass(eq=False, kw_only=True)
class ExternallyIdentifiableMixin(Entity, ABC):
    """Capability: owns ExternalIDs.

    Requires the concrete class to provide `entity_type` and `resolved_id`
    (usually via inheriting from `Entity` / `ResolvableEntity`).
    """

    _external_ids: list[ExternalID] = field(
        default_factory=list["ExternalID"], repr=False, init=False
    )

    @property
    def external_ids(self) -> tuple[ExternalID, ...]:
        return tuple(self._external_ids)

    def add_external_id(
        self,
        namespace: Namespace,
        value: str,
        *,
        provider: Provider | None = None,
        replace: bool = False,
    ) -> None:
        # TODO owner = cast(EntityRef, self)
        resolved_provider = provider if provider is not None else provider_for(namespace)
        ext = ExternalID(
            namespace=namespace,
            value=value,
            _owner_type=self.entity_type,
            _owner_id=self.resolved_id,
            provider=resolved_provider,
        )
        if replace:
            self._external_ids[:] = [e for e in self._external_ids if e.namespace != namespace]
        if any(e for e in self._external_ids if e.namespace == namespace):
            raise ValueError(f"External ID {namespace} already exists on {self}")
        self._external_ids.append(ext)

    @property
    def external_ids_by_namespace(self) -> dict[Namespace, ExternalID]:
        mapping: dict[Namespace, ExternalID] = {}
        for e in self._external_ids:
            mapping[e.namespace] = e
        return mapping
