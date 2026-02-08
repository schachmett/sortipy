"""Resolve release candidates for enrichment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import Artist, ExternalNamespace, Recording, Release, ReleaseSet

from .dto import ReleaseCandidate

if TYPE_CHECKING:
    from sortipy.domain.model import Mbid
    from sortipy.domain.ports.enrichment import (
        ReleaseCandidatesFromArtist,
        ReleaseCandidatesFromRecording,
        ReleaseCandidatesFromReleaseSet,
    )


class ReleaseSelectionPolicy(Protocol):
    def choose(
        self,
        *,
        entity: Recording | ReleaseSet | Artist | Release,
        candidates: list[ReleaseCandidate],
    ) -> ReleaseCandidate | None: ...


def resolve_release_candidate(
    entity: Recording | ReleaseSet | Artist | Release,
    *,
    fetch_candidates_from_recording: ReleaseCandidatesFromRecording,
    fetch_candidates_from_release_set: ReleaseCandidatesFromReleaseSet,
    fetch_candidates_from_artist: ReleaseCandidatesFromArtist,
    policy: ReleaseSelectionPolicy | None = None,
) -> ReleaseCandidate | None:
    """Resolve a release candidate for enrichment.

    Strategy:
    1) Prefer a release already linked in the domain graph (and uniquely identified).
    2) Otherwise fetch candidates via adapter (recording → release_set → artist).
    3) Select candidate using policy (or default heuristic).
    """

    existing = _existing_release_candidates(entity)
    if existing:
        return _choose_candidate(entity, existing, policy)

    candidates: list[ReleaseCandidate] = []
    if isinstance(entity, Recording):
        candidates = fetch_candidates_from_recording(entity)
    elif isinstance(entity, ReleaseSet):
        candidates = fetch_candidates_from_release_set(entity)
    elif isinstance(entity, Artist):
        candidates = fetch_candidates_from_artist(entity)
    else:
        candidates = fetch_candidates_from_release_set(entity.release_set)

    if not candidates:
        return None

    return _choose_candidate(entity, candidates, policy)


def _existing_release_candidates(
    entity: Recording | ReleaseSet | Artist | Release,
) -> list[ReleaseCandidate]:
    releases: list[Release]
    if isinstance(entity, Release):
        releases = [entity]
    elif isinstance(entity, Recording | ReleaseSet):
        releases = list(entity.releases)
    else:
        releases = [release for rs in entity.release_sets for release in rs.releases]
    return _release_candidates_from_releases(releases)


def _release_candidates_from_releases(
    releases: list[Release],
) -> list[ReleaseCandidate]:
    candidates: list[ReleaseCandidate] = []
    for release in releases:
        mbid = _release_mbid(release)
        if mbid is None:
            continue
        candidates.append(_candidate_from_release(release, mbid))
    return candidates


def _candidate_from_release(release: Release, mbid: Mbid) -> ReleaseCandidate:
    release_set = release.release_set
    artist_names = [artist.name for artist in release_set.artists]
    return ReleaseCandidate(
        mbid=mbid,
        title=release.title,
        release_date=release.release_date,
        country=release.country,
        status=release.status,
        packaging=release.packaging,
        release_set_mbid=_release_set_mbid(release_set),
        artist_names=artist_names,
        track_count=len(release.tracks),
        media_formats=[release.format] if release.format else [],
    )


def _release_mbid(release: Release) -> Mbid | None:
    entry = release.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_RELEASE)
    if entry is None:
        return None
    return entry.value


def _release_set_mbid(release_set: ReleaseSet | None) -> Mbid | None:
    if release_set is None:
        return None
    entry = release_set.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP)
    if entry is None:
        return None
    return entry.value


def _choose_candidate(
    entity: Recording | ReleaseSet | Artist | Release,
    candidates: list[ReleaseCandidate],
    policy: ReleaseSelectionPolicy | None,
) -> ReleaseCandidate | None:
    if policy is not None:
        return policy.choose(entity=entity, candidates=candidates)
    return candidates[0] if candidates else None
