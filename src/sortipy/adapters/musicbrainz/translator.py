"""Translate MusicBrainz payloads into enrichment updates."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sortipy.domain.entity_updates import (
    ArtistUpdate,
    ContributionUpdate,
    EnrichmentMetadata,
    ExternalIdUpdate,
    LabelUpdate,
    RecordingUpdate,
    ReleaseCandidate,
    ReleaseSetUpdate,
    ReleaseTrackUpdate,
    ReleaseUpdate,
)
from sortipy.domain.model import (
    Area,
    AreaRole,
    AreaType,
    ArtistKind,
    ArtistRole,
    ExternalNamespace,
    LifeSpan,
    PartialDate,
    Provider,
    ReleasePackaging,
    ReleaseSetSecondaryType,
    ReleaseSetType,
    ReleaseStatus,
)

from .schema import MBReleaseGroupPrimaryType, MBReleaseGroupSecondaryType, MBReleaseStatus

_ARTIST_KIND_MAP: dict[str, ArtistKind] = {
    "person": ArtistKind.PERSON,
    "group": ArtistKind.GROUP,
    "orchestra": ArtistKind.ORCHESTRA,
    "choir": ArtistKind.CHOIR,
    "other": ArtistKind.OTHER,
}

_AREA_TYPE_MAP: dict[str, AreaType] = {
    "country": AreaType.COUNTRY,
    "subdivision": AreaType.SUBDIVISION,
    "city": AreaType.CITY,
    "district": AreaType.DISTRICT,
    "island": AreaType.ISLAND,
    "county": AreaType.COUNTY,
    "municipality": AreaType.MUNICIPALITY,
    "region": AreaType.REGION,
    "province": AreaType.PROVINCE,
    "state": AreaType.STATE,
}

_RELEASE_SET_TYPE_MAP: dict[MBReleaseGroupPrimaryType, ReleaseSetType] = {
    MBReleaseGroupPrimaryType.ALBUM: ReleaseSetType.ALBUM,
    MBReleaseGroupPrimaryType.SINGLE: ReleaseSetType.SINGLE,
    MBReleaseGroupPrimaryType.EP: ReleaseSetType.EP,
    MBReleaseGroupPrimaryType.BROADCAST: ReleaseSetType.BROADCAST,
    MBReleaseGroupPrimaryType.OTHER: ReleaseSetType.OTHER,
}

_RELEASE_SET_SECONDARY_MAP: dict[MBReleaseGroupSecondaryType, ReleaseSetSecondaryType] = {
    MBReleaseGroupSecondaryType.COMPILATION: ReleaseSetSecondaryType.COMPILATION,
    MBReleaseGroupSecondaryType.SOUNDTRACK: ReleaseSetSecondaryType.SOUNDTRACK,
    MBReleaseGroupSecondaryType.SPOKENWORD: ReleaseSetSecondaryType.SPOKENWORD,
    MBReleaseGroupSecondaryType.INTERVIEW: ReleaseSetSecondaryType.INTERVIEW,
    MBReleaseGroupSecondaryType.AUDIOBOOK: ReleaseSetSecondaryType.AUDIOBOOK,
    MBReleaseGroupSecondaryType.AUDIO_DRAMA: ReleaseSetSecondaryType.AUDIO_DRAMA,
    MBReleaseGroupSecondaryType.LIVE: ReleaseSetSecondaryType.LIVE,
    MBReleaseGroupSecondaryType.REMIX: ReleaseSetSecondaryType.REMIX,
    MBReleaseGroupSecondaryType.DJMIX: ReleaseSetSecondaryType.DJMIX,
    MBReleaseGroupSecondaryType.MIXTAPE: ReleaseSetSecondaryType.MIXTAPE,
    MBReleaseGroupSecondaryType.DEMO: ReleaseSetSecondaryType.DEMO,
    MBReleaseGroupSecondaryType.FIELD_RECORDING: ReleaseSetSecondaryType.FIELD_RECORDING,
}

_RELEASE_STATUS_MAP: dict[MBReleaseStatus, ReleaseStatus] = {
    MBReleaseStatus.OFFICIAL: ReleaseStatus.OFFICIAL,
    MBReleaseStatus.PROMOTION: ReleaseStatus.PROMOTION,
    MBReleaseStatus.BOOTLEG: ReleaseStatus.BOOTLEG,
    MBReleaseStatus.PSEUDO_RELEASE: ReleaseStatus.PSEUDO_RELEASE,
    MBReleaseStatus.WITHDRAWN: ReleaseStatus.WITHDRAWN,
    MBReleaseStatus.EXPUNGED: ReleaseStatus.EXPUNGED,
    MBReleaseStatus.CANCELLED: ReleaseStatus.CANCELLED,
}

_RELEASE_PACKAGING_MAP: dict[str, ReleasePackaging] = {
    "none": ReleasePackaging.NONE,
    "jewel case": ReleasePackaging.JEWEL_CASE,
    "digipak": ReleasePackaging.DIGIPAK,
    "gatefold cover": ReleasePackaging.GATEFOLD,
    "cardboard/paper sleeve": ReleasePackaging.CARDBOARD_PAPER_SLEEVE,
}

if TYPE_CHECKING:
    from .schema import (
        MBArtistCredit,
        MBLabelInfo,
        MBRecording,
        MBRelation,
        MBRelease,
        MBReleaseGroup,
        MBReleaseRef,
        MusicBrainzAlias,
        MusicBrainzArtist,
    )


def translate_recording(
    recording: MBRecording,
) -> ReleaseUpdate:
    artist_cache: dict[str, ArtistUpdate] = {}
    release = _select_release(recording)
    release_group = _select_release_group(release, recording)
    release_set_update = (
        _release_group_update(release_group, artist_cache) if release_group else None
    )
    recording_update = _recording_update(recording, artist_cache)
    release_tracks = _release_tracks_for_recording(release, recording_update)
    return _release_update(
        release=release,
        release_set=release_set_update,
        recording_update=recording_update,
        release_tracks=release_tracks,
    )


def translate_release(release: MBRelease) -> ReleaseUpdate:
    artist_cache: dict[str, ArtistUpdate] = {}
    release_set_update = (
        _release_group_update(release.release_group, artist_cache)
        if release.release_group
        else None
    )
    release_tracks = _release_tracks_from_release(release, artist_cache)
    return _release_update_from_release(
        release=release,
        release_set=release_set_update,
        release_tracks=release_tracks,
    )


def _metadata() -> EnrichmentMetadata:
    return EnrichmentMetadata(source=Provider.MUSICBRAINZ, confidence=1.0)


def _recording_update(
    recording: MBRecording,
    artist_cache: dict[str, ArtistUpdate],
) -> RecordingUpdate:
    return RecordingUpdate(
        metadata=_metadata(),
        title=recording.title,
        external_ids=_recording_external_ids(recording),
        disambiguation=recording.disambiguation or None,
        duration_ms=recording.length,
        aliases=_alias_names(recording.aliases),
        contributions=_build_contributions(recording.artist_credit, artist_cache),
    )


def _build_contributions(
    credits_: list[MBArtistCredit],
    artist_cache: dict[str, ArtistUpdate],
) -> list[ContributionUpdate]:
    updates: list[ContributionUpdate] = []
    prev_join: str | None = None

    for index, credit in enumerate(credits_):
        role = _role_for_credit(index=index, prev_join_phrase=prev_join)
        updates.append(
            ContributionUpdate(
                artist=_artist_update(credit.artist, artist_cache),
                role=role,
                credit_order=index,
                credited_as=_credited_as(credit),
                join_phrase=credit.join_phrase,
            )
        )
        prev_join = credit.join_phrase

    return updates


def _release_group_update(
    group: MBReleaseGroup,
    artist_cache: dict[str, ArtistUpdate],
) -> ReleaseSetUpdate:
    return ReleaseSetUpdate(
        metadata=_metadata(),
        external_ids=_release_group_external_ids(group),
        title=group.title,
        disambiguation=group.disambiguation or None,
        primary_type=_release_set_type(group.primary_type),
        secondary_types=_release_set_secondary_types(group.secondary_types),
        first_release_date=_parse_partial_date(group.first_release_date),
        aliases=_alias_names(group.aliases),
        contributions=_build_contributions(group.artist_credit, artist_cache),
    )


def _role_for_credit(*, index: int, prev_join_phrase: str | None) -> ArtistRole:
    if index == 0:
        return ArtistRole.PRIMARY
    if _is_featuring(prev_join_phrase):
        return ArtistRole.FEATURED
    return ArtistRole.UNKNOWN


def _credited_as(credit: MBArtistCredit) -> str | None:
    if credit.name and credit.name != credit.artist.name:
        return credit.name
    return None


def _is_featuring(join_phrase: str | None) -> bool:
    if join_phrase is None:
        return False
    lowered = join_phrase.lower()
    return "feat" in lowered or "ft." in lowered


def _alias_names(aliases: list[MusicBrainzAlias]) -> list[str]:
    return [alias.name for alias in aliases]


def _artist_update(
    artist: MusicBrainzArtist,
    artist_cache: dict[str, ArtistUpdate],
) -> ArtistUpdate:
    cached = artist_cache.get(artist.id)
    if cached is not None:
        return cached
    update = ArtistUpdate(
        metadata=_metadata(),
        name=artist.name,
        external_ids=_artist_external_ids(artist),
        sort_name=artist.sort_name,
        disambiguation=artist.disambiguation or None,
        country=artist.country,
        kind=_artist_kind(artist.type),
        aliases=_alias_names(artist.aliases),
        life_span=_life_span(artist.life_span),
        areas=_areas_for_artist(artist),
    )
    artist_cache[artist.id] = update
    return update


def _artist_external_ids(artist: MusicBrainzArtist) -> list[ExternalIdUpdate]:
    ids = [
        ExternalIdUpdate(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST,
            value=artist.id,
        )
    ]
    ids.extend(
        ExternalIdUpdate(namespace="artist:ipi", value=ipi) for ipi in getattr(artist, "ipis", [])
    )
    ids.extend(
        ExternalIdUpdate(namespace="artist:isni", value=isni)
        for isni in getattr(artist, "isnis", [])
    )
    ids.extend(_urls_as_external_ids(getattr(artist, "relations", [])))
    return ids


def _recording_external_ids(recording: MBRecording) -> list[ExternalIdUpdate]:
    ids = [
        ExternalIdUpdate(
            namespace=ExternalNamespace.MUSICBRAINZ_RECORDING,
            value=recording.id,
        )
    ]
    ids.extend(
        ExternalIdUpdate(namespace=ExternalNamespace.RECORDING_ISRC, value=isrc)
        for isrc in recording.isrcs
    )
    ids.extend(_urls_as_external_ids(recording.relations))
    return ids


def _recording_external_ids_from_mbid(mbid: str) -> list[ExternalIdUpdate]:
    return [
        ExternalIdUpdate(
            namespace=ExternalNamespace.MUSICBRAINZ_RECORDING,
            value=mbid,
        )
    ]


def _release_group_external_ids(group: MBReleaseGroup) -> list[ExternalIdUpdate]:
    ids = [
        ExternalIdUpdate(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
            value=group.id,
        )
    ]
    ids.extend(_urls_as_external_ids(group.relations))
    return ids


def _urls_as_external_ids(relations: list[MBRelation]) -> list[ExternalIdUpdate]:
    ids: list[ExternalIdUpdate] = []
    for relation in relations:
        if relation.url is None:
            continue
        url = relation.url.resource
        namespace = f"url:{relation.type.replace(' ', '-')}:{urlparse(url).netloc}"
        ids.append(ExternalIdUpdate(namespace, value=url))
    return ids


def _artist_kind(raw: str | None) -> ArtistKind | None:
    if raw is None:
        return None
    normalized = raw.strip().lower()
    return _ARTIST_KIND_MAP.get(normalized)


def _area_type(raw: str | None) -> AreaType | None:
    if raw is None:
        return None
    normalized = raw.strip().lower()
    return _AREA_TYPE_MAP.get(normalized, AreaType.OTHER)


def _areas_for_artist(artist: MusicBrainzArtist) -> list[Area]:
    areas: list[Area] = []
    if artist.area is not None:
        areas.append(_area_from_mb(artist.area, AreaRole.PRIMARY))
    if artist.begin_area is not None:
        areas.append(_area_from_mb(artist.begin_area, AreaRole.BEGIN))
    if artist.end_area is not None:
        areas.append(_area_from_mb(artist.end_area, AreaRole.END))
    return areas


def _area_from_mb(area: object, role: AreaRole) -> Area:
    return Area(
        name=getattr(area, "name", ""),
        area_type=_area_type(getattr(area, "type", None)),
        role=role,
        country_codes=tuple(getattr(area, "iso_3166_1_codes", []) or ()),
    )


def _life_span(life_span: object | None) -> LifeSpan | None:
    if life_span is None:
        return None
    return LifeSpan(
        begin=_parse_partial_date(getattr(life_span, "begin", None)),
        end=_parse_partial_date(getattr(life_span, "end", None)),
        ended=getattr(life_span, "ended", None),
    )


def _release_set_type(raw: MBReleaseGroupPrimaryType | None) -> ReleaseSetType | None:
    if raw is None:
        return None
    return _RELEASE_SET_TYPE_MAP.get(raw, ReleaseSetType.OTHER)


def _release_set_secondary_types(
    raw_values: list[MBReleaseGroupSecondaryType],
) -> list[ReleaseSetSecondaryType]:
    resolved: list[ReleaseSetSecondaryType] = []
    for value in raw_values:
        enum_value = _RELEASE_SET_SECONDARY_MAP.get(value)
        if enum_value is not None:
            resolved.append(enum_value)
    return resolved


def _parse_partial_date(raw: str | None) -> PartialDate | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    parts = text.split("-")
    try:
        year = int(parts[0]) if parts[0] else None
    except ValueError:
        return None
    if year is None:
        return None
    month = None
    day = None
    if len(parts) > 1 and parts[1]:
        try:
            month = int(parts[1])
        except ValueError:
            month = None
    if len(parts) > 2 and parts[2]:  # noqa: PLR2004
        try:
            day = int(parts[2])
        except ValueError:
            day = None
    return PartialDate(year=year, month=month, day=day)


def _release_status(raw: MBReleaseStatus | None) -> ReleaseStatus | None:
    if raw is None:
        return None
    return _RELEASE_STATUS_MAP.get(raw)


def _release_packaging(raw: str | None) -> ReleasePackaging | None:
    if raw is None:
        return None
    text = raw
    normalized = text.strip().lower()
    if not normalized:
        return None
    return _RELEASE_PACKAGING_MAP.get(normalized, ReleasePackaging.OTHER)


def _select_release(recording: MBRecording) -> MBRelease | None:
    if not recording.releases:
        return None
    return recording.releases[0]


def _select_release_group(
    release: MBRelease | None,
    recording: MBRecording,
) -> MBReleaseGroup | None:
    if release is not None and release.release_group is not None:
        return release.release_group
    if recording.release_groups:
        return recording.release_groups[0]
    return None


def _release_tracks_for_recording(
    release: MBRelease | None,
    recording_update: RecordingUpdate,
) -> list[ReleaseTrackUpdate]:
    if release is None:
        return [ReleaseTrackUpdate(recording=recording_update)]
    recording_mbid = _recording_mbid_from_update(recording_update)
    if recording_mbid is None:
        return [ReleaseTrackUpdate(recording=recording_update)]
    for medium in release.media:
        for track in medium.tracks:
            recording = track.recording
            if recording is None:
                continue
            if recording.id != recording_mbid:
                continue
            title_override = track.title if track.title != recording_update.title else None
            return [
                ReleaseTrackUpdate(
                    recording=recording_update,
                    disc_number=medium.position,
                    track_number=track.position,
                    title_override=title_override,
                    duration_ms=track.length,
                )
            ]
    return [ReleaseTrackUpdate(recording=recording_update)]


def _release_tracks_from_release(
    release: MBRelease,
    artist_cache: dict[str, ArtistUpdate],
) -> list[ReleaseTrackUpdate]:
    tracks: list[ReleaseTrackUpdate] = []
    recording_updates: dict[str, RecordingUpdate] = {}
    for medium in release.media:
        for track in medium.tracks:
            recording = track.recording
            if recording is None:
                continue
            recording_update = recording_updates.get(recording.id)
            if recording_update is None:
                credits_ = track.artist_credit or release.artist_credit
                recording_update = RecordingUpdate(
                    metadata=_metadata(),
                    title=recording.title,
                    external_ids=_recording_external_ids_from_mbid(recording.id),
                    disambiguation=recording.disambiguation or None,
                    duration_ms=track.length or recording.length,
                    contributions=_build_contributions(credits_, artist_cache),
                )
                recording_updates[recording.id] = recording_update
            title_override = (
                track.title if track.title and track.title != recording_update.title else None
            )
            tracks.append(
                ReleaseTrackUpdate(
                    recording=recording_update,
                    disc_number=medium.position,
                    track_number=track.position,
                    title_override=title_override,
                    duration_ms=track.length,
                )
            )
    return tracks


def _recording_mbid_from_update(update: RecordingUpdate) -> str | None:
    for entry in update.external_ids:
        if entry.namespace == ExternalNamespace.MUSICBRAINZ_RECORDING:
            return entry.value
    return None


def _release_update(
    *,
    release: MBRelease | None,
    release_set: ReleaseSetUpdate | None,
    recording_update: RecordingUpdate,
    release_tracks: list[ReleaseTrackUpdate],
) -> ReleaseUpdate:
    if release is None:
        return ReleaseUpdate(
            metadata=_metadata(),
            title=recording_update.title,
            release_set=release_set,
            release_tracks=release_tracks,
        )
    return _release_update_from_release(
        release=release,
        release_set=release_set,
        release_tracks=release_tracks,
    )


def _release_update_from_release(
    *,
    release: MBRelease,
    release_set: ReleaseSetUpdate | None,
    release_tracks: list[ReleaseTrackUpdate],
) -> ReleaseUpdate:
    text_representation = release.text_representation
    return ReleaseUpdate(
        metadata=_metadata(),
        title=release.title,
        external_ids=_release_external_ids(release),
        disambiguation=release.disambiguation or None,
        release_date=_parse_partial_date(release.date),
        country=release.country,
        status=_release_status(release.status),
        packaging=_release_packaging(release.packaging),
        text_language=text_representation.language if text_representation else None,
        text_script=text_representation.script if text_representation else None,
        release_set=release_set,
        release_tracks=release_tracks,
        labels=_label_updates(release.label_info),
        track_count=_release_track_count(release),
        media_formats=_release_media_formats(release),
    )


def release_candidate_from_release(release: MBRelease) -> ReleaseCandidate:
    artist_names = [credit.artist.name for credit in release.artist_credit]
    release_set_mbid = release.release_group.id if release.release_group is not None else None
    return ReleaseCandidate(
        mbid=release.id,
        title=release.title,
        release_date=_parse_partial_date(release.date),
        status=_release_status(release.status),
        packaging=_release_packaging(release.packaging),
        country=release.country,
        release_set_mbid=release_set_mbid,
        artist_names=artist_names,
        track_count=_release_track_count(release),
        media_formats=_release_media_formats(release),
    )


def release_candidate_from_release_ref(release: MBReleaseRef) -> ReleaseCandidate:
    return ReleaseCandidate(
        mbid=release.id,
        title=release.title,
        release_date=_parse_partial_date(release.date),
        status=_release_status(release.status),
        packaging=_release_packaging(release.packaging),
        country=release.country,
        release_set_mbid=None,
        artist_names=[],
        track_count=None,
        media_formats=[],
    )


def _release_external_ids(release: MBRelease) -> list[ExternalIdUpdate]:
    ids = [
        ExternalIdUpdate(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE,
            value=release.id,
        )
    ]
    if release.barcode:
        ids.extend(_barcode_external_ids(release.barcode))
    ids.extend(_urls_as_external_ids(release.relations))
    return ids


_BARCODE_LENGTH_UPC = 12
_BARCODE_LENGTH_EAN = 13


def _barcode_external_ids(barcode: str) -> list[ExternalIdUpdate]:
    value = barcode.strip()
    if not value:
        return []
    if value.isdigit():
        if len(value) == _BARCODE_LENGTH_UPC:
            namespace = ExternalNamespace.RELEASE_UPC
        elif len(value) == _BARCODE_LENGTH_EAN:
            namespace = ExternalNamespace.RELEASE_EAN
        else:
            namespace = "release:barcode"
    else:
        namespace = "release:barcode"
    return [ExternalIdUpdate(namespace=namespace, value=value)]


def _label_updates(label_infos: list[MBLabelInfo]) -> list[LabelUpdate]:
    updates: list[LabelUpdate] = []
    for info in label_infos:
        label = getattr(info, "label", None)
        external_ids: list[ExternalIdUpdate] = []
        name = None
        if label is not None:
            name = getattr(label, "name", None)
            label_id = getattr(label, "id", None)
            if label_id:
                external_ids.append(
                    ExternalIdUpdate(
                        namespace=ExternalNamespace.MUSICBRAINZ_LABEL,
                        value=label_id,
                    )
                )
            external_ids.extend(_urls_as_external_ids(getattr(label, "relations", [])))
        updates.append(
            LabelUpdate(
                name=name,
                catalog_number=getattr(info, "catalog_number", None),
                external_ids=external_ids,
            )
        )
    return updates


def _release_track_count(release: MBRelease) -> int | None:
    if release.track_count is not None:
        return release.track_count
    counts = [medium.track_count for medium in release.media if medium.track_count]
    if not counts:
        return None
    return sum(counts)


def _release_media_formats(release: MBRelease) -> list[str]:
    formats = [medium.format for medium in release.media if medium.format]
    seen: set[str] = set()
    unique: list[str] = []
    for value in formats:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
