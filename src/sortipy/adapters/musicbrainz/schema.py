"""MusicBrainz response schemas for recording enrichment."""

# switch off type warnings because of default_factory=list or set
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import logging
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

type MBId = str
type MBDate = str  # Format: YYYY-MM-DD
type CountryCode = str  # ISO 3166-1 + specials, see https://musicbrainz.org/doc/Release/Country

# TODO add release model at the recording model


class MBBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    _logged_extra_keys: ClassVar[set[str]] = set()

    def model_post_init(self, _context: object, /) -> None:
        extras = self.__pydantic_extra__
        if not extras:
            return
        new_keys = set(extras).difference(self._logged_extra_keys)
        if not new_keys:
            return
        self._logged_extra_keys.update(new_keys)
        log.warning(
            "MusicBrainz %s: unmodeled keys: %s",
            type(self).__name__,
            ", ".join(sorted(new_keys)),
        )


class MusicBrainzAlias(MBBaseModel):
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    locale: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")
    primary: bool | None = None
    begin_date: MBDate | None = Field(default=None, alias="begin-date")
    end_date: MBDate | None = Field(default=None, alias="end-date")


class MusicBrainzLifeSpan(MBBaseModel):
    begin: MBDate | None = None
    end: MBDate | None = None
    ended: bool | None = None


class MusicBrainzTag(MBBaseModel):
    name: str
    count: int | None = None


class MusicBrainzRating(MBBaseModel):
    value: float | None = None
    votes_count: int | None = Field(default=None, alias="votes-count")


class MusicBrainzArtist(MBBaseModel):
    id: MBId
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    disambiguation: str | None = None
    country: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")
    gender: str | None = None
    gender_id: MBId | None = Field(default=None, alias="gender-id")
    area: "MusicBrainzArea | None" = None
    begin_area: "MusicBrainzArea | None" = Field(default=None, alias="begin-area")
    end_area: "MusicBrainzArea | None" = Field(default=None, alias="end-area")
    life_span: MusicBrainzLifeSpan | None = Field(default=None, alias="life-span")
    aliases: list[MusicBrainzAlias] = Field(default_factory=list)
    ipis: list[str] = Field(default_factory=list)
    isnis: list[str] = Field(default_factory=list)
    tags: list[MusicBrainzTag] = Field(default_factory=list)
    rating: MusicBrainzRating | None = None
    relations: list[MBRelation] = Field(default_factory=list)
    annotation: str | None = None


class MBArtistCredit(MBBaseModel):
    artist: MusicBrainzArtist
    name: str
    join_phrase: str | None = Field(default=None, alias="joinphrase")


class MusicBrainzArea(MBBaseModel):
    id: MBId
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    disambiguation: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")
    iso_3166_1_codes: list[CountryCode] | None = Field(default=None, alias="iso-3166-1-codes")


class MBLabel(MBBaseModel):
    id: MBId
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    disambiguation: str | None = None
    country: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")
    label_code: int | None = Field(default=None, alias="label-code")
    life_span: MusicBrainzLifeSpan | None = Field(default=None, alias="life-span")
    aliases: list[MusicBrainzAlias] = Field(default_factory=list[MusicBrainzAlias])
    tags: list[MusicBrainzTag] = Field(default_factory=list[MusicBrainzTag])
    rating: MusicBrainzRating | None = None
    relations: list[MBRelation] = Field(default_factory=list)
    annotation: str | None = None


class MBLabelInfo(MBBaseModel):
    label: MBLabel | None = None
    catalog_number: str | None = Field(default=None, alias="catalog-number")


class MBReleaseEvent(MBBaseModel):
    date: MBDate | None = None
    area: MusicBrainzArea | None = None


class MBTextRepresentation(MBBaseModel):
    language: str | None = None
    script: str | None = None


class MBCoverArtArchive(MBBaseModel):
    count: int | None = None
    front: bool | None = None
    back: bool | None = None
    artwork: bool | None = None
    darkened: bool | None = None


class MBReleaseGroupPrimaryType(StrEnum):
    ALBUM = "Album"
    SINGLE = "Single"
    EP = "EP"
    BROADCAST = "Broadcast"
    OTHER = "Other"


