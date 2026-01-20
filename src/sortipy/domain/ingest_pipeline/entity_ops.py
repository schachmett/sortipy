"""Central registry for per-entity ingest operations."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    EntityType,
    ExternalNamespace,
    IdentifiedEntity,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    User,
)

from .context import NormalizationData

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from uuid import UUID

    from sortipy.domain.model import (
        ExternallyIdentifiable,
        Provenanced,
        ProvenanceTracked,
    )

    from .context import NormalizationState, NormKey, NormKeySeq


@dataclass(slots=True)
class BaseNormalizationData[TEntity: IdentifiedEntity](NormalizationData[TEntity]):
    priority_keys: NormKeySeq = field(init=False)

    @property
    def _keys(self) -> NormKeySeq: ...

    def __post_init__(self) -> None:
        seen: set[NormKey] = set()
        deduped: list[NormKey] = []
        for key in self._keys:
            if not all(key) or key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        self.priority_keys = tuple(deduped)


@dataclass(slots=True)
class ArtistNormalizationData(BaseNormalizationData[Artist]):
    normalized_name: str | None
    sources: tuple[str, ...]
    musicbrainz_id: str | None

    @property
    def _keys(self) -> NormKeySeq:
        return (
            ("artist:mbid", self.musicbrainz_id),
            ("artist:source-name", _primary_source(self.sources), self.normalized_name),
            ("artist:name", self.normalized_name),
        )


@dataclass(slots=True)
class ReleaseSetNormalizationData(BaseNormalizationData[ReleaseSet]):
    normalized_title: str | None
    normalized_primary_artist_name: str | None
    sources: tuple[str, ...]
    musicbrainz_id: str | None

    @property
    def _keys(self) -> NormKeySeq:
        return (
            ("release_set:mbid", self.musicbrainz_id),
            (
                "release_set:source-artist-title",
                _primary_source(self.sources),
                self.normalized_primary_artist_name,
                self.normalized_title,
            ),
            (
                "release_set:artist-title",
                self.normalized_primary_artist_name,
                self.normalized_title,
            ),
        )


@dataclass(slots=True)
class ReleaseNormalizationData(BaseNormalizationData[Release]):
    normalized_title: str | None
    normalized_artist_name: str | None
    sources: tuple[str, ...]
    musicbrainz_id: str | None

    @property
    def _keys(self) -> NormKeySeq:
        return (
            ("release:mbid", self.musicbrainz_id),
            (
                "release:source-artist-title",
                _primary_source(self.sources),
                self.normalized_artist_name,
                self.normalized_title,
            ),
            ("release:artist-title", self.normalized_artist_name, self.normalized_title),
        )


@dataclass(slots=True)
class RecordingNormalizationData(BaseNormalizationData[Recording]):
    normalized_title: str | None
    duration_bin: int | None
    normalized_primary_artist_name: str | None
    sources: tuple[str, ...]
    musicbrainz_id: str | None

    @property
    def _keys(self) -> NormKeySeq:
        return (
            ("recording:mbid", self.musicbrainz_id),
            (
                "recording:artist-title-duration",
                self.normalized_primary_artist_name,
                self.normalized_title,
                self.duration_bin,
            ),
            (
                "recording:source-artist-title",
                _primary_source(self.sources),
                self.normalized_primary_artist_name,
                self.normalized_title,
            ),
            ("recording:artist-title", self.normalized_primary_artist_name, self.normalized_title),
        )


@dataclass(slots=True)
class UserNormalizationData(BaseNormalizationData[User]):
    normalized_display_name: str | None
    email: str | None
    spotify_user_id: str | None
    lastfm_user: str | None

    @property
    def _keys(self) -> NormKeySeq:
        return (
            ("user:lastfm", self.lastfm_user),
            ("user:spotify", self.spotify_user_id),
            ("user:email", self.email),
            ("user:display_name", self.normalized_display_name),
        )


@dataclass(slots=True)
class PlayEventNormalizationData(BaseNormalizationData[PlayEvent]):
    user_id: UUID
    source: str
    played_at: datetime
    recording_id: UUID
    track_id: UUID | None

    @property
    def _keys(self) -> NormKeySeq:
        keys: list[NormKey] = [
            ("play_event:user-source-played_at", self.user_id, self.source, self.played_at),
            ("play_event:recording-played_at", self.recording_id, self.played_at),
        ]
        if self.track_id is not None:
            keys.append(("play_event:track-played_at", self.track_id, self.played_at))
        return tuple(keys)


# --- Helpers shared by compute functions -------------------------------------


_ROLE_PRIORITY: dict[ArtistRole | None, int] = {
    ArtistRole.PRIMARY: 0,
    ArtistRole.FEATURED: 1,
    ArtistRole.PRODUCER: 2,
    ArtistRole.COMPOSER: 3,
    ArtistRole.CONDUCTOR: 4,
    None: 10,
}


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value)
    text = text.casefold()
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    text = " ".join(text.split())
    return text or None


def _normalize_sources(entity: Provenanced) -> tuple[str, ...]:
    provenance = entity.provenance
    if provenance is None or not provenance.sources:
        return ()
    return tuple(sorted(provider.value for provider in provenance.sources))


def _primary_source(sources: tuple[str, ...]) -> str | None:
    if not sources:
        return None
    return sources[0]


def _external_id_value(
    entity: ExternallyIdentifiable, namespace: ExternalNamespace | str
) -> str | None:
    target_namespace = str(namespace)
    for external_id in entity.external_ids:
        if str(external_id.namespace) == target_namespace:
            return external_id.value
    return None


def _release_set_primary_artist_name(
    release_set: ReleaseSet,
    state: NormalizationState,
) -> str | None:
    if not release_set.contributions:
        return None
    ordered = sorted(
        release_set.contributions,
        key=lambda contribution: (
            _ROLE_PRIORITY.get(contribution.role, 10),
            contribution.credit_order if contribution.credit_order is not None else 10_000,
        ),
    )
    for contribution in ordered:
        artist_data = state.fetch(contribution.artist)
        if artist_data is not None and artist_data.normalized_name:
            return artist_data.normalized_name
        fallback = _normalize_text(contribution.artist.name)
        if fallback:
            return fallback
    return None


def _release_artist_name(release: Release, state: NormalizationState) -> str | None:
    release_set_data = state.fetch(release.release_set)
    if release_set_data is not None and release_set_data.normalized_primary_artist_name:
        return release_set_data.normalized_primary_artist_name
    fallback = _release_set_primary_artist_name(release.release_set, state)
    if fallback:
        return fallback
    for track in release.tracks:
        recording_name = _recording_primary_artist_name(track.recording, state)
        if recording_name:
            return recording_name
    return None


def _recording_primary_artist_name(recording: Recording, state: NormalizationState) -> str | None:
    if not recording.contributions:
        return None
    ordered = sorted(
        recording.contributions,
        key=lambda contribution: (
            _ROLE_PRIORITY.get(contribution.role, 10),
            contribution.credit_order if contribution.credit_order is not None else 10_000,
        ),
    )
    for contribution in ordered:
        artist_data = state.fetch(contribution.artist)
        if artist_data is not None and artist_data.normalized_name:
            return artist_data.normalized_name
        fallback = _normalize_text(contribution.artist.name)
        if fallback:
            return fallback
    return None


def _normalize_duration(duration_ms: int | None, *, bucket_ms: int = 2000) -> int | None:
    if duration_ms is None:
        return None
    return duration_ms // bucket_ms


# --- Compute functions -------------------------------------------------------


def normalize_artist(
    artist: Artist,
    _state: NormalizationState,
) -> ArtistNormalizationData:
    normalized_name = _normalize_text(artist.name)
    sources = _normalize_sources(artist)
    return ArtistNormalizationData(
        normalized_name=normalized_name,
        sources=sources,
        musicbrainz_id=_external_id_value(artist, ExternalNamespace.MUSICBRAINZ_ARTIST),
    )


def normalize_release_set(
    release_set: ReleaseSet,
    state: NormalizationState,
) -> ReleaseSetNormalizationData:
    normalized_title = _normalize_text(release_set.title)
    normalized_primary_artist = _release_set_primary_artist_name(release_set, state)
    return ReleaseSetNormalizationData(
        normalized_title=normalized_title,
        normalized_primary_artist_name=normalized_primary_artist,
        sources=_normalize_sources(release_set),
        musicbrainz_id=_external_id_value(
            release_set,
            ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
        ),
    )


def normalize_release(
    release: Release,
    state: NormalizationState,
) -> ReleaseNormalizationData:
    normalized_title = _normalize_text(release.title)
    normalized_artist_name = _release_artist_name(release, state)
    return ReleaseNormalizationData(
        normalized_title=normalized_title,
        normalized_artist_name=normalized_artist_name,
        sources=_normalize_sources(release),
        musicbrainz_id=_external_id_value(release, ExternalNamespace.MUSICBRAINZ_RELEASE),
    )


def normalize_recording(
    recording: Recording,
    state: NormalizationState,
) -> RecordingNormalizationData:
    normalized_title = _normalize_text(recording.title)
    duration_bin = _normalize_duration(recording.duration_ms)
    normalized_primary_artist = _recording_primary_artist_name(recording, state)
    return RecordingNormalizationData(
        normalized_title=normalized_title,
        duration_bin=duration_bin,
        normalized_primary_artist_name=normalized_primary_artist,
        sources=_normalize_sources(recording),
        musicbrainz_id=_external_id_value(recording, ExternalNamespace.MUSICBRAINZ_RECORDING),
    )


def normalize_user(
    user: User,
    _state: NormalizationState,
) -> UserNormalizationData:
    return UserNormalizationData(
        normalized_display_name=_normalize_text(user.display_name),
        email=user.email,
        spotify_user_id=user.spotify_user_id,
        lastfm_user=user.lastfm_user,
    )


def normalize_play_event(
    play_event: PlayEvent,
    _state: NormalizationState,
) -> PlayEventNormalizationData:
    track = play_event.track
    return PlayEventNormalizationData(
        user_id=play_event.user.resolved_id,
        source=play_event.source.value,
        played_at=play_event.played_at,
        recording_id=play_event.recording.resolved_id,
        track_id=track.resolved_id if track is not None else None,
    )


# --- Absorb policies ---------------------------------------------------------


def absorb_artist(primary: Artist, duplicate: Artist) -> None:
    _merge_scalar_attributes(
        primary,
        duplicate,
        ("sort_name", "country", "formed_year", "disbanded_year"),
    )
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)

    for contribution in list(duplicate.release_set_contributions):
        contribution.release_set.replace_artist(duplicate, primary)
    for contribution in list(duplicate.recording_contributions):
        contribution.recording.replace_artist(duplicate, primary)


def absorb_release_set(primary: ReleaseSet, duplicate: ReleaseSet) -> None:
    _merge_scalar_attributes(primary, duplicate, ("primary_type",))
    if primary.first_release is None and duplicate.first_release is not None:
        primary.first_release = duplicate.first_release
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)

    duplicate.move_contributions_to(primary)
    for release in list(duplicate.releases):
        duplicate.remove_release(release)
        primary.add_release(release)


def absorb_release(primary: Release, duplicate: Release) -> None:
    _merge_scalar_attributes(
        primary,
        duplicate,
        ("release_date", "country", "format", "medium_count"),
    )
    if not primary.labels and duplicate.labels:
        for label in duplicate.labels:
            primary.add_label(label)
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)

    duplicate.release_set.remove_release(duplicate)
    duplicate.move_tracks_to(primary)


def absorb_recording(primary: Recording, duplicate: Recording) -> None:
    _merge_scalar_attributes(primary, duplicate, ("duration_ms", "version"))
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)

    duplicate.move_contributions_to(primary)
    duplicate.move_tracks_to(primary)


def absorb_user(primary: User, duplicate: User) -> None:
    _merge_scalar_attributes(
        primary,
        duplicate,
        ("email", "spotify_user_id", "lastfm_user"),
    )
    if not primary.display_name and duplicate.display_name:
        primary.display_name = duplicate.display_name
    _merge_sources(primary, duplicate)


def absorb_play_event(primary: PlayEvent, duplicate: PlayEvent) -> None:
    if primary.track is None and duplicate.track is not None:
        primary.user.link_play_to_track(primary, duplicate.track)
    if primary.duration_ms is None and duplicate.duration_ms is not None:
        primary.duration_ms = duplicate.duration_ms
    _merge_sources(primary, duplicate)


# --- Shared merge helpers ----------------------------------------------------


def _merge_scalar_attributes(
    primary: object,
    duplicate: object,
    attributes: tuple[str, ...],
) -> None:
    for attribute in attributes:
        if getattr(primary, attribute) is None:
            value = getattr(duplicate, attribute)
            if value is not None:
                setattr(primary, attribute, value)


def _merge_sources(primary: ProvenanceTracked, duplicate: Provenanced) -> None:
    provenance = duplicate.provenance
    if provenance is None:
        return
    for source in provenance.sources:
        primary.add_source(source)


def _merge_external_ids(primary: ExternallyIdentifiable, duplicate: ExternallyIdentifiable) -> None:
    existing = {(external_id.namespace, external_id.value) for external_id in primary.external_ids}
    for external_id in duplicate.external_ids:
        key = (external_id.namespace, external_id.value)
        if key in existing:
            continue
        primary.add_external_id(
            external_id.namespace,
            external_id.value,
            provider=external_id.provider,
        )
        existing.add(key)


# --- Registry ---------------------------------------------------------------


@dataclass(slots=True)
class EntityOps[TEntity: IdentifiedEntity]:
    data_type: type[NormalizationData[TEntity]]
    normalize: Callable[[TEntity, NormalizationState], NormalizationData[TEntity]]
    absorb: Callable[[TEntity, TEntity], None]


_REGISTRY: dict[EntityType, EntityOps[Any]] = {
    EntityType.ARTIST: EntityOps(
        data_type=ArtistNormalizationData,
        normalize=normalize_artist,
        absorb=absorb_artist,
    ),
    EntityType.RELEASE_SET: EntityOps(
        data_type=ReleaseSetNormalizationData,
        normalize=normalize_release_set,
        absorb=absorb_release_set,
    ),
    EntityType.RELEASE: EntityOps(
        data_type=ReleaseNormalizationData,
        normalize=normalize_release,
        absorb=absorb_release,
    ),
    EntityType.RECORDING: EntityOps(
        data_type=RecordingNormalizationData,
        normalize=normalize_recording,
        absorb=absorb_recording,
    ),
    EntityType.USER: EntityOps(
        data_type=UserNormalizationData,
        normalize=normalize_user,
        absorb=absorb_user,
    ),
    EntityType.PLAY_EVENT: EntityOps(
        data_type=PlayEventNormalizationData,
        normalize=normalize_play_event,
        absorb=absorb_play_event,
    ),
}


def ops_for[TEntity: IdentifiedEntity](entity: TEntity) -> EntityOps[TEntity]:
    try:
        return _REGISTRY[entity.entity_type]
    except KeyError as exc:
        raise RuntimeError(f"No ops registered for {entity.entity_type}") from exc
