"""Fetcher checks for MusicBrainz enrichment."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.adapters.musicbrainz.fetcher import (
    fetch_release_candidates_from_recording,
    fetch_release_update,
)
from sortipy.adapters.musicbrainz.schema import (
    MBRecordingSearch,
    MBRelease,
    MBReleaseSearch,
)
from sortipy.adapters.musicbrainz.translator import translate_release
from sortipy.domain.entity_updates import ReleaseCandidate
from sortipy.domain.model import Artist, ExternalNamespace, Recording

if TYPE_CHECKING:
    from sortipy.adapters.musicbrainz.schema import (
        MBRecording,
    )
    from sortipy.config.musicbrainz import MusicBrainzConfig


class FakeMusicBrainzClient:
    def __init__(
        self,
        *,
        recording_payload: MBRecording | dict[str, MBRecording] | None = None,
        release_payloads: dict[str, MBRelease] | None = None,
        search_results: MBRecordingSearch | None = None,
    ) -> None:
        if isinstance(recording_payload, dict):
            self._recording_payloads = recording_payload
            self._recording_payload = next(iter(recording_payload.values()))
        else:
            self._recording_payloads = None
            self._recording_payload = recording_payload
        self._release_payloads = release_payloads or {}
        self._search_results = search_results or MBRecordingSearch(recordings=[])
        self.fetch_recording_mbid: str | None = None
        self.fetch_release_mbid: str | None = None
        self.search_query: str | None = None

    def fetch_recording(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None = None,
    ) -> MBRecording:
        del inc
        if self._recording_payloads is not None and mbid in self._recording_payloads:
            self.fetch_recording_mbid = mbid
            return self._recording_payloads[mbid]
        if self._recording_payload is not None:
            self.fetch_recording_mbid = mbid
            return self._recording_payload
        raise AssertionError("recording payload not configured")

    def search_recordings(
        self,
        *,
        query: str,
        limit: int = 1,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBRecordingSearch:
        del limit, offset, inc
        self.search_query = query
        return self._search_results

    def fetch_release(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None = None,
    ) -> MBRelease:
        del inc
        self.fetch_release_mbid = mbid
        try:
            return self._release_payloads[mbid]
        except KeyError as exc:
            raise AssertionError(f"release payload not configured for {mbid}") from exc

    def browse_releases_by_release_group(
        self,
        *,
        release_group_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch:
        del release_group_mbid, limit, offset, inc
        return MBReleaseSearch(releases=[])

    def browse_releases_by_artist(
        self,
        *,
        artist_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch:
        del artist_mbid, limit, offset, inc
        return MBReleaseSearch(releases=[])


def _domain_recording(*, title: str, artist_name: str | None = None) -> Recording:
    recording = Recording(title=title)
    if artist_name:
        artist = Artist(name=artist_name)
        recording.add_artist(artist)
    return recording


def test_fetch_release_candidates_prefers_mbid(
    recordings: list[MBRecording],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    for recording in recordings:
        artist_name = recording.artist_credit[0].artist.name if recording.artist_credit else None
        domain_recording = _domain_recording(title=recording.title, artist_name=artist_name)
        domain_recording.add_external_id(
            ExternalNamespace.MUSICBRAINZ_RECORDING,
            recording.id,
            replace=True,
        )
        fake = FakeMusicBrainzClient(
            recording_payload=recording,
            search_results=MBRecordingSearch(recordings=[recording]),
        )

        candidates = fetch_release_candidates_from_recording(
            domain_recording,
            config=musicbrainz_config,
            client=fake,
        )

        assert fake.fetch_recording_mbid == recording.id
        assert fake.search_query is None
        assert [candidate.mbid for candidate in candidates] == [
            release.id for release in recording.releases
        ]


def test_fetch_release_candidates_searches_without_mbid(
    recordings: list[MBRecording],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    for recording in recordings:
        artist_name = recording.artist_credit[0].artist.name if recording.artist_credit else None
        domain_recording = _domain_recording(title=recording.title, artist_name=artist_name)
        fake = FakeMusicBrainzClient(
            recording_payload=recording,
            search_results=MBRecordingSearch(recordings=[recording]),
        )

        candidates = fetch_release_candidates_from_recording(
            domain_recording,
            config=musicbrainz_config,
            client=fake,
        )

        assert fake.fetch_recording_mbid is None
        assert fake.search_query is not None
        assert "recording" in fake.search_query
        if recording.artist_credit:
            assert "artist" in fake.search_query
        assert [candidate.mbid for candidate in candidates] == [
            release.id for release in recording.releases
        ]


def test_fetch_release_candidates_skips_on_empty_search(
    recordings: list[MBRecording],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    for recording in recordings:
        artist_name = recording.artist_credit[0].artist.name if recording.artist_credit else None
        domain_recording = _domain_recording(title=recording.title, artist_name=artist_name)
        fake = FakeMusicBrainzClient(
            recording_payload=recording,
            search_results=MBRecordingSearch(recordings=[]),
        )

        candidates = fetch_release_candidates_from_recording(
            domain_recording,
            config=musicbrainz_config,
            client=fake,
        )

        assert candidates == []


def test_fetch_release_update_full_adapter(
    release_payloads_by_id: dict[str, dict[str, object]],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    payloads = {
        mbid: MBRelease.model_validate(payload) for mbid, payload in release_payloads_by_id.items()
    }
    fake = FakeMusicBrainzClient(
        release_payloads=payloads,
    )

    for mbid, release in payloads.items():
        update = fetch_release_update(
            ReleaseCandidate(mbid=mbid),
            config=musicbrainz_config,
            client=fake,
        )
        assert update == translate_release(release)
