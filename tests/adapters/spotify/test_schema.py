"""Schema validation for captured Spotify payloads."""

from __future__ import annotations

from sortipy.adapters.spotify.schema import (
    FollowedArtistsResponse,
    SavedAlbumsPage,
    SavedTracksPage,
)


def test_schema_accepts_saved_tracks_payload(
    spotify_payloads: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    tracks_payload, _, _ = spotify_payloads
    parsed = SavedTracksPage.model_validate(tracks_payload)
    assert parsed.items
    assert parsed.items[0].track.id


def test_schema_accepts_saved_albums_payload(
    spotify_payloads: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    _, albums_payload, _ = spotify_payloads
    parsed = SavedAlbumsPage.model_validate(albums_payload)
    assert parsed.items
    assert parsed.items[0].album.id


def test_schema_accepts_followed_artists_payload(
    spotify_payloads: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    _, _, artists_payload = spotify_payloads
    parsed = FollowedArtistsResponse.model_validate(artists_payload)
    assert parsed.artists.items
    assert parsed.artists.items[0].id
