"""Minimal Pydantic models for the Spotify Web API."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field


class SpotifyBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SpotifyArtist(SpotifyBaseModel):
    id: str
    name: str


class SpotifyAlbum(SpotifyBaseModel):
    id: str
    name: str
    release_date: str | None = None
    artists: list[SpotifyArtist] = Field(default_factory=list["SpotifyArtist"])
    external_ids: dict[str, str] = Field(default_factory=dict)


class SpotifyTrack(SpotifyBaseModel):
    id: str
    name: str
    duration_ms: int | None = None
    album: SpotifyAlbum
    artists: list[SpotifyArtist] = Field(default_factory=list["SpotifyArtist"])
    external_ids: dict[str, str] = Field(default_factory=dict)


class SavedTrackItem(SpotifyBaseModel):
    added_at: datetime | None = None
    track: SpotifyTrack


class SavedAlbumItem(SpotifyBaseModel):
    added_at: datetime | None = None
    album: SpotifyAlbum


class SpotifyCursor(SpotifyBaseModel):
    after: str | None = None
    before: str | None = None


class SpotifyPage(SpotifyBaseModel):
    href: str | None = None
    limit: int | None = None
    next: str | None = None
    offset: int | None = None
    previous: str | None = None
    total: int | None = None


class SavedTracksPage(SpotifyPage):
    items: list[SavedTrackItem] = Field(default_factory=list["SavedTrackItem"])


class SavedAlbumsPage(SpotifyPage):
    items: list[SavedAlbumItem] = Field(default_factory=list["SavedAlbumItem"])


class FollowedArtistsPage(SpotifyBaseModel):
    href: str | None = None
    limit: int | None = None
    next: str | None = None
    total: int | None = None
    cursors: SpotifyCursor | None = None
    items: list[SpotifyArtist] = Field(default_factory=list["SpotifyArtist"])


class FollowedArtistsResponse(SpotifyBaseModel):
    artists: FollowedArtistsPage
