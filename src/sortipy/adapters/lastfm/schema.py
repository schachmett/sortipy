"""Pydantic models describing the Last.fm API payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ImageSize = Literal["small", "medium", "large", "extralarge"]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class LastFmBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ImageModel(LastFmBaseModel):
    size: ImageSize
    url: str = Field(alias="#text")


class ArtistPayload(LastFmBaseModel):
    name: str
    mbid: str | None = None
    url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_compact_schema(cls, value: object) -> object:
        if isinstance(value, Mapping):
            mapping_value = cast(Mapping[str, object], value)
            if "#text" in mapping_value and "name" not in mapping_value:
                data: dict[str, object] = dict(mapping_value)
                text_value = data.get("#text")
                if isinstance(text_value, str):
                    data["name"] = text_value
                return data
            return mapping_value
        return value

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)


class AlbumPayload(LastFmBaseModel):
    mbid: str | None = None
    title: str = Field(alias="#text")

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)


class TrackAttr(LastFmBaseModel):
    nowplaying: Literal["true"]


class DatePayload(LastFmBaseModel):
    uts: int = Field(alias="uts")
    text: str = Field(alias="#text")

    @field_validator("uts", mode="before")
    @classmethod
    def _parse_epoch(cls, value: int | str) -> int:
        return int(value)


class TrackPayload(LastFmBaseModel):
    artist: ArtistPayload
    streamable: Literal["0", "1"]
    image: list[ImageModel]
    mbid: str | None = None
    album: AlbumPayload
    name: str
    url: str
    date: DatePayload | None = None
    attr: TrackAttr | None = Field(default=None, alias="@attr")

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)

    @property
    def is_now_playing(self) -> bool:
        return self.attr is not None and self.attr.nowplaying == "true"


class ResponseAttr(LastFmBaseModel):
    user: str
    total_pages: int = Field(alias="totalPages")
    page: int
    per_page: int = Field(alias="perPage")
    total: int

    @field_validator("total_pages", "page", "per_page", "total", mode="before")
    @classmethod
    def _parse_int(cls, value: int | str) -> int:
        return int(value)


class RecentTracks(LastFmBaseModel):
    track: list[TrackPayload]
    attr: ResponseAttr = Field(alias="@attr")


class RecentTracksResponse(LastFmBaseModel):
    recenttracks: RecentTracks


class ErrorResponse(LastFmBaseModel):
    error: int
    message: str


TrackPayloadInput = TrackPayload | Mapping[str, object]
