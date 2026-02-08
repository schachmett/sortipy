"""Apply update DTOs to domain entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import (
    Artist,
    ExternalNamespace,
    Label,
    Recording,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.domain.model import (
        Release,
        ReleaseSet,
    )
    from sortipy.domain.model.associations import (
        RecordingContribution,
        ReleaseSetContribution,
        ReleaseTrack,
    )
    from sortipy.domain.model.external_ids import ExternallyIdentifiable

    from .dto import (
        ArtistUpdate,
        ContributionUpdate,
        ExternalIdUpdate,
        LabelUpdate,
        RecordingUpdate,
        ReleaseSetUpdate,
        ReleaseTrackUpdate,
        ReleaseUpdate,
    )


def apply_release_update(release: Release, update: ReleaseUpdate) -> Release:
    """Apply a release update graph to the domain model."""

    _apply_release_fields(release, update)
    if update.release_set is not None:
        _apply_release_set_update(release.release_set, update.release_set)
    for track_update in update.release_tracks:
        _apply_release_track_update(release, track_update)
    for label_update in update.labels:
        _apply_label_update(release, label_update)
    return release


def _apply_release_fields(release: Release, update: ReleaseUpdate) -> None:
    if update.title:
        release.title = update.title
    if update.release_date is not None:
        release.release_date = update.release_date
    if update.country is not None:
        release.country = update.country
    if update.status is not None:
        release.status = update.status
    if update.packaging is not None:
        release.packaging = update.packaging
    if update.media_formats and release.format is None:
        release.format = update.media_formats[0]
    if update.metadata.source:
        release.add_source(update.metadata.source)
    _apply_external_ids(release, update.external_ids)


def _apply_release_set_update(release_set: ReleaseSet, update: ReleaseSetUpdate) -> None:
    if update.title:
        release_set.title = update.title
    if update.primary_type is not None:
        release_set.primary_type = update.primary_type
    if update.secondary_types:
        release_set.secondary_types = list(update.secondary_types)
    if update.first_release_date is not None:
        release_set.first_release = update.first_release_date
    if update.aliases:
        release_set.aliases = _merge_list(release_set.aliases, update.aliases)
    if update.metadata.source:
        release_set.add_source(update.metadata.source)
    _apply_external_ids(release_set, update.external_ids)
    for contribution in update.contributions:
        _apply_release_set_contribution(release_set, contribution)


def _apply_release_track_update(release: Release, update: ReleaseTrackUpdate) -> None:
    recording = _resolve_recording(release, update.recording)
    if recording is None:
        recording = Recording(title=update.recording.title)
    _apply_recording_update(recording, update.recording)

    existing = _find_release_track(release, recording, update)
    if existing is None:
        release.add_track(
            recording,
            disc_number=update.disc_number,
            track_number=update.track_number,
            title_override=update.title_override,
            duration_ms=update.duration_ms,
        )
    else:
        if update.disc_number is not None:
            existing.disc_number = update.disc_number
        if update.track_number is not None:
            existing.track_number = update.track_number
        if update.title_override is not None:
            existing.title_override = update.title_override
        if update.duration_ms is not None:
            existing.duration_ms = update.duration_ms


def _apply_recording_update(recording: Recording, update: RecordingUpdate) -> None:
    if update.title:
        recording.title = update.title
    if update.disambiguation is not None:
        recording.disambiguation = update.disambiguation
    if update.duration_ms is not None:
        recording.duration_ms = update.duration_ms
    if update.aliases:
        recording.aliases = _merge_list(recording.aliases, update.aliases)
    if update.metadata.source:
        recording.add_source(update.metadata.source)
    _apply_external_ids(recording, update.external_ids)
    for contribution in update.contributions:
        _apply_recording_contribution(recording, contribution)


def _apply_recording_contribution(
    recording: Recording,
    update: ContributionUpdate,
) -> None:
    artist = _resolve_artist(recording.artists, update.artist)
    if artist is None:
        artist = Artist(name=update.artist.name)
        _apply_artist_update(artist, update.artist)
    contribution = _find_contribution(recording, artist, update)
    if contribution is None:
        contribution = recording.add_artist(
            artist,
            role=update.role,
            credit_order=update.credit_order,
            credited_as=update.credited_as,
            join_phrase=update.join_phrase,
        )
    contribution.role = update.role
    contribution.credit_order = update.credit_order
    contribution.credited_as = update.credited_as
    contribution.join_phrase = update.join_phrase


def _apply_release_set_contribution(
    release_set: ReleaseSet,
    update: ContributionUpdate,
) -> None:
    artist = _resolve_artist(release_set.artists, update.artist)
    if artist is None:
        artist = Artist(name=update.artist.name)
        _apply_artist_update(artist, update.artist)
    contribution = _find_release_set_contribution(release_set, artist, update)
    if contribution is None:
        contribution = release_set.add_artist(
            artist,
            role=update.role,
            credit_order=update.credit_order,
            credited_as=update.credited_as,
            join_phrase=update.join_phrase,
        )
    contribution.role = update.role
    contribution.credit_order = update.credit_order
    contribution.credited_as = update.credited_as
    contribution.join_phrase = update.join_phrase


def _apply_artist_update(artist: Artist, update: ArtistUpdate) -> None:
    if update.name:
        artist.name = update.name
    if update.sort_name is not None:
        artist.sort_name = update.sort_name
    if update.country is not None:
        artist.country = update.country
    if update.kind is not None:
        artist.kind = update.kind
    if update.aliases:
        artist.aliases = _merge_list(artist.aliases, update.aliases)
    if update.life_span is not None:
        artist.life_span = update.life_span
    if update.areas:
        artist.areas = list(update.areas)
    if update.metadata.source:
        artist.add_source(update.metadata.source)
    _apply_external_ids(artist, update.external_ids)


def _apply_label_update(release: Release, update: LabelUpdate) -> None:
    label = _resolve_label(release.labels, update)
    if label is None:
        name = update.name or "Unknown"
        label = Label(name=name)
        _apply_external_ids(label, update.external_ids)
        release.add_label(label)
    else:
        if update.name:
            label.name = update.name
        _apply_external_ids(label, update.external_ids)


def _apply_external_ids(
    entity: ExternallyIdentifiable, external_ids: list[ExternalIdUpdate]
) -> None:
    for ext in external_ids:
        old_id = entity.external_ids_by_namespace.get(ext.namespace)
        if old_id is not None:
            if old_id.value != ext.value:
                raise ValueError(f"External ID conflict for {ext.namespace}!")
            continue
        entity.add_external_id(ext.namespace, ext.value, replace=False)


def _resolve_recording(
    release: Release,
    update: RecordingUpdate,
) -> Recording | None:
    # TODO(enrichment): consider fallback matching when MBID is missing.
    # Ideas:
    # - Match by ISRC if available (ExternalNamespace.RECORDING_ISRC).
    # - Match by title + duration (+ primary artist name).
    # - Delegate matching to ingest pipeline dedup/canonicalization instead of ad-hoc logic.
    mbid = _external_id_value(update.external_ids, ExternalNamespace.MUSICBRAINZ_RECORDING)
    if mbid is None:
        return None
    for recording in release.recordings:
        existing = recording.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_RECORDING)
        if existing and existing.value == mbid:
            return recording
    return None


def _resolve_artist(
    artists: Iterable[Artist],
    update: ArtistUpdate,
) -> Artist | None:
    mbid = _external_id_value(update.external_ids, ExternalNamespace.MUSICBRAINZ_ARTIST)
    if mbid is not None:
        for artist in artists:
            existing = artist.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_ARTIST)
            if existing and existing.value == mbid:
                return artist
    for artist in artists:
        if artist.name == update.name:
            return artist
    return None


def _resolve_label(
    labels: Iterable[Label],
    update: LabelUpdate,
) -> Label | None:
    mbid = _external_id_value(update.external_ids, ExternalNamespace.MUSICBRAINZ_LABEL)
    if mbid is not None:
        for label in labels:
            existing = label.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_LABEL)
            if existing and existing.value == mbid:
                return label
    if update.name is None:
        return None
    for label in labels:
        if label.name == update.name:
            return label
    return None


def _find_contribution(
    recording: Recording,
    artist: Artist,
    update: ContributionUpdate,
) -> RecordingContribution | None:
    # TODO(enrichment): relax matching when credit_order is missing/unknown.
    # Ideas:
    # - If credit_order is None, match by artist + role + credited_as/join_phrase.
    # - If only one contribution exists for the artist, reuse it.
    # - Or delegate to ingest pipeline dedup logic.
    for contribution in recording.contributions:
        if contribution.artist is artist and contribution.credit_order == update.credit_order:
            return contribution
    return None


def _find_release_set_contribution(
    release_set: ReleaseSet,
    artist: Artist,
    update: ContributionUpdate,
) -> ReleaseSetContribution | None:
    # TODO(enrichment): relax matching when credit_order is missing/unknown.
    # Ideas:
    # - If credit_order is None, match by artist + role + credited_as/join_phrase.
    # - If only one contribution exists for the artist, reuse it.
    # - Or delegate to ingest pipeline dedup logic.
    for contribution in release_set.contributions:
        if contribution.artist is artist and contribution.credit_order == update.credit_order:
            return contribution
    return None


def _find_release_track(
    release: Release,
    recording: Recording,
    update: ReleaseTrackUpdate,
) -> ReleaseTrack | None:
    # TODO(enrichment): when disc/track numbers are missing, consider extra signals.
    # Ideas:
    # - Match by title_override or duration.
    # - If multiple tracks point to same recording, prefer exact disc/track match.
    # - Or let ingest pipeline reconcile duplicates after enrichment.
    for track in release.tracks:
        if track.recording is not recording:
            continue
        if update.disc_number is not None and track.disc_number != update.disc_number:
            continue
        if update.track_number is not None and track.track_number != update.track_number:
            continue
        return track
    return None


def _external_id_value(
    external_ids: list[ExternalIdUpdate],
    namespace: ExternalNamespace,
) -> str | None:
    for ext in external_ids:
        if ext.namespace == namespace:
            return ext.value
    return None


def _merge_list(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for value in incoming:
        if value not in merged:
            merged.append(value)
    return merged
