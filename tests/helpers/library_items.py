"""Reusable fakes and helpers for library-item related tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    LibraryItem,
    Provider,
    Recording,
    ReleaseSet,
    User,
)
from sortipy.domain.ports.fetching import LibraryItemFetcher, LibraryItemFetchResult

if TYPE_CHECKING:
    from collections.abc import Iterable


def make_recording_library_item(user: User | None = None) -> LibraryItem:
    artist = Artist(name="Example Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release = release_set.create_release(title="Example Release")
    recording = Recording(title="Example Recording")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)
    release.add_track(recording)

    owner = user or User(display_name="Example User")
    return owner.save_entity(recording, source=Provider.SPOTIFY)


def make_release_set_library_item(user: User | None = None) -> LibraryItem:
    artist = Artist(name="Example Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)

    owner = user or User(display_name="Example User")
    return owner.save_entity(release_set, source=Provider.SPOTIFY)


def make_artist_library_item(user: User | None = None) -> LibraryItem:
    owner = user or User(display_name="Example User")
    artist = Artist(name="Example Artist")
    return owner.save_entity(artist, source=Provider.SPOTIFY)


class FakeLibraryItemSource(LibraryItemFetcher):
    """In-memory implementation of the library-item source port for testing."""

    def __init__(self, items: Iterable[LibraryItem]) -> None:
        self._items = list(items)
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        user: User,
        batch_size: int = 50,
        max_tracks: int | None = None,
        max_albums: int | None = None,
        max_artists: int | None = None,
    ) -> LibraryItemFetchResult:
        self.calls.append(
            {
                "user": user,
                "batch_size": batch_size,
                "max_tracks": max_tracks,
                "max_albums": max_albums,
                "max_artists": max_artists,
            }
        )
        return LibraryItemFetchResult(library_items=list(self._items))