class MBReleaseGroupSecondaryType(StrEnum):
    COMPILATION = "Compilation"
    SOUNDTRACK = "Soundtrack"
    SPOKENWORD = "Spokenword"
    INTERVIEW = "Interview"
    AUDIOBOOK = "Audiobook"
    AUDIO_DRAMA = "Audio Drama"
    LIVE = "Live"
    REMIX = "Remix"
    DJMIX = "DJ-mix"
    MIXTAPE = "Mixtape/Street"
    DEMO = "Demo"
    FIELD_RECORDING = "Field recording"


class MBReleaseGroup(MBBaseModel):
    id: MBId
    title: str
    disambiguation: str | None = None
    type: str | None = None
    primary_type: MBReleaseGroupPrimaryType | None = Field(default=None, alias="primary-type")
    primary_type_id: MBId | None = Field(default=None, alias="primary-type-id")
    secondary_types: list[MBReleaseGroupSecondaryType] = Field(
        default_factory=list, alias="secondary-types"
    )
    secondary_type_ids: list[MBId] = Field(default_factory=list, alias="secondary-type-ids")
    first_release_date: MBDate | None = Field(default=None, alias="first-release-date")
    artist_credit: list[MBArtistCredit] = Field(default_factory=list, alias="artist-credit")
    releases: list[MBReleaseRef] = Field(default_factory=list)
    tags: list[MusicBrainzTag] = Field(default_factory=list[MusicBrainzTag])
    rating: MusicBrainzRating | None = None
    relations: list[MBRelation] = Field(default_factory=list)
    aliases: list[MusicBrainzAlias] = Field(default_factory=list[MusicBrainzAlias])
    annotation: str | None = None


class MBReleaseStatus(StrEnum):
    OFFICIAL = "Official"
    PROMOTION = "Promotion"
    BOOTLEG = "Bootleg"
    PSEUDO_RELEASE = "Pseudo-release"
    WITHDRAWN = "Withdrawn"
    EXPUNGED = "Expunged"
    CANCELLED = "Cancelled"


class MBReleaseRef(MBBaseModel):
    id: MBId
    title: str | None = None
    status: MBReleaseStatus | None = None
    status_id: str | None = Field(default=None, alias="status-id")
    quality: str | None = Field(default=None, description="data quality")
    country: CountryCode | None = None
    date: MBDate | None = None
    barcode: str | None = None
    packaging: str | None = None
    packaging_id: MBId | None = Field(default=None, alias="packaging-id")
    disambiguation: str | None = None


class MBRelease(MBBaseModel):
    id: MBId
    title: str
    status: MBReleaseStatus | None = None
    status_id: str | None = Field(default=None, alias="status-id")
    quality: str | None = Field(default=None, description="data quality")
    country: CountryCode | None = None
    date: MBDate | None = None
    asin: str | None = None
    barcode: str | None = None
    packaging: str | None = None
    packaging_id: MBId | None = Field(default=None, alias="packaging-id")
    disambiguation: str | None = None
    cover_art_archive: MBCoverArtArchive | None = Field(default=None, alias="cover-art-archive")
    text_representation: MBTextRepresentation | None = Field(
        default=None, alias="text-representation"
    )
    release_events: list[MBReleaseEvent] = Field(default_factory=list, alias="release-events")
    artist_credit: list[MBArtistCredit] = Field(default_factory=list, alias="artist-credit")
    release_group: MBReleaseGroup | None = Field(default=None, alias="release-group")
    label_info: list[MBLabelInfo] = Field(default_factory=list[MBLabelInfo], alias="label-info")
    track_count: int | None = Field(default=None, alias="track-count")
    media: list[MBMedium] = Field(default_factory=list)
    relations: list[MBRelation] = Field(default_factory=list)
    tags: list[MusicBrainzTag] = Field(default_factory=list)
    rating: MusicBrainzRating | None = None
    annotation: str | None = None


class MBRecordingRef(MBBaseModel):
    id: MBId
    title: str
    length: int | None = Field(default=None, description="Length in ms")
    disambiguation: str | None = None


