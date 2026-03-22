"""Translate MusicBrainz payloads into fresh domain aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from sortipy.domain.model import (
    Area,
    AreaRole,
    AreaType,
    Artist,
    ArtistKind,
    ArtistRole,
    ExternalNamespace,
    Label,
    LifeSpan,
    PartialDate,
    Provider,
    Recording,
    ReleasePackaging,
    ReleaseSet,
    ReleaseSetSecondaryType,
    ReleaseSetType,
    ReleaseStatus,
)
from sortipy.domain.ports.enrichment import ReleaseCandidate

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
    from collections.abc import Sequence

    from sortipy.domain.model import Namespace, Release

    from .schema import (
        MBArtistCredit,
        MBLabelInfo,
        MBRecording,
        MBRecordingRef,
        MBRelation,
        MBRelease,
        MBReleaseGroup,
        MBReleaseRef,
        MusicBrainzAlias,
        MusicBrainzArtist,
    )


def translate_recording(recording: MBRecording) -> Release:
    """Translate a MusicBrainz recording payload into a release aggregate."""

    release = _select_release(recording)
    if release is None:
        release_set = ReleaseSet(title=recording.title)
        release_set.add_source(Provider.MUSICBRAINZ)
        release_entity = release_set.create_release(title=recording.title)
        release_entity.add_source(Provider.MUSICBRAINZ)
        recording_entity = _recording_entity(
            recording,
            artist_cache={},
            fallback_credits=recording.artist_credit,
        )
        release_entity.add_track(recording_entity)
        return release_entity
    return translate_release(release)


def translate_release(release: MBRelease) -> Release:
    """Translate a MusicBrainz release payload into a release aggregate."""

    artist_cache: dict[str, Artist] = {}
    recording_cache: dict[str, Recording] = {}
    release_set = _release_set_entity(
        release.release_group,
        fallback_title=release.title,
        fallback_credits=release.artist_credit,
        artist_cache=artist_cache,
    )
    release_entity = release_set.create_release(
        title=release.title,
        release_date=_parse_partial_date(release.date),
        country=release.country,
        format_=_primary_release_format(release),
        medium_count=len(release.media) if release.media else None,
    )
    release_entity.add_source(Provider.MUSICBRAINZ)
    release_entity.status = _release_status(release.status)
    release_entity.packaging = _release_packaging(release.packaging)
    _add_external_ids(release_entity, _release_external_ids(release))
    _add_labels(release_entity, release.label_info)
    _add_release_tracks(
        release_entity,
        release,
        artist_cache=artist_cache,
        recording_cache=recording_cache,
    )
    return release_entity


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
    )


def _release_set_entity(
    release_group: MBReleaseGroup | None,
    *,
    fallback_title: str,
    fallback_credits: list[MBArtistCredit],
    artist_cache: dict[str, Artist],
) -> ReleaseSet:
    if release_group is None:
        release_set = ReleaseSet(title=fallback_title)
        artist_credits = fallback_credits
    else:
        release_set = ReleaseSet(
            title=release_group.title,
            primary_type=_release_set_type(release_group.primary_type),
            secondary_types=_release_set_secondary_types(release_group.secondary_types),
            first_release=_parse_partial_date(release_group.first_release_date),
            aliases=_alias_names(release_group.aliases),
        )
        _add_external_ids(release_set, _release_group_external_ids(release_group))
        artist_credits = release_group.artist_credit or fallback_credits
    release_set.add_source(Provider.MUSICBRAINZ)
    _add_release_set_credits(release_set, artist_credits, artist_cache)
    return release_set


def _add_release_set_credits(
    release_set: ReleaseSet,
    artist_credits: list[MBArtistCredit],
    artist_cache: dict[str, Artist],
) -> None:
    prev_join: str | None = None
    for index, credit in enumerate(artist_credits):
        contribution = release_set.add_artist(
            _artist_entity(credit.artist, artist_cache),
            role=_role_for_credit(index=index, prev_join_phrase=prev_join),
            credit_order=index,
            credited_as=_credited_as(credit),
            join_phrase=credit.join_phrase,
        )
        contribution.add_source(Provider.MUSICBRAINZ)
        prev_join = credit.join_phrase


def _add_release_tracks(
    release_entity: Release,
    release: MBRelease,
    *,
    artist_cache: dict[str, Artist],
    recording_cache: dict[str, Recording],
) -> None:
    for medium in release.media:
        for track in medium.tracks:
            recording_payload = track.recording
            if recording_payload is None:
                continue
            recording_entity = recording_cache.get(recording_payload.id)
            if recording_entity is None:
                artist_credits = track.artist_credit or release.artist_credit
                recording_entity = _recording_entity(
                    recording_payload,
                    artist_cache=artist_cache,
                    fallback_credits=artist_credits,
                )
                recording_cache[recording_payload.id] = recording_entity
            title_override = (
                track.title if track.title and track.title != recording_entity.title else None
            )
            release_track = release_entity.add_track(
                recording_entity,
                disc_number=medium.position,
                track_number=track.position,
                title_override=title_override,
                duration_ms=track.length,
            )
            release_track.add_source(Provider.MUSICBRAINZ)


def _recording_entity(
    recording: MBRecording | MBRecordingRef,
    *,
    artist_cache: dict[str, Artist],
    fallback_credits: list[MBArtistCredit],
) -> Recording:
    aliases = _recording_aliases(getattr(recording, "aliases", []))
    entity = Recording(
        title=recording.title,
        duration_ms=recording.length,
        disambiguation=recording.disambiguation or None,
        aliases=_alias_names(aliases),
    )
    entity.add_source(Provider.MUSICBRAINZ)
    _add_external_ids(entity, _recording_external_ids(recording))
    prev_join: str | None = None
    artist_credits = _artist_credits(getattr(recording, "artist_credit", [])) or fallback_credits
    for index, credit in enumerate(artist_credits):
        contribution = entity.add_artist(
            _artist_entity(credit.artist, artist_cache),
            role=_role_for_credit(index=index, prev_join_phrase=prev_join),
            credit_order=index,
            credited_as=_credited_as(credit),
            join_phrase=credit.join_phrase,
        )
        contribution.add_source(Provider.MUSICBRAINZ)
        prev_join = credit.join_phrase
    return entity


def _artist_entity(
    artist: MusicBrainzArtist,
    artist_cache: dict[str, Artist],
) -> Artist:
    cached = artist_cache.get(artist.id)
    if cached is not None:
        return cached
    entity = Artist(
        name=artist.name,
        sort_name=artist.sort_name,
        country=artist.country,
        kind=_artist_kind(artist.type),
        aliases=_alias_names(artist.aliases),
        life_span=_life_span(artist.life_span),
        areas=_areas_for_artist(artist),
    )
    entity.add_source(Provider.MUSICBRAINZ)
    _add_external_ids(entity, _artist_external_ids(artist))
    artist_cache[artist.id] = entity
    return entity


def _add_labels(release: Release, label_infos: list[MBLabelInfo]) -> None:
    for info in label_infos:
        label = getattr(info, "label", None)
        label_name = getattr(label, "name", None)
        label_id = getattr(label, "id", None)
        if not label_name and not label_id:
            continue
        entity = Label(name=label_name or label_id or "unknown-label")
        entity.add_source(Provider.MUSICBRAINZ)
        if label_id:
            entity.add_external_id(ExternalNamespace.MUSICBRAINZ_LABEL, label_id)
        if label is not None:
            _add_external_ids(entity, _urls_as_external_ids(getattr(label, "relations", [])))
        release.add_label(entity)


def _add_external_ids(
    entity: Artist | Label | Recording | Release | ReleaseSet,
    ids: list[tuple[Namespace, str]],
) -> None:
    existing = set(entity.external_ids_by_namespace)
    for namespace, value in ids:
        if namespace in existing:
            continue
        entity.add_external_id(namespace, value)
        existing.add(namespace)


def _artist_external_ids(artist: MusicBrainzArtist) -> list[tuple[Namespace, str]]:
    ids: list[tuple[Namespace, str]] = [
        (ExternalNamespace.MUSICBRAINZ_ARTIST, artist.id),
    ]
    ids.extend(("artist:ipi", ipi) for ipi in getattr(artist, "ipis", []))
    ids.extend(("artist:isni", isni) for isni in getattr(artist, "isnis", []))
    ids.extend(_urls_as_external_ids(_relations(getattr(artist, "relations", []))))
    return ids


def _recording_external_ids(recording: MBRecording | MBRecordingRef) -> list[tuple[Namespace, str]]:
    ids: list[tuple[Namespace, str]] = [
        (ExternalNamespace.MUSICBRAINZ_RECORDING, recording.id),
    ]
    ids.extend((ExternalNamespace.RECORDING_ISRC, isrc) for isrc in getattr(recording, "isrcs", ()))
    ids.extend(_urls_as_external_ids(_relations(getattr(recording, "relations", []))))
    return ids


def _release_group_external_ids(group: MBReleaseGroup) -> list[tuple[Namespace, str]]:
    ids: list[tuple[Namespace, str]] = [
        (ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, group.id),
    ]
    ids.extend(_urls_as_external_ids(group.relations))
    return ids


def _release_external_ids(release: MBRelease) -> list[tuple[Namespace, str]]:
    ids: list[tuple[Namespace, str]] = [
        (ExternalNamespace.MUSICBRAINZ_RELEASE, release.id),
    ]
    if release.barcode:
        ids.extend(_barcode_external_ids(release.barcode))
    ids.extend(_urls_as_external_ids(release.relations))
    return ids


def _urls_as_external_ids(relations: list[MBRelation]) -> list[tuple[Namespace, str]]:
    ids: list[tuple[Namespace, str]] = []
    for relation in relations:
        if relation.url is None:
            continue
        url = relation.url.resource
        namespace = f"url:{relation.type.replace(' ', '-')}:{urlparse(url).netloc}"
        ids.append((namespace, url))
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
    normalized = raw.strip().lower()
    if not normalized:
        return None
    return _RELEASE_PACKAGING_MAP.get(normalized, ReleasePackaging.OTHER)


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


def _alias_names(aliases: Sequence[MusicBrainzAlias | dict[str, object]]) -> list[str]:
    names: list[str] = []
    for alias in aliases:
        if isinstance(alias, dict):
            name = alias.get("name")
            if isinstance(name, str):
                names.append(name)
            continue
        names.append(alias.name)
    return names


def _artist_credits(value: object) -> list[MBArtistCredit]:
    if not isinstance(value, list):
        return []
    return cast("list[MBArtistCredit]", value)


def _recording_aliases(value: object) -> list[MusicBrainzAlias | dict[str, object]]:
    if not isinstance(value, list):
        return []
    return cast("list[MusicBrainzAlias | dict[str, object]]", value)


def _relations(value: object) -> list[MBRelation]:
    if not isinstance(value, list):
        return []
    return cast("list[MBRelation]", value)


def _select_release(recording: MBRecording) -> MBRelease | None:
    if not recording.releases:
        return None
    return recording.releases[0]


def _primary_release_format(release: MBRelease) -> str | None:
    formats = _release_media_formats(release)
    return formats[0] if formats else None


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
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


_BARCODE_LENGTH_UPC = 12
_BARCODE_LENGTH_EAN = 13


def _barcode_external_ids(barcode: str) -> list[tuple[Namespace, str]]:
    value = barcode.strip()
    if not value:
        return []
    if value.isdigit():
        if len(value) == _BARCODE_LENGTH_UPC:
            namespace: Namespace = ExternalNamespace.RELEASE_UPC
        elif len(value) == _BARCODE_LENGTH_EAN:
            namespace = ExternalNamespace.RELEASE_EAN
        else:
            namespace = "release:barcode"
    else:
        namespace = "release:barcode"
    return [(namespace, value)]
