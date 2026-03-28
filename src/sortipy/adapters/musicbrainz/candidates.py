"""MusicBrainz release candidate types and selection helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import Artist, ExternalNamespace, Recording, Release, ReleaseSet

if TYPE_CHECKING:
    from sortipy.domain.model import CountryCode, Mbid, PartialDate, ReleasePackaging, ReleaseStatus

    from .schema import MBRelease, MBReleaseRef


def _new_strings() -> list[str]:
    return []


@dataclass(slots=True)
class MusicBrainzReleaseCandidate:
    """Candidate release summary for MusicBrainz selection."""

    mbid: Mbid
    title: str | None = None
    release_date: PartialDate | None = None
    status: ReleaseStatus | None = None
    packaging: ReleasePackaging | None = None
    country: CountryCode | None = None
    release_set_mbid: Mbid | None = None
    artist_names: list[str] = field(default_factory=_new_strings)
    track_count: int | None = None
    media_formats: list[str] = field(default_factory=_new_strings)


MusicBrainzReleaseGraphFetcher = Callable[[MusicBrainzReleaseCandidate], Release]
MusicBrainzReleaseCandidatesFromRecording = Callable[[Recording], list[MusicBrainzReleaseCandidate]]
MusicBrainzReleaseCandidatesFromReleaseSet = Callable[
    [ReleaseSet], list[MusicBrainzReleaseCandidate]
]
MusicBrainzReleaseCandidatesFromArtist = Callable[[Artist], list[MusicBrainzReleaseCandidate]]


class MusicBrainzReleaseSelectionPolicy(Protocol):
    def choose(
        self,
        *,
        entity: Recording | ReleaseSet | Artist | Release,
        candidates: list[MusicBrainzReleaseCandidate],
    ) -> MusicBrainzReleaseCandidate | None: ...


def resolve_release_candidate(
    entity: Recording | ReleaseSet | Artist | Release,
    *,
    fetch_candidates_from_recording: MusicBrainzReleaseCandidatesFromRecording,
    fetch_candidates_from_release_set: MusicBrainzReleaseCandidatesFromReleaseSet,
    fetch_candidates_from_artist: MusicBrainzReleaseCandidatesFromArtist,
    policy: MusicBrainzReleaseSelectionPolicy | None = None,
) -> MusicBrainzReleaseCandidate | None:
    """Resolve the best MusicBrainz release candidate for ``entity``."""

    existing = _existing_release_candidates(entity)
    if existing:
        return _choose_candidate(entity, existing, policy)

    candidates: list[MusicBrainzReleaseCandidate] = []
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


def release_candidate_from_release(
    release: MBRelease,
    *,
    release_date: PartialDate | None,
    status: ReleaseStatus | None,
    packaging: ReleasePackaging | None,
    track_count: int | None,
    media_formats: list[str],
) -> MusicBrainzReleaseCandidate:
    artist_names = [credit.artist.name for credit in release.artist_credit]
    release_set_mbid = release.release_group.id if release.release_group is not None else None
    return MusicBrainzReleaseCandidate(
        mbid=release.id,
        title=release.title,
        release_date=release_date,
        status=status,
        packaging=packaging,
        country=release.country,
        release_set_mbid=release_set_mbid,
        artist_names=artist_names,
        track_count=track_count,
        media_formats=media_formats,
    )


def release_candidate_from_release_ref(
    release: MBReleaseRef,
    *,
    release_date: PartialDate | None,
    status: ReleaseStatus | None,
    packaging: ReleasePackaging | None,
) -> MusicBrainzReleaseCandidate:
    return MusicBrainzReleaseCandidate(
        mbid=release.id,
        title=release.title,
        release_date=release_date,
        status=status,
        packaging=packaging,
        country=release.country,
    )


def _existing_release_candidates(
    entity: Recording | ReleaseSet | Artist | Release,
) -> list[MusicBrainzReleaseCandidate]:
    releases: list[Release]
    if isinstance(entity, Release):
        releases = [entity]
    elif isinstance(entity, Recording | ReleaseSet):
        releases = list(entity.releases)
    else:
        releases = [
            release for release_set in entity.release_sets for release in release_set.releases
        ]
    return _release_candidates_from_releases(releases)


def _release_candidates_from_releases(releases: list[Release]) -> list[MusicBrainzReleaseCandidate]:
    candidates: list[MusicBrainzReleaseCandidate] = []
    for release in releases:
        mbid = _release_mbid(release)
        if mbid is None:
            continue
        candidates.append(_candidate_from_release(release, mbid))
    return candidates


def _candidate_from_release(release: Release, mbid: Mbid) -> MusicBrainzReleaseCandidate:
    release_set = release.release_set
    return MusicBrainzReleaseCandidate(
        mbid=mbid,
        title=release.title,
        release_date=release.release_date,
        country=release.country,
        status=release.status,
        packaging=release.packaging,
        release_set_mbid=_release_set_mbid(release_set),
        artist_names=[artist.name for artist in release_set.artists],
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
    candidates: list[MusicBrainzReleaseCandidate],
    policy: MusicBrainzReleaseSelectionPolicy | None,
) -> MusicBrainzReleaseCandidate | None:
    if policy is not None:
        return policy.choose(entity=entity, candidates=candidates)
    return candidates[0] if candidates else None
