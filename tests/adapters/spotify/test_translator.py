"""Translator tests for Spotify payloads."""

from __future__ import annotations

from sortipy.adapters.spotify.schema import (
    FollowedArtistsResponse,
    SavedAlbumsPage,
    SavedTracksPage,
)
from sortipy.adapters.spotify.translator import (
    translate_followed_artist,
    translate_saved_album,
    translate_saved_track,
)
from sortipy.domain.model import Artist, ExternalNamespace, Recording, ReleaseSet, User


def test_translate_saved_track_returns_recording_library_item(
    spotify_payloads: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    tracks_payload, _, _ = spotify_payloads
    parsed = SavedTracksPage.model_validate(tracks_payload)
    user = User(display_name="Spotify Smoke")

    library_item = translate_saved_track(parsed.items[0].track, user=user)
    target = library_item.require_target()

    assert library_item.user is user
    assert isinstance(target, Recording)
    assert ExternalNamespace.SPOTIFY_TRACK in target.external_ids_by_namespace


def test_translate_saved_album_returns_release_set_library_item(
    spotify_payloads: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    _, albums_payload, _ = spotify_payloads
    parsed = SavedAlbumsPage.model_validate(albums_payload)
    user = User(display_name="Spotify Smoke")

    library_item = translate_saved_album(parsed.items[0].album, user=user)
    target = library_item.require_target()

    assert library_item.user is user
    assert isinstance(target, ReleaseSet)
    assert ExternalNamespace.SPOTIFY_ALBUM in target.external_ids_by_namespace


def test_translate_followed_artist_returns_artist_library_item(
    spotify_payloads: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    _, _, artists_payload = spotify_payloads
    parsed = FollowedArtistsResponse.model_validate(artists_payload)
    user = User(display_name="Spotify Smoke")

    library_item = translate_followed_artist(parsed.artists.items[0], user=user)
    target = library_item.require_target()

    assert library_item.user is user
    assert isinstance(target, Artist)
    assert ExternalNamespace.SPOTIFY_ARTIST in target.external_ids_by_namespace
