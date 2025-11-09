"""Helpers for aligning ingested entities with canonical catalog entries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.types import (
    Artist,
    CanonicalEntity,
    Namespace,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    Track,
)

if TYPE_CHECKING:
    from sortipy.domain.ports.persistence import CanonicalEntityRepository
    from sortipy.domain.ports.unit_of_work import PlayEventRepositories


def canonicalize_artist(artist: Artist, repositories: PlayEventRepositories) -> Artist:
    existing = _existing_entity(artist, repositories.artists)
    if existing is not None:
        # NOTE: future merge pipeline will reconcile artist metadata differences here.
        return existing
    return artist


def canonicalize_release_set(
    release_set: ReleaseSet,
    repositories: PlayEventRepositories,
) -> ReleaseSet:
    existing = _existing_entity(release_set, repositories.release_sets)
    if existing is not None:
        # NOTE: merge pipeline will reconcile artist lists and release-set metadata here.
        return existing

    for link in release_set.artists:
        link.artist = canonicalize_artist(link.artist, repositories)
    return release_set


def canonicalize_release(release: Release, repositories: PlayEventRepositories) -> Release:
    existing = _existing_entity(release, repositories.releases)
    if existing is not None:
        # NOTE: merge pipeline will reconcile release metadata (formats, dates, etc.).
        return existing

    release.release_set = canonicalize_release_set(release.release_set, repositories)
    return release


def canonicalize_recording(
    recording: Recording,
    repositories: PlayEventRepositories,
) -> Recording:
    existing = _existing_entity(recording, repositories.recordings)
    if existing is not None:
        # NOTE: merge pipeline will reconcile recording credits/durations when needed.
        return existing

    for link in recording.artists:
        link.artist = canonicalize_artist(link.artist, repositories)
    return recording


def canonicalize_track(track: Track, repositories: PlayEventRepositories) -> Track:
    existing = _existing_entity(track, repositories.tracks)
    if existing is not None:
        # NOTE: merge pipeline will reconcile track numbering/override metadata here.
        return existing

    track.release = canonicalize_release(track.release, repositories)
    track.recording = canonicalize_recording(track.recording, repositories)
    reused = _existing_track_on_release(track)
    if reused is not None:
        # NOTE: merge pipeline will reconcile per-track overrides when differences exist.
        return reused
    return track


def canonicalize_play_event(
    event: PlayEvent,
    repositories: PlayEventRepositories,
) -> PlayEvent:
    if event.track is not None:
        event.track = canonicalize_track(event.track, repositories)
        event.recording = event.track.recording
    else:
        event.recording = canonicalize_recording(event.recording, repositories)
    return event


def _existing_entity[TCanonical: CanonicalEntity](
    entity: TCanonical,
    repository: CanonicalEntityRepository[TCanonical],
) -> TCanonical | None:
    existing = _lookup_by_external_ids(entity, repository)
    if existing is not None:
        _merge_external_ids(entity, existing)
    return existing


def _lookup_by_external_ids[TCanonical: CanonicalEntity](
    entity: TCanonical,
    repository: CanonicalEntityRepository[TCanonical],
) -> TCanonical | None:
    for external_id in entity.external_ids:
        existing = repository.get_by_external_id(external_id.namespace, external_id.value)
        if existing is not None:
            return existing
    return None


def _merge_external_ids(source: CanonicalEntity, target: CanonicalEntity) -> None:
    existing_keys: set[tuple[Namespace, str]] = {
        (external_id.namespace, external_id.value) for external_id in target.external_ids
    }
    for external_id in source.external_ids:
        key = (external_id.namespace, external_id.value)
        if key not in existing_keys:
            target.external_ids.append(external_id)
            existing_keys.add(key)


def _existing_track_on_release(track: Track) -> Track | None:
    release = track.release
    for candidate in release.tracks:
        if _same_recording(candidate, track) and _similar_track_position(candidate, track):
            return candidate
    return None


def _same_recording(candidate: Track, track: Track) -> bool:
    recording_identity = track.recording.identity
    candidate_identity = candidate.recording.identity
    if recording_identity is not None and candidate_identity is not None:
        return candidate_identity == recording_identity
    return candidate.recording.title == track.recording.title


def _similar_track_position(candidate: Track, track: Track) -> bool:
    candidate_position = (candidate.disc_number, candidate.track_number)
    track_position = (track.disc_number, track.track_number)
    if candidate_position == track_position and candidate_position != (None, None):
        return True
    title_a = candidate.title_override or candidate.recording.title
    title_b = track.title_override or track.recording.title
    return title_a == title_b
