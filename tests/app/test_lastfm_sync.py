from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sortipy.app import sync_lastfm_scrobbles
from sortipy.domain.data_integration import (
    FetchScrobblesResult,
    LastFmScrobbleSource,
    ScrobbleRepository,
    ScrobbleUnitOfWork,
    SyncRequest,
    SyncScrobblesResult,
)
from sortipy.domain.types import Album, Artist, Provider, Scrobble, Track


class FakeSource(LastFmScrobbleSource):
    def __init__(self, scrobbles: list[Scrobble]) -> None:
        self._scrobbles = scrobbles
        self.calls: list[dict[str, int | bool | None]] = []

    def fetch_recent(
        self,
        *,
        page: int = 1,
        limit: int = 200,
        from_ts: int | None = None,
        to_ts: int | None = None,
        extended: bool = False,
    ) -> FetchScrobblesResult:
        self.calls.append(
            {
                "page": page,
                "limit": limit,
                "from_ts": from_ts,
                "to_ts": to_ts,
                "extended": extended,
            }
        )
        return FetchScrobblesResult(
            scrobbles=self._scrobbles,
            page=page,
            total_pages=1,
            now_playing=None,
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


class MonkeyPatch(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


class FakeUnitOfWork(ScrobbleUnitOfWork):
    def __init__(self, repo: FakeRepository) -> None:
        self.scrobbles = repo
        self.committed = False

    def __enter__(self) -> FakeUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


def _make_scrobble(name: str) -> Scrobble:
    timestamp = datetime.now(tz=UTC).replace(microsecond=0)
    artist = Artist(name="Artist")
    album = Album(name="Album", artist=artist)
    track = Track(name=name, artist=artist, album=album)
    scrobble = Scrobble(timestamp=timestamp, track=track, provider=Provider.LASTFM)
    track.add_scrobble(scrobble)
    album.add_track(track)
    if track not in artist.tracks:
        artist.tracks.append(track)
    if album not in artist.albums:
        artist.albums.append(album)
    return scrobble


def test_sync_lastfm_scrobbles_orchestrates_dependencies(monkeypatch: MonkeyPatch) -> None:
    startup_called = False

    def fake_startup() -> None:
        nonlocal startup_called
        startup_called = True

    monkeypatch.setattr("sortipy.app.startup", fake_startup)

    scrobble = _make_scrobble("Example Track")
    source = FakeSource([scrobble])
    repo = FakeRepository()

    def factory() -> ScrobbleUnitOfWork:
        return FakeUnitOfWork(repo)

    result = sync_lastfm_scrobbles(
        SyncRequest(limit=1),
        source=source,
        unit_of_work_factory=factory,
    )

    assert startup_called is True
    assert isinstance(result, SyncScrobblesResult)
    assert result.stored == 1
    assert repo.items == [scrobble]
    assert source.calls[0]["limit"] == 1


def test_sync_lastfm_scrobbles_respects_existing_entries(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sortipy.app.startup", lambda: None)

    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    existing = _make_scrobble("Existing")
    existing.timestamp = base_time
    newer = _make_scrobble("Newer")
    newer.timestamp = base_time + timedelta(seconds=60)

    repo = FakeRepository()
    repo.add(existing)
    source = FakeSource([existing, newer])

    def factory() -> ScrobbleUnitOfWork:
        return FakeUnitOfWork(repo)

    result = sync_lastfm_scrobbles(
        SyncRequest(limit=2),
        source=source,
        unit_of_work_factory=factory,
    )

    assert result.stored == 1
    assert newer in repo.items
    assert existing in repo.items