class MBTrack(MBBaseModel):
    id: MBId | None = None
    position: int | None = None
    number: str | None = None
    title: str
    length: int | None = None
    recording: MBRecordingRef | None = None
    artist_credit: list[MBArtistCredit] = Field(default_factory=list, alias="artist-credit")


class MBMedium(MBBaseModel):
    position: int | None = None
    format: str | None = None
    format_id: MBId | None = Field(default=None, alias="format-id")
    track_count: int | None = Field(default=None, alias="track-count")
    track_offset: int | None = Field(default=None, alias="track-offset")
    tracks: list[MBTrack] = Field(default_factory=list[MBTrack])


class MBUrl(MBBaseModel):
    id: MBId
    resource: str


class MBEntityType(StrEnum):
    AREA = "area"
    ARTIST = "artist"
    COLLECTION = "collection"
    EVENT = "event"
    GENRE = "genre"
    INSTRUMENT = "instrument"
    LABEL = "label"
    PLACE = "place"
    RECORDING = "recording"
    RELEASE = "release"
    RELEASE_GROUP = "release-group"
    SERIES = "series"
    WORK = "work"
    URL = "url"


# TODO: add relation types


class MBRelation(MBBaseModel):
    type: str
    type_id: MBId = Field(alias="type-id")
    target_type: MBEntityType = Field(alias="target-type")
    direction: Literal["forward", "backward"] | None = None
    begin: MBDate | None = None
    end: MBDate | None = None
    artist: MusicBrainzArtist | None = None
    recording: MBRecordingRef | None = None
    release: MBReleaseRef | None = None
    release_group: MBReleaseGroup | None = Field(default=None, alias="release-group")
    label: MBLabel | None = None
    work: MBWork | None = None
    url: MBUrl | None = None
    attributes: list[str] = Field(default_factory=list)
    attribute_ids: dict[str, str] = Field(default_factory=dict, alias="attribute-ids")
    attribute_credits: dict[str, str] = Field(default_factory=dict, alias="attribute-credits")
    attribute_values: dict[str, str] = Field(default_factory=dict, alias="attribute-values")
    ended: bool | None = None
    source_credit: str | None = Field(default=None, alias="source-credit")
    target_credit: str | None = Field(default=None, alias="target-credit")


class MBWork(MBBaseModel):
    id: MBId
    title: str
    disambiguation: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")
    language: str | None = None
    languages: list[str] = Field(default_factory=list)
    aliases: list[MusicBrainzAlias] = Field(default_factory=list[MusicBrainzAlias])
    tags: list[MusicBrainzTag] = Field(default_factory=list[MusicBrainzTag])
    rating: MusicBrainzRating | None = None


class MBRecording(MBBaseModel):
    id: MBId
    title: str
    length: int | None = Field(default=None, description="Length in ms")
    disambiguation: str | None = None
    score: int | str | None = None
    artist_credit: list[MBArtistCredit] = Field(default_factory=list, alias="artist-credit")
    isrcs: list[str] = Field(default_factory=list)
    first_release_date: MBDate | None = Field(default=None, alias="first-release-date")
    annotation: str | None = None
    video: bool | None = None
    releases: list[MBRelease] = Field(default_factory=list[MBRelease])
    release_groups: list[MBReleaseGroup] = Field(default_factory=list, alias="release-groups")
    relations: list[MBRelation] = Field(default_factory=list)
    aliases: list[MusicBrainzAlias] = Field(default_factory=list[MusicBrainzAlias])
    tags: list[MusicBrainzTag] = Field(default_factory=list[MusicBrainzTag])
    rating: MusicBrainzRating | None = None


class MBRecordingSearch(MBBaseModel):
    created: str | None = None
    count: int | None = None
    offset: int | None = None
    recordings: list[MBRecording] = Field(default_factory=list[MBRecording])


class MBReleaseSearch(MBBaseModel):
    created: str | None = None
    count: int | None = None
    offset: int | None = None
    releases: list[MBReleaseRef] = Field(default_factory=list[MBReleaseRef])


RecordingLookupResponse = MBRecording
