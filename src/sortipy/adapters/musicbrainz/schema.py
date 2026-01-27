"""MusicBrainz response schemas for recording enrichment."""

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


class MusicBrainzBaseModel(BaseModel):
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


class MusicBrainzArtist(MusicBrainzBaseModel):
    id: MBId
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    disambiguation: str | None = None
    country: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")


class MusicBrainzArtistCredit(MusicBrainzBaseModel):
    artist: MusicBrainzArtist
    name: str
    join_phrase: str | None = Field(default=None, alias="joinphrase")


class MusicBrainzArea(MusicBrainzBaseModel):
    id: MBId
    name: str
    sort_name: str | None = Field(default=None, alias="sort-name")
    disambiguation: str | None = None
    type: str | None = None
    type_id: MBId | None = Field(default=None, alias="type-id")
    iso_3166_1_codes: list[CountryCode] | None = Field(default=None, alias="iso-3166-1-codes")


class MusicBrainzReleaseEvent(MusicBrainzBaseModel):
    date: MBDate
    area: MusicBrainzArea | None = None


class MusicBrainzTextRepresentation(MusicBrainzBaseModel):
    language: str | None = None
    script: str | None = None


class ReleaseGroupPrimaryType(StrEnum):
    ALBUM = "Album"
    SINGLE = "Single"
    EP = "EP"
    BROADCAST = "Broadcast"
    OTHER = "Other"


class ReleaseGroupSecondaryType(StrEnum):
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


class MusicBrainzReleaseGroup(MusicBrainzBaseModel):
    id: MBId
    title: str
    disambiguation: str | None = None
    primary_type: ReleaseGroupPrimaryType | None = Field(default=None, alias="primary-type")
    primary_type_id: MBId | None = Field(default=None, alias="primary-type-id")
    secondary_types: list[str] = Field(default_factory=list, alias="secondary-types")
    secondary_type_ids: list[MBId] = Field(default_factory=list, alias="secondary-type-ids")
    first_release_date: MBDate | None = Field(default=None, alias="first-release-date")
    artist_credit: list[MusicBrainzArtistCredit] = Field(
        default_factory=list["MusicBrainzArtistCredit"], alias="artist-credit"
    )


class ReleaseStatus(StrEnum):
    OFFICIAL = "Official"
    PROMOTION = "Promotion"
    BOOTLEG = "Bootleg"
    PSEUDO_RELEASE = "Pseudo-release"
    WITHDRAWN = "Withdrawn"
    EXPUNGED = "Expunged"
    CANCELLED = "Cancelled"


class MusicBrainzRelease(MusicBrainzBaseModel):
    id: MBId
    title: str
    status: ReleaseStatus
    status_id: str | None = Field(default=None, alias="status-id")
    quality: str | None = Field(default=None, description="data quality")
    country: CountryCode | None = None
    date: MBDate
    barcode: str | None = None
    packaging: str | None = None
    packaging_id: MBId | None = Field(default=None, alias="packaging-id")
    disambiguation: str | None = None
    text_representation: MusicBrainzTextRepresentation | None = Field(
        default=None, alias="text-representation"
    )
    release_events: list[MusicBrainzReleaseEvent] = Field(
        default_factory=list["MusicBrainzReleaseEvent"], alias="release-events"
    )
    artist_credit: list[MusicBrainzArtistCredit] = Field(
        default_factory=list["MusicBrainzArtistCredit"], alias="artist-credit"
    )
    release_group: MusicBrainzReleaseGroup | None = Field(default=None, alias="release-group")


class MusicBrainzUrl(MusicBrainzBaseModel):
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


class MusicBrainzRelation(MusicBrainzBaseModel):
    type: str
    type_id: MBId = Field(alias="type-id")
    target_type: MBEntityType = Field(alias="target-type")
    direction: Literal["forward", "backward"] | None = None
    artist: MusicBrainzArtist | None = None
    url: MusicBrainzUrl | None = None
    attributes: list[str] = Field(default_factory=list)
    attribute_ids: dict[str, str] = Field(default_factory=dict, alias="attribute-ids")
    attribute_values: dict[str, str] = Field(default_factory=dict, alias="attribute-values")
    ended: bool | None = None
    source_credit: str | None = Field(default=None, alias="source-credit")
    target_credit: str | None = Field(default=None, alias="target-credit")


class MusicBrainzRecording(MusicBrainzBaseModel):
    id: MBId
    title: str
    length: int | None = Field(default=None, description="Length in ms")
    disambiguation: str | None = None
    artist_credit: list[MusicBrainzArtistCredit] = Field(
        default_factory=list["MusicBrainzArtistCredit"], alias="artist-credit"
    )
    isrcs: list[str] = Field(default_factory=list)
    first_release_date: MBDate | None = Field(default=None, alias="first-release-date")
    annotation: str | None = None
    video: bool | None = None
    releases: list[MusicBrainzRelease] = Field(default_factory=list["MusicBrainzRelease"])
    relations: list[MusicBrainzRelation] = Field(default_factory=list["MusicBrainzRelation"])


class MusicBrainzRecordingSearch(MusicBrainzBaseModel):
    created: str | None = None
    count: int | None = None
    offset: int | None = None
    recordings: list[MusicBrainzRecording] = Field(default_factory=list["MusicBrainzRecording"])


RecordingLookupResponse = MusicBrainzRecording
