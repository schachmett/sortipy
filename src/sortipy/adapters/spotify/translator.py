"""Translate Spotify payloads into domain entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    LibraryItem,
    Provider,
    Recording,
    Release,
    ReleaseSet,
    User,
)

if TYPE_CHECKING:
    from .schema import SpotifyAlbum, SpotifyArtist, SpotifyTrack


def translate_saved_track(
    track: SpotifyTrack,
    *,
    user: User,
) -> LibraryItem:
    active_user = user
    artists = [_build_artist(artist) for artist in track.artists]

    release_set, release = _build_release_set_and_release(track.album)
    recording = _build_recording(track)
    release_track = release.add_track(recording)
    release_track.add_source(Provider.SPOTIFY)

    for index, artist in enumerate(artists):
        role = ArtistRole.PRIMARY if index == 0 else ArtistRole.UNKNOWN
        release_set.add_artist(artist, role=role)
        recording.add_artist(artist, role=role)

    return active_user.save_entity(recording, source=Provider.SPOTIFY)


def translate_saved_album(
    album: SpotifyAlbum,
    *,
    user: User,
) -> LibraryItem:
    active_user = user
    artists = [_build_artist(artist) for artist in album.artists]
    release_set, _release = _build_release_set_and_release(album)

    for index, artist in enumerate(artists):
        role = ArtistRole.PRIMARY if index == 0 else ArtistRole.UNKNOWN
        release_set.add_artist(artist, role=role)

    return active_user.save_entity(release_set, source=Provider.SPOTIFY)


def translate_followed_artist(
    artist: SpotifyArtist,
    *,
    user: User,
) -> LibraryItem:
    active_user = user
    entity = _build_artist(artist)

    return active_user.save_entity(entity, source=Provider.SPOTIFY)


def _build_artist(artist: SpotifyArtist) -> Artist:
    entity = Artist(name=artist.name)
    entity.add_source(Provider.SPOTIFY)
    entity.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, artist.id)
    return entity


def _build_release_set_and_release(album: SpotifyAlbum) -> tuple[ReleaseSet, Release]:
    release_set = ReleaseSet(title=album.name)
    release_set.add_source(Provider.SPOTIFY)
    release_set.add_external_id(ExternalNamespace.SPOTIFY_ALBUM, album.id)
    _add_external_album_ids(release_set, album)

    release = release_set.create_release(title=album.name)
    release.add_source(Provider.SPOTIFY)
    return release_set, release


def _build_recording(track: SpotifyTrack) -> Recording:
    recording = Recording(title=track.name, duration_ms=track.duration_ms)
    recording.add_source(Provider.SPOTIFY)
    recording.add_external_id(ExternalNamespace.SPOTIFY_TRACK, track.id)
    _add_external_track_ids(recording, track)
    return recording


def _add_external_track_ids(recording: Recording, track: SpotifyTrack) -> None:
    isrc = track.external_ids.get("isrc")
    if isrc:
        recording.add_external_id(
            ExternalNamespace.RECORDING_ISRC,
            isrc,
            provider=Provider.SPOTIFY,
        )
    ean = track.external_ids.get("ean")
    if ean:
        recording.add_external_id(
            ExternalNamespace.RELEASE_EAN,
            ean,
            provider=Provider.SPOTIFY,
        )
    upc = track.external_ids.get("upc")
    if upc:
        recording.add_external_id(
            ExternalNamespace.RELEASE_UPC,
            upc,
            provider=Provider.SPOTIFY,
        )


def _add_external_album_ids(release_set: ReleaseSet, album: SpotifyAlbum) -> None:
    ean = album.external_ids.get("ean")
    if ean:
        release_set.add_external_id(
            ExternalNamespace.RELEASE_EAN,
            ean,
            provider=Provider.SPOTIFY,
        )
    upc = album.external_ids.get("upc")
    if upc:
        release_set.add_external_id(
            ExternalNamespace.RELEASE_UPC,
            upc,
            provider=Provider.SPOTIFY,
        )
