"""Public domain model surface."""

from __future__ import annotations

from sortipy.domain.model.associations import (
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
)
from sortipy.domain.model.audit import (
    EntityMerge,
)
from sortipy.domain.model.entity import (
    Entity,
    EntityRef,
)
from sortipy.domain.model.enums import *  # noqa: F403
from sortipy.domain.model.external_ids import (
    ExternalID,
    ExternalIdCollection,
    ExternallyIdentifiable,
    Namespace,
    provider_for,
)
from sortipy.domain.model.music import (
    Artist,
    Label,
    Recording,
    Release,
    ReleaseSet,
)
from sortipy.domain.model.primitives import *  # noqa: F403
from sortipy.domain.model.provenance import (
    Provenance,
    Provenanced,
    ProvenanceTracked,
)
from sortipy.domain.model.user import (
    LibraryItem,
    PlayEvent,
    User,
)

__all__ = [  # noqa: RUF022
    # base
    "Entity",
    "EntityRef",
    # external ids
    "ExternalID",
    "Namespace",
    "ExternalIdCollection",
    "provider_for",
    "ExternallyIdentifiable",
    # provenance
    "Provenance",
    "Provenanced",
    "ProvenanceTracked",
    # associations
    "ReleaseSetContribution",
    "RecordingContribution",
    "ReleaseTrack",
    # music
    "Artist",
    "ReleaseSet",
    "Release",
    "Recording",
    "Label",
    # user
    "User",
    "LibraryItem",
    "PlayEvent",
    # audit
    "EntityMerge",
]
