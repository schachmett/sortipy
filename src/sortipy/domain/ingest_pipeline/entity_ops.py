"""Central registry for per-entity ingest operations."""
# ruff: noqa: I001

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from sortipy.domain.ingest_pipeline.state import (
    NormalizationData,
    NormalizationState,
)
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    CanonicalEntity,
    CanonicalEntityType,
    ExternalNamespace,
    Recording,
    Release,
    ReleaseSet,
    Track,
)


@dataclass(slots=True)
class BaseNormalizationData[TEntity: CanonicalEntity](NormalizationData[TEntity]):
    priority_keys: tuple[tuple[object, ...], ...] = field(init=False)

    @property
    def _keys(self) -> tuple[tuple[object, ...], ...]: ...

    def __post_init__(self) -> None:
        seen: set[tuple[object, ...]] = set()
        deduped: list[tuple[object, ...]] = []
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
    def _keys(self) -> tuple[tuple[object, ...], ...]:
        return (
            ("artist:mbid", self.musicbrainz_id),
            ("artist:name", self.normalized_name),
        )


@dataclass(slots=True)
class ReleaseSetNormalizationData(BaseNormalizationData[ReleaseSet]):
    normalized_title: str | None
    normalized_primary_artist_name: str | None
    musicbrainz_id: str | None

    @property
    def _keys(self) -> tuple[tuple[object, ...], ...]:
        return (
            ("release_set:mbid", self.musicbrainz_id),
            (
                "release_set:artist-title",
                self.normalized_primary_artist_name,
                self.normalized_title,
            ),
            ("release_set:title", self.normalized_title),
        )


@dataclass(slots=True)
class ReleaseNormalizationData(BaseNormalizationData[Release]):
    normalized_title: str | None
    normalized_artist_name: str | None
    musicbrainz_id: str | None

    @property
    def _keys(self) -> tuple[tuple[object, ...], ...]:
        return (
            ("release:mbid", self.musicbrainz_id),
            ("release:artist-title", self.normalized_artist_name, self.normalized_title),
            ("release:title", self.normalized_title),
        )


@dataclass(slots=True)
class RecordingNormalizationData(BaseNormalizationData[Recording]):
    normalized_title: str | None
    duration_bin: int | None
    normalized_primary_artist_name: str | None
    musicbrainz_id: str | None

    @property
    def _keys(self) -> tuple[tuple[object, ...], ...]:
        return (
            ("recording:mbid", self.musicbrainz_id),
            (
                "recording:artist-title-duration",
                self.normalized_primary_artist_name,
                self.normalized_title,
                self.duration_bin,
            ),
            ("recording:artist-title", self.normalized_primary_artist_name, self.normalized_title),
            ("recording:title-duration", self.normalized_title, self.duration_bin),
            ("recording:title", self.normalized_title),
        )


@dataclass(slots=True)
class TrackNormalizationData(BaseNormalizationData[Track]):
    normalized_title: str | None
    release_keys: tuple[tuple[object, ...], ...]
    recording_keys: tuple[tuple[object, ...], ...]
    disc_number: int | None
    track_number: int | None

    @property
    def _keys(self) -> tuple[tuple[object, ...], ...]:
        return (
            *(
                (
                    "track:full",
                    release_key,
                    recording_key,
                    self.disc_number,
                    self.track_number,
                    self.normalized_title,
                )
                for release_key in self.release_keys
                for recording_key in self.recording_keys
            ),
            *(
                (
                    "track:release-recording-title",
                    release_key,
                    recording_key,
                    self.normalized_title,
                )
                for release_key in self.release_keys
                for recording_key in self.recording_keys
            ),
            (
                "track:title-position",
                self.normalized_title,
                self.disc_number,
                self.track_number,
            ),
            ("track:title", self.normalized_title),
        )


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


def _normalize_sources(entity: object) -> tuple[str, ...]:
    sources = getattr(entity, "sources", None)
    if not sources:
        return ()
    return tuple(sorted(provider.value for provider in sources))


def _external_id_value(entity: CanonicalEntity, namespace: ExternalNamespace | str) -> str | None:
    target_namespace = str(namespace)
    for external_id in entity.external_ids:
        if str(external_id.namespace) == target_namespace:
            return external_id.value
    return None


