"""External identifiers owned by typed references.

Important: ExternalID points to (owner_type, owner_id), not to a concrete FK.
Domain attaches ExternalIDs to the *resolved id* of canonical entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

from sortipy.domain.model.base import Entity
from sortipy.domain.model.enums import EntityType, ExternalNamespace, Provider

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


type Namespace = str | ExternalNamespace


_NAMESPACE_PROVIDERS: Final[dict[Namespace, Provider]] = {
    ExternalNamespace.MUSICBRAINZ_ARTIST: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_RELEASE: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_RECORDING: Provider.MUSICBRAINZ,
    ExternalNamespace.MUSICBRAINZ_LABEL: Provider.MUSICBRAINZ,
    ExternalNamespace.SPOTIFY_ARTIST: Provider.SPOTIFY,
    ExternalNamespace.LASTFM_ARTIST: Provider.LASTFM,
    ExternalNamespace.LASTFM_RECORDING: Provider.LASTFM,
    ExternalNamespace.USER_SPOTIFY: Provider.SPOTIFY,
    ExternalNamespace.USER_LASTFM: Provider.LASTFM,
    ExternalNamespace.RECORDING_ISRC: Provider.MUSICBRAINZ,
    ExternalNamespace.LABEL_CATALOG_NUMBER: Provider.MUSICBRAINZ,
    ExternalNamespace.LABEL_BARCODE: Provider.MUSICBRAINZ,
}


def provider_for(namespace: Namespace) -> Provider | None:
    return _NAMESPACE_PROVIDERS.get(namespace)


@dataclass(eq=False, kw_only=True)
class ExternalID:
    namespace: Namespace
    value: str

    owner_type: EntityType
    owner_id: UUID

    provider: Provider | None = None
    created_at: datetime | None = None


@dataclass(eq=False, kw_only=True)
class ExternallyIdentifiableEntity(Entity):
    """Mixin-like protocol by convention.

    Keep it simple: concrete classes carry `external_ids: list[ExternalID]` and
    call these helpers.
    """

    external_ids: list[ExternalID] = field(default_factory=list["ExternalID"], repr=False)

    def add_external_id(
        self,
        namespace: Namespace,
        value: str,
        *,
        provider: Provider | None = None,
        replace: bool = False,
    ) -> None:
        resolved_provider = provider if provider is not None else provider_for(namespace)
        ext = ExternalID(
            namespace=namespace,
            value=value,
            owner_type=self.entity_type,
            owner_id=self.resolved_id,
            provider=resolved_provider,
        )
        if replace:
            self.external_ids[:] = [e for e in self.external_ids if e.namespace != namespace]
        self.external_ids.append(ext)

    @property
    def external_ids_by_namespace(self) -> dict[Namespace, ExternalID]:
        mapping: dict[Namespace, ExternalID] = {}
        for e in self.external_ids:
            mapping[e.namespace] = e
        return mapping


class HasExternalIDs(Protocol):
    external_ids: list[ExternalID]

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
