from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.types import Album, AlbumType, Artist, Provider, Scrobble, Track


def test_add_track_to_album_is_idempotent() -> None:
    artist = Artist(name="Test Artist")
    album = Album(name="Test Album", artist=artist, album_type=AlbumType.ALBUM)
    track = Track(name="Song", artist=artist, album=album)

    album.add_track(track)
    album.add_track(track)

    assert album.tracks == [track]


def test_track_scrobbles_are_unique() -> None:
    artist = Artist(name="Test Artist")
    album = Album(name="Test Album", artist=artist)
    track = Track(name="Song", artist=artist, album=album)
    scrobble = Scrobble(timestamp=datetime.now(tz=UTC), track=track)

    track.add_scrobble(scrobble)
    track.add_scrobble(scrobble)

    assert track.scrobbles == [scrobble]


def test_sources_are_tracked() -> None:
    artist = Artist(name="Test Artist")
    artist.add_source(Provider.LASTFM)
    artist.add_source(Provider.SPOTIFY)

    assert artist.sources == {Provider.LASTFM, Provider.SPOTIFY}


def test_album_and_track_cross_links() -> None:
    artist = Artist(name="Test Artist")
    album = Album(name="Test Album", artist=artist)
    track = Track(name="Song", artist=artist, album=album)
    scrobble = Scrobble(timestamp=datetime(2024, 1, 1, tzinfo=UTC), track=track)
    track.add_scrobble(scrobble)
    album.add_track(track)

    assert track in album.tracks
    assert track.album is album
    assert track.scrobbles[0].track is track