def _release_set_primary_artist_name(
    release_set: ReleaseSet,
    state: NormalizationState,
) -> str | None:
    if not release_set.artists:
        return None
    ordered = sorted(
        release_set.artists,
        key=lambda link: (
            _ROLE_PRIORITY.get(link.role, 10),
            link.credit_order if link.credit_order is not None else 10_000,
        ),
    )
    for link in ordered:
        artist_data = state.fetch(link.artist)
        if artist_data is not None and artist_data.normalized_name:
            return artist_data.normalized_name
        fallback = _normalize_text(link.artist.name)
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
    if not recording.artists:
        return None
    ordered = sorted(
        recording.artists,
        key=lambda link: (
            _ROLE_PRIORITY.get(link.role, 10),
            link.credit_order if link.credit_order is not None else 10_000,
        ),
    )
    for link in ordered:
        artist_data = state.fetch(link.artist)
        if artist_data is not None and artist_data.normalized_name:
            return artist_data.normalized_name
        fallback = _normalize_text(link.artist.name)
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
    _state: NormalizationState | None = None,
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
        musicbrainz_id=_external_id_value(recording, ExternalNamespace.MUSICBRAINZ_RECORDING),
    )


def normalize_track(
    track: Track,
    state: NormalizationState,
) -> TrackNormalizationData:
    base_title = track.title_override or track.recording.title
    normalized_title = _normalize_text(base_title)
    release_data = state.fetch(track.release)
    if not release_data is not None:
        raise TypeError("Release normalization must run before track normalization")
    recording_data = state.fetch(track.recording)
    if not recording_data is not None:
        raise TypeError("Recording normalization must run before track normalization")
    return TrackNormalizationData(
        normalized_title=normalized_title,
        release_keys=release_data.priority_keys,
        recording_keys=recording_data.priority_keys,
        disc_number=track.disc_number or 1,
        track_number=track.track_number,
    )


# --- Merge policies ----------------------------------------------------------


def merge_artist(primary: Artist, duplicate: Artist) -> None:
    _merge_scalar_attributes(
        primary,
        duplicate,
        ("sort_name", "country", "formed_year", "disbanded_year"),
    )
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)


def merge_release_set(primary: ReleaseSet, duplicate: ReleaseSet) -> None:
    _merge_scalar_attributes(primary, duplicate, ("primary_type",))
    if primary.first_release is None and duplicate.first_release is not None:
        primary.first_release = duplicate.first_release
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)


def merge_release(primary: Release, duplicate: Release) -> None:
    _merge_scalar_attributes(
        primary,
        duplicate,
        ("release_date", "country", "format", "medium_count"),
    )
    if not primary.labels and duplicate.labels:
        primary.labels = duplicate.labels
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)


def merge_recording(primary: Recording, duplicate: Recording) -> None:
    _merge_scalar_attributes(primary, duplicate, ("duration_ms", "version"))
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)


def merge_track(primary: Track, duplicate: Track) -> None:
    _merge_scalar_attributes(
        primary,
        duplicate,
        ("disc_number", "track_number", "title_override", "duration_ms"),
    )
    _merge_sources(primary, duplicate)
    _merge_external_ids(primary, duplicate)


# --- Reference rewriters -----------------------------------------------------


def rewire_artist(primary: Artist, duplicate: Artist) -> None:
    for release_set in list(duplicate.release_sets):
        _ensure_item(primary.release_sets, release_set)
        for link in release_set.artists:
            if link.artist is duplicate:
                link.artist = primary
        duplicate.release_sets.clear()

    for recording in list(duplicate.recordings):
        _ensure_item(primary.recordings, recording)
        for link in recording.artists:
            if link.artist is duplicate:
                link.artist = primary
        duplicate.recordings.clear()


def rewire_release_set(primary: ReleaseSet, duplicate: ReleaseSet) -> None:
    for release in list(duplicate.releases):
        release.release_set = primary
        _ensure_item(primary.releases, release)
    duplicate.releases.clear()

    for link in list(duplicate.artists):
        link.release_set = primary
        _replace_item(link.artist.release_sets, duplicate, primary)
        _ensure_item(primary.artists, link)
    duplicate.artists.clear()


def rewire_release(primary: Release, duplicate: Release) -> None:
    release_set = primary.release_set or duplicate.release_set
    _replace_item(release_set.releases, duplicate, primary)
    primary.release_set = release_set
    duplicate.release_set = release_set

    for track in list(duplicate.tracks):
        track.release = primary
        _ensure_item(primary.tracks, track)
    duplicate.tracks.clear()


