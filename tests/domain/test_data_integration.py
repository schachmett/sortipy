from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sortipy.domain.data_integration import (
    FetchScrobblesResult,
    LastFmScrobbleSource,
    ScrobbleRepository,
    ScrobbleUnitOfWork,
    SyncRequest,
    SyncScrobbles,
    SyncScrobblesResult,
)
from sortipy.domain.types import Album, Artist, Provider, Scrobble, Track

if TYPE_CHECKING:
    from types import TracebackType


def make_scrobble(name: str = "Example Track") -> Scrobble:
    artist = Artist(name="Example Artist")
    album = Album(name="Example Album", artist=artist)
    track = Track(name=name, artist=artist, album=album)
    scrobble = Scrobble(timestamp=datetime.now(tz=UTC), track=track, provider=Provider.LASTFM)
    track.add_scrobble(scrobble)
    album.add_track(track)
    artist.tracks.append(track)
    artist.albums.append(album)
    return scrobble


class FakeSource(LastFmScrobbleSource):
    def __init__(
        self,
        scrobble_pages: list[list[Scrobble]],
        *,
        now_playing: list[Scrobble | None] | None = None,
    ) -> None:
        self._pages = scrobble_pages
        self._now_playing = now_playing or [None] * max(1, len(scrobble_pages))
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
        total_pages = max(1, len(self._pages))
        index = page - 1
        scrobbles = self._pages[index] if 0 <= index < len(self._pages) else []
        now_playing = self._now_playing[index] if 0 <= index < len(self._now_playing) else None
        return FetchScrobblesResult(
            scrobbles=list(scrobbles),
            page=page,
            total_pages=total_pages,
            now_playing=now_playing,
        )


class FakeRepository(ScrobbleRepository):
    def __init__(self) -> None:
        self.items: list[Scrobble] = []

    def add(self, scrobble: Scrobble) -> None:
        self.items.append(scrobble)

    def exists(self, timestamp: datetime) -> bool:
        return any(item.timestamp == timestamp for item in self.items)

    def latest_timestamp(self) -> datetime | None:
        if not self.items:
            return None
        return max(item.timestamp for item in self.items)


class FakeUnitOfWork(ScrobbleUnitOfWork):
    def __init__(self, repo: FakeRepository) -> None:
        self.scrobbles: ScrobbleRepository = repo
        self.committed = False
        self.rollback_called = False

    def __enter__(self) -> FakeUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            self.rollback()
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rollback_called = True


def test_sync_scrobbles_persists_results() -> None:
    scrobble = make_scrobble()
    repo = FakeRepository()
    service = SyncScrobbles(
        source=FakeSource([[scrobble]]),
        unit_of_work=lambda: FakeUnitOfWork(repo),
    )

    result = service.run(SyncRequest(limit=5))

    assert isinstance(result, SyncScrobblesResult)
    assert result.stored == 1
    assert result.pages_processed == 1
    assert repo.items == [scrobble]
    assert repo.items[0].timestamp == scrobble.timestamp


def test_sync_scrobbles_skips_commit_when_empty() -> None:
    repo = FakeRepository()
    uow = FakeUnitOfWork(repo)
    service = SyncScrobbles(
        source=FakeSource([[]]),
        unit_of_work=lambda: uow,
    )

    result = service.run()

    assert result.stored == 0
    assert repo.items == []
    assert uow.committed is False


def test_sync_scrobbles_skips_existing_timestamps() -> None:
    scrobble = make_scrobble()
    repo = FakeRepository()
    repo.add(scrobble)
    service = SyncScrobbles(
        source=FakeSource([[scrobble]]),
        unit_of_work=lambda: FakeUnitOfWork(repo),
    )

    result = service.run()

    assert result.stored == 0
    assert repo.items == [scrobble]


def test_sync_scrobbles_respects_from_timestamp() -> None:
    scrobble_old = make_scrobble("Old")
    scrobble_old.timestamp = scrobble_old.timestamp.replace(microsecond=0)
    scrobble_new = make_scrobble("New")
    scrobble_new.timestamp = scrobble_old.timestamp + timedelta(seconds=60)
    repo = FakeRepository()
    repo.add(scrobble_old)
    fake_source = FakeSource([[scrobble_old, scrobble_new]])
    service = SyncScrobbles(
        source=fake_source,
        unit_of_work=lambda: FakeUnitOfWork(repo),
    )

    result = service.run()

    assert result.stored == 1
    assert scrobble_new in repo.items
    assert fake_source.calls[0][2] is not None


def test_sync_scrobbles_returns_now_playing_without_persisting() -> None:
    in_progress = make_scrobble("Now Playing")
    scrobble = make_scrobble("Logged")
    repo = FakeRepository()
    fake_source = FakeSource([[scrobble]], now_playing=[in_progress])
    service = SyncScrobbles(
        source=fake_source,
        unit_of_work=lambda: FakeUnitOfWork(repo),
    )

    result = service.run()

    assert result.now_playing is in_progress
    assert in_progress not in repo.items
    assert scrobble in repo.items
