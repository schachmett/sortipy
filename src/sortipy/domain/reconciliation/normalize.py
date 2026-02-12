"""Normalization stage contracts for claim reconciliation.

Responsibilities of this stage:
- derive deterministic lookup keys from claims
- expose keys per claim node (not per canonical entity)
- avoid persistence side effects

Implementation note:
- key strategies currently live in ``domain.ingest_pipeline.entity_ops``
- this module is the target destination for claim-based equivalents
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Hashable
from dataclasses import dataclass
from functools import singledispatch
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Label,
    LibraryItem,
    PlayEvent,
    Recording,
    RecordingContribution,
    Release,
    ReleaseSet,
    ReleaseSetContribution,
    ReleaseTrack,
    User,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import (
        AssociationEntity,
        ExternallyIdentifiable,
        Namespace,
        Provenanced,
        Provider,
    )

    from .claims import RelationshipClaim
    from .graph import ClaimGraph


type ClaimKey = tuple[Hashable, ...]
_DEFAULT_IDENTITY_DURATION_BUCKET_MS = 2000
log = logging.getLogger(__name__)


@dataclass(slots=True)
class NormalizationResult:
    """Deterministic keys for every claim in the graph."""

    keys_by_claim: dict[UUID, tuple[ClaimKey, ...]]


class ClaimNormalizer(Protocol):
    """Compute deterministic keys for a claim graph."""

    def normalize(self, graph: ClaimGraph) -> NormalizationResult: ...


@dataclass(slots=True, kw_only=True)
class DefaultClaimNormalizer:
    """Default deterministic key strategy for reconciliation claims."""

    duration_bucket_ms: int = 2000

    def normalize(self, graph: ClaimGraph) -> NormalizationResult:
        keys_by_claim: dict[UUID, tuple[ClaimKey, ...]] = {}
        for claim in graph.claims:
            keys = _keys_for_entity(claim.entity, self.duration_bucket_ms)
            keys_by_claim[claim.claim_id] = keys
            if not keys:
                log.warning(
                    "No normalization keys for claim_id=%s entity_type=%s",
                    claim.claim_id,
                    claim.entity_type,
                )
        return NormalizationResult(keys_by_claim=keys_by_claim)


_ROLE_PRIORITY: dict[ArtistRole | None, int] = {
    ArtistRole.PRIMARY: 0,
    ArtistRole.FEATURED: 1,
    ArtistRole.PRODUCER: 2,
    ArtistRole.COMPOSER: 3,
    ArtistRole.CONDUCTOR: 4,
    ArtistRole.UNKNOWN: 10,
    None: 11,
}


@singledispatch
def _keys_for_entity(_entity: object, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    return ()


@_keys_for_entity.register
def _(artist: Artist, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    normalized_name = _normalize_text(artist.name)
    sources = _normalized_sources(artist)
    return _filter_and_dedupe_keys(
        (
            ("artist:mbid", _external_id_value(artist, ExternalNamespace.MUSICBRAINZ_ARTIST)),
            ("artist:source-name", _primary_source(sources), normalized_name),
            ("artist:name", normalized_name),
        )
    )


@_keys_for_entity.register
def _(release_set: ReleaseSet, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    normalized_title = _normalize_text(release_set.title)
    normalized_artist = _release_set_primary_artist_name(release_set)
    sources = _normalized_sources(release_set)
    return _filter_and_dedupe_keys(
        (
            (
                "release_set:mbid",
                _external_id_value(release_set, ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP),
            ),
            (
                "release_set:source-artist-title",
                _primary_source(sources),
                normalized_artist,
                normalized_title,
            ),
            ("release_set:artist-title", normalized_artist, normalized_title),
        )
    )


@_keys_for_entity.register
def _(release: Release, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    normalized_title = _normalize_text(release.title)
    normalized_artist = _release_artist_name(release)
    sources = _normalized_sources(release)
    return _filter_and_dedupe_keys(
        (
            ("release:mbid", _external_id_value(release, ExternalNamespace.MUSICBRAINZ_RELEASE)),
            (
                "release:source-artist-title",
                _primary_source(sources),
                normalized_artist,
                normalized_title,
            ),
            ("release:artist-title", normalized_artist, normalized_title),
        )
    )


@_keys_for_entity.register
def _(recording: Recording, duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    normalized_title = _normalize_text(recording.title)
    duration_bin = _normalize_duration(recording.duration_ms, bucket_ms=duration_bucket_ms)
    normalized_artist = _recording_primary_artist_name(recording)
    sources = _normalized_sources(recording)
    return _filter_and_dedupe_keys(
        (
            (
                "recording:mbid",
                _external_id_value(recording, ExternalNamespace.MUSICBRAINZ_RECORDING),
            ),
            (
                "recording:artist-title-duration",
                normalized_artist,
                normalized_title,
                duration_bin,
            ),
            (
                "recording:source-artist-title",
                _primary_source(sources),
                normalized_artist,
                normalized_title,
            ),
            ("recording:artist-title", normalized_artist, normalized_title),
        )
    )


@_keys_for_entity.register
def _(label: Label, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    normalized_name = _normalize_text(label.name)
    sources = _normalized_sources(label)
    return _filter_and_dedupe_keys(
        (
            ("label:mbid", _external_id_value(label, ExternalNamespace.MUSICBRAINZ_LABEL)),
            ("label:source-name", _primary_source(sources), normalized_name),
            ("label:name", normalized_name),
        )
    )


@_keys_for_entity.register
def _(user: User, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    return _filter_and_dedupe_keys(
        (
            ("user:lastfm", user.lastfm_user),
            ("user:spotify", user.spotify_user_id),
            ("user:email", user.email),
            ("user:display_name", _normalize_text(user.display_name)),
        )
    )


@_keys_for_entity.register
def _(event: PlayEvent, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    user_identity = _identity_key_for_entity(event.user)
    recording_identity = _identity_key_for_entity(event.recording)
    keys: list[ClaimKey] = [
        ("play_event:user-source-played_at", user_identity, event.source, event.played_at),
        ("play_event:recording-played_at", recording_identity, event.played_at),
    ]
    if event.track is not None:
        keys.append(
            (
                "play_event:track-played_at",
                _identity_key_for_entity(event.track),
                event.played_at,
            )
        )
    return _filter_and_dedupe_keys(tuple(keys))


@_keys_for_entity.register
def _(item: LibraryItem, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    user_identity = _identity_key_for_entity(item.user)
    target_identity = _library_item_target_identity(item)
    return _filter_and_dedupe_keys(
        (
            (
                "library_item:user-target",
                user_identity,
                item.target_type,
                target_identity,
            ),
            (
                "library_item:user-source-target",
                user_identity,
                item.source,
                item.target_type,
                target_identity,
            ),
        )
    )


@_keys_for_entity.register
def _(track: ReleaseTrack, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    return _filter_and_dedupe_keys(
        (
            (
                "release_track:release-recording",
                _identity_key_for_entity(track.release),
                _identity_key_for_entity(track.recording),
            ),
            (
                "release_track:release-position",
                _identity_key_for_entity(track.release),
                track.disc_number,
                track.track_number,
            ),
        )
    )


@_keys_for_entity.register
def _(contribution: ReleaseSetContribution, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    return _filter_and_dedupe_keys(
        (
            (
                "release_set_contribution:release_set-artist-role",
                _identity_key_for_entity(contribution.release_set),
                _identity_key_for_entity(contribution.artist),
                contribution.role or ArtistRole.UNKNOWN,
            ),
            (
                "release_set_contribution:release_set-artist-credit_order",
                _identity_key_for_entity(contribution.release_set),
                _identity_key_for_entity(contribution.artist),
                contribution.credit_order if contribution.credit_order is not None else -1,
            ),
        )
    )


@_keys_for_entity.register
def _(contribution: RecordingContribution, _duration_bucket_ms: int) -> tuple[ClaimKey, ...]:
    return _filter_and_dedupe_keys(
        (
            (
                "recording_contribution:recording-artist-role",
                _identity_key_for_entity(contribution.recording),
                _identity_key_for_entity(contribution.artist),
                contribution.role or ArtistRole.UNKNOWN,
            ),
            (
                "recording_contribution:recording-artist-credit_order",
                _identity_key_for_entity(contribution.recording),
                _identity_key_for_entity(contribution.artist),
                contribution.credit_order if contribution.credit_order is not None else -1,
            ),
        )
    )


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value)
    text = text.casefold()
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    text = " ".join(text.split())
    return text or None


def _filter_and_dedupe_keys(keys: tuple[ClaimKey, ...]) -> tuple[ClaimKey, ...]:
    """Drop incomplete keys and dedupe while preserving first-seen order."""

    seen: set[ClaimKey] = set()
    filtered: list[ClaimKey] = []
    for key in keys:
        if not _all_key_values_present(key) or key in seen:
            continue
        seen.add(key)
        filtered.append(key)
    return tuple(filtered)


def _all_key_values_present(key: ClaimKey) -> bool:
    return all(_is_key_value_present(value) for value in key)


def _is_key_value_present(value: Hashable) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    return True


def _normalized_sources(entity: Provenanced) -> tuple[Provider, ...]:
    provenance = entity.provenance
    if provenance is None or not provenance.sources:
        return ()
    return tuple(sorted(provenance.sources, key=lambda source: source.value))


def _primary_source(sources: tuple[Provider, ...]) -> Provider | None:
    if not sources:
        return None
    return sources[0]


def _external_id_value(
    entity: ExternallyIdentifiable,
    namespace: Namespace,
) -> str | None:
    target_namespace = str(namespace)
    for external_id in entity.external_ids:
        if str(external_id.namespace) == target_namespace:
            return external_id.value
    return None


def _release_set_primary_artist_name(release_set: ReleaseSet) -> str | None:
    if not release_set.contributions:
        return None
    ordered = sorted(
        release_set.contributions,
        key=lambda contribution: (
            _ROLE_PRIORITY.get(contribution.role, 11),
            contribution.credit_order if contribution.credit_order is not None else 10_000,
        ),
    )
    for contribution in ordered:
        normalized_name = _normalize_text(contribution.artist.name)
        if normalized_name:
            return normalized_name
    return None


def _release_artist_name(release: Release) -> str | None:
    from_release_set = _release_set_primary_artist_name(release.release_set)
    if from_release_set:
        return from_release_set
    for track in release.tracks:
        recording_name = _recording_primary_artist_name(track.recording)
        if recording_name:
            return recording_name
    return None


def _recording_primary_artist_name(recording: Recording) -> str | None:
    if not recording.contributions:
        return None
    ordered = sorted(
        recording.contributions,
        key=lambda contribution: (
            _ROLE_PRIORITY.get(contribution.role, 11),
            contribution.credit_order if contribution.credit_order is not None else 10_000,
        ),
    )
    for contribution in ordered:
        normalized_name = _normalize_text(contribution.artist.name)
        if normalized_name:
            return normalized_name
    return None


def _normalize_duration(duration_ms: int | None, *, bucket_ms: int) -> int | None:
    if duration_ms is None:
        return None
    return duration_ms // bucket_ms


def _identity_key_for_entity(entity: object) -> ClaimKey | None:
    keys = _keys_for_entity(entity, _DEFAULT_IDENTITY_DURATION_BUCKET_MS)
    return _preferred_identity_key_from_keys(keys)


def _preferred_identity_key_from_keys(keys: tuple[ClaimKey, ...]) -> ClaimKey | None:
    for key in keys:
        head = key[0]
        if isinstance(head, str) and ":source-" not in head:
            return key
    return keys[0] if keys else None


def _library_item_target_identity(item: LibraryItem) -> ClaimKey | None:
    target = item.target
    if target is not None:
        return _identity_key_for_entity(target)
    return ("library_item:target", str(item.target_type), str(item.target_id))


def normalized_relationship_key(claim: RelationshipClaim) -> ClaimKey:
    payload_components = _normalized_relationship_payload(claim.payload)
    return (
        "relationship",
        claim.kind,
        claim.source_claim_id,
        claim.target_claim_id,
        *payload_components,
    )


def _normalized_relationship_payload(payload: AssociationEntity | None) -> tuple[Hashable, ...]:
    if payload is None:
        return ()
    return _relationship_payload_components(payload)


@singledispatch
def _relationship_payload_components(_payload: object) -> tuple[Hashable, ...]:
    return ()


@_relationship_payload_components.register
def _(payload: ReleaseTrack) -> tuple[Hashable, ...]:
    return (
        payload.disc_number if payload.disc_number is not None else -1,
        payload.track_number if payload.track_number is not None else -1,
        _normalize_text(payload.title_override),
        payload.duration_ms,
    )


@_relationship_payload_components.register
def _(payload: ReleaseSetContribution) -> tuple[Hashable, ...]:
    return (
        payload.role or ArtistRole.UNKNOWN,
        payload.credit_order if payload.credit_order is not None else -1,
        _normalize_text(payload.credited_as),
        _normalize_text(payload.join_phrase),
    )


@_relationship_payload_components.register
def _(payload: RecordingContribution) -> tuple[Hashable, ...]:
    return (
        payload.role or ArtistRole.UNKNOWN,
        payload.credit_order if payload.credit_order is not None else -1,
        _normalize_text(payload.credited_as),
        _normalize_text(payload.join_phrase),
    )
