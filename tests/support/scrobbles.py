"""Reusable fakes and helpers for scrobble-related tests."""

from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.data_integration import (
    FetchScrobblesResult,
    LastFmScrobbleSource,
    ScrobbleRepository,
    ScrobbleUnitOfWork,
)
from sortipy.domain.types import Album, Artist, Provider, Scrobble, Track


def make_scrobble(name: str = "Example Track", *, timestamp: datetime | None = None) -> Scrobble:
    """Create a scrobble with minimal associated domain entities."""

    artist = Artist(name="Example Artist")
    album = Album(name="Example Album", artist=artist)
    track = Track(name=name, artist=artist, album=album)
    scrobble_time = timestamp or datetime.now(tz=UTC)
    scrobble = Scrobble(timestamp=scrobble_time, track=track, provider=Provider.LASTFM)
    track.add_scrobble(scrobble)
    album.add_track(track)
    if track not in artist.tracks:
        artist.tracks.append(track)
    if album not in artist.albums:
        artist.albums.append(album)
    return scrobble


class FakeScrobbleSource(LastFmScrobbleSource):
    """In-memory implementation of the Last.fm source port for testing."""

    def __init__(
        self,
        scrobble_pages: list[list[Scrobble]],
        *,
        now_playing: list[Scrobble | None] | None = None,
    ) -> None:
        self._pages: list[list[Scrobble]] = [list(page) for page in scrobble_pages]
        if not self._pages:
            self._pages = [[]]
        default_now_playing = [None] * len(self._pages)
        self._now_playing = list(now_playing or default_now_playing)
        if len(self._now_playing) < len(self._pages):
            self._now_playing.extend([None] * (len(self._pages) - len(self._now_playing)))
        self.calls: list[tuple[int, int, int | None, int | None, bool]] = []

    def fetch_recent(
        self,
        *,
        page: int = 1,
        limit: int = 200,
        from_ts: int | None = None,
        to_ts: int | None = None,
        extended: bool = False,
    ) -> FetchScrobblesResult:
        self.calls.append((page, limit, from_ts, to_ts, extended))
        index = max(page - 1, 0)
        scrobbles = self._pages[index] if index < len(self._pages) else []
        now_playing = self._now_playing[index] if index < len(self._now_playing) else None
        return FetchScrobblesResult(
            scrobbles=list(scrobbles),
            page=page,
            total_pages=max(1, len(self._pages)),
            now_playing=now_playing,
        )


class FakeScrobbleRepository(ScrobbleRepository):
    """Simple in-memory repository for scrobbles."""

    def __init__(self, initial: list[Scrobble] | None = None) -> None:
        self.items: list[Scrobble] = list(initial or [])

    def add(self, scrobble: Scrobble) -> None:
        self.items.append(scrobble)

    def exists(self, timestamp: datetime) -> bool:
        return any(item.timestamp == timestamp for item in self.items)

    def latest_timestamp(self) -> datetime | None:
        if not self.items:
            return None
        return max(item.timestamp for item in self.items)


class FakeScrobbleUnitOfWork(ScrobbleUnitOfWork):
    """Unit of work capturing scrobble persistence interactions."""

    def __init__(self, repository: FakeScrobbleRepository) -> None:
        self.scrobbles: ScrobbleRepository = repository
        self.committed = False
        self.rollback_called = False

    def __enter__(self) -> FakeScrobbleUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if exc_type is not None:
            self.rollback()
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rollback_called = True


__all__ = [
    "FakeScrobbleRepository",
    "FakeScrobbleSource",
    "FakeScrobbleUnitOfWork",
    "make_scrobble",
]
