"""Domain services for enrichment workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.entity_updates import (
    apply_release_update,
    resolve_release_candidate,
)
from sortipy.domain.model import Artist, Recording, Release, ReleaseSet

if TYPE_CHECKING:
    from sortipy.domain.entity_updates import (
        ReleaseSelectionPolicy,
    )
    from sortipy.domain.ports.enrichment import (
        ReleaseCandidatesFromArtist,
        ReleaseCandidatesFromRecording,
        ReleaseCandidatesFromReleaseSet,
        ReleaseUpdateFetcher,
    )


def enrich_release_for_entity(
    entity: Recording | ReleaseSet | Artist | Release,
    *,
    fetch_release_update: ReleaseUpdateFetcher,
    fetch_candidates_from_recording: ReleaseCandidatesFromRecording,
    fetch_candidates_from_release_set: ReleaseCandidatesFromReleaseSet,
    fetch_candidates_from_artist: ReleaseCandidatesFromArtist,
    policy: ReleaseSelectionPolicy | None = None,
) -> Release | None:
    """Fetch and apply a release update for an entity."""

    candidate = resolve_release_candidate(
        entity,
        fetch_candidates_from_recording=fetch_candidates_from_recording,
        fetch_candidates_from_release_set=fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fetch_candidates_from_artist,
        policy=policy,
    )
    if candidate is None:
        return None
    update = fetch_release_update(candidate)
    if isinstance(entity, Release):
        release = entity
    elif (isinstance(entity, Recording) and entity.releases) or (
        isinstance(entity, ReleaseSet) and entity.releases
    ):
        release = entity.releases[0]
    elif isinstance(entity, Artist) and entity.release_sets:
        release = entity.release_sets[0].releases[0]
    else:
        return None
    return apply_release_update(release, update)