def rewire_recording(primary: Recording, duplicate: Recording) -> None:
    for track in list(duplicate.tracks):
        track.recording = primary
        _ensure_item(primary.tracks, track)
    duplicate.tracks.clear()

    for play_event in list(duplicate.play_events):
        play_event.recording = primary
        _ensure_item(primary.play_events, play_event)
    duplicate.play_events.clear()

    for link in list(duplicate.artists):
        link.recording = primary
        _replace_item(link.artist.recordings, duplicate, primary)
        _ensure_item(primary.artists, link)
    duplicate.artists.clear()


def rewire_track(primary: Track, duplicate: Track) -> None:
    source_release = duplicate.release
    target_release = primary.release
    _replace_item(source_release.tracks, duplicate, primary)
    if target_release is not source_release:
        _ensure_item(target_release.tracks, primary)
    duplicate.release = target_release

    source_recording = duplicate.recording
    target_recording = primary.recording
    _replace_item(source_recording.tracks, duplicate, primary)
    if target_recording is not source_recording:
        _ensure_item(target_recording.tracks, primary)
    duplicate.recording = target_recording

    for play_event in list(duplicate.play_events):
        play_event.track = primary
        _ensure_item(primary.play_events, play_event)
    duplicate.play_events.clear()


# --- Shared merge helpers ----------------------------------------------------


def _merge_scalar_attributes(
    primary: CanonicalEntity,
    duplicate: CanonicalEntity,
    attributes: tuple[str, ...],
) -> None:
    for attribute in attributes:
        if getattr(primary, attribute) is None:
            value = getattr(duplicate, attribute)
            if value is not None:
                setattr(primary, attribute, value)


def _merge_sources(primary: CanonicalEntity, duplicate: CanonicalEntity) -> None:
    primary.sources.update(duplicate.sources)


def _merge_external_ids(primary: CanonicalEntity, duplicate: CanonicalEntity) -> None:
    existing = {(external_id.namespace, external_id.value) for external_id in primary.external_ids}
    for external_id in duplicate.external_ids:
        key = (external_id.namespace, external_id.value)
        if key not in existing:
            primary.external_ids.append(external_id)
            existing.add(key)


def _ensure_item[T](sequence: list[T], item: T) -> None:
    if any(existing is item for existing in sequence):
        return
    sequence.append(item)


def _replace_item[T](sequence: list[T], old: T, new: T | None) -> None:
    for index, current in enumerate(sequence):
        if current is old:
            if new is None:
                sequence.pop(index)
            else:
                sequence[index] = new
            return


# --- Registry ---------------------------------------------------------------


@dataclass(slots=True)
class EntityOps[TEntity: CanonicalEntity, TData: NormalizationData[Any]]:
    data_type: type[TData]
    normalize: Callable[[TEntity, NormalizationState], TData]
    merge: Callable[[TEntity, TEntity], None]
    rewire: Callable[[TEntity, TEntity], None]


_REGISTRY: dict[CanonicalEntityType, EntityOps[Any, Any]] = {
    CanonicalEntityType.ARTIST: EntityOps(
        data_type=ArtistNormalizationData,
        normalize=normalize_artist,
        merge=merge_artist,
        rewire=rewire_artist,
    ),
    CanonicalEntityType.RELEASE_SET: EntityOps(
        data_type=ReleaseSetNormalizationData,
        normalize=normalize_release_set,
        merge=merge_release_set,
        rewire=rewire_release_set,
    ),
    CanonicalEntityType.RELEASE: EntityOps(
        data_type=ReleaseNormalizationData,
        normalize=normalize_release,
        merge=merge_release,
        rewire=rewire_release,
    ),
    CanonicalEntityType.RECORDING: EntityOps(
        data_type=RecordingNormalizationData,
        normalize=normalize_recording,
        merge=merge_recording,
        rewire=rewire_recording,
    ),
    CanonicalEntityType.TRACK: EntityOps(
        data_type=TrackNormalizationData,
        normalize=normalize_track,
        merge=merge_track,
        rewire=rewire_track,
    ),
}


def ops_for(entity: CanonicalEntity) -> EntityOps[Any, Any]:
    try:
        return _REGISTRY[entity.entity_type]
    except KeyError as exc:
        raise RuntimeError(f"No ops registered for {entity.entity_type}") from exc
