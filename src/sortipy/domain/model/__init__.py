"""Public domain model surface."""

from __future__ import annotations

from sortipy.domain.model.associations import (
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
)
from sortipy.domain.model.audit import EntityMerge
from sortipy.domain.model.base import (
    CanonicalEntity,
    ExternallyIdentifiableEntity,
    HasEntityType,
    IngestedEntity,
    ResolvableEntity,
)
from sortipy.domain.model.enums import *  # noqa: F403
from sortipy.domain.model.external_ids import ExternalID, HasExternalIDs, Namespace, provider_for
from sortipy.domain.model.music import (
    Artist,
    Label,
    Recording,
    Release,
    ReleaseSet,
)
from sortipy.domain.model.primitives import *  # noqa: F403
from sortipy.domain.model.user import (
    LibraryItem,
    PlayEvent,
    User,
)

__all__ = [  # noqa: RUF022
    # base
    "HasEntityType",
    "IngestedEntity",
    "ExternallyIdentifiableEntity",
    "CanonicalEntity",
    "ResolvableEntity",
    # external ids
    "ExternalID",
    "Namespace",
    "HasExternalIDs",
    "provider_for",
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
