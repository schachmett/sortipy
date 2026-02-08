"""Domain enums (pure, dependency-light)."""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    LASTFM = "lastfm"
    SPOTIFY = "spotify"
    MUSICBRAINZ = "musicbrainz"


class ExternalNamespace(StrEnum):
    MUSICBRAINZ_ARTIST = "musicbrainz:artist"
    MUSICBRAINZ_RELEASE_GROUP = "musicbrainz:release-group"
    MUSICBRAINZ_RELEASE = "musicbrainz:release"
    MUSICBRAINZ_RECORDING = "musicbrainz:recording"
    MUSICBRAINZ_LABEL = "musicbrainz:label"

    SPOTIFY_ARTIST = "spotify:artist"
    SPOTIFY_ALBUM = "spotify:album"
    SPOTIFY_TRACK = "spotify:track"

    LASTFM_ARTIST = "lastfm:artist"
    LASTFM_RECORDING = "lastfm:recording"

    RECORDING_ISRC = "recording:isrc"
    RELEASE_EAN = "release:ean"
    RELEASE_UPC = "release:upc"
    LABEL_CATALOG_NUMBER = "label:catalog_number"
    LABEL_BARCODE = "label:barcode"

    USER_SPOTIFY = "spotify:user"
    USER_LASTFM = "lastfm:user"


class EntityType(StrEnum):
    """Typed-reference discriminator for polymorphic ownership (ExternalID, LibraryItem, etc.)."""

    ARTIST = "artist"
    RELEASE_SET = "release_set"
    RELEASE = "release"
    RECORDING = "recording"
    LABEL = "label"

    # Association objects that can be externally identifiable:
    RELEASE_TRACK = "release_track"
    RELEASE_SET_CONTRIBUTION = "release_set_contribution"
    RECORDING_CONTRIBUTION = "recording_contribution"

    # User-facing:
    USER = "user"
    PLAY_EVENT = "play_event"
    LIBRARY_ITEM = "library_item"


class ArtistRole(StrEnum):
    UNKNOWN = "unknown"
    PRIMARY = "primary"
    FEATURED = "featured"
    PRODUCER = "producer"
    COMPOSER = "composer"
    CONDUCTOR = "conductor"


class ArtistKind(StrEnum):
    PERSON = "person"
    GROUP = "group"
    ORCHESTRA = "orchestra"
    CHOIR = "choir"
    OTHER = "other"


class AreaType(StrEnum):
    COUNTRY = "country"
    SUBDIVISION = "subdivision"
    CITY = "city"
    DISTRICT = "district"
    ISLAND = "island"
    COUNTY = "county"
    MUNICIPALITY = "municipality"
    REGION = "region"
    PROVINCE = "province"
    STATE = "state"
    OTHER = "other"


class AreaRole(StrEnum):
    PRIMARY = "primary"
    BEGIN = "begin"
    END = "end"


class ReleaseSetType(StrEnum):
    ALBUM = "album"
    SINGLE = "single"
    EP = "ep"
    BROADCAST = "broadcast"
    OTHER = "other"


class ReleaseSetSecondaryType(StrEnum):
    COMPILATION = "compilation"
    SOUNDTRACK = "soundtrack"
    SPOKENWORD = "spokenword"
    INTERVIEW = "interview"
    AUDIOBOOK = "audiobook"
    AUDIO_DRAMA = "audio drama"
    LIVE = "live"
    REMIX = "remix"
    DJMIX = "dj-mix"
    MIXTAPE = "mixtape"
    DEMO = "demo"
    FIELD_RECORDING = "field recording"


class ReleaseStatus(StrEnum):
    OFFICIAL = "official"
    PROMOTION = "promotion"
    BOOTLEG = "bootleg"
    PSEUDO_RELEASE = "pseudo-release"
    WITHDRAWN = "withdrawn"
    EXPUNGED = "expunged"
    CANCELLED = "cancelled"


class ReleasePackaging(StrEnum):
    NONE = "none"
    JEWEL_CASE = "jewel case"
    DIGIPAK = "digipak"
    GATEFOLD = "gatefold cover"
    CARDBOARD_PAPER_SLEEVE = "cardboard/paper sleeve"
    OTHER = "other"


class MergeReason(StrEnum):
    MANUAL = "manual"
