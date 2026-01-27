"""Fetcher checks for MusicBrainz enrichment."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from sortipy.adapters.musicbrainz.fetcher import enrich_recordings
from sortipy.adapters.musicbrainz.schema import MusicBrainzRecording, MusicBrainzRecordingSearch
from sortipy.domain.model import Artist, ExternalNamespace, Recording

if TYPE_CHECKING:
    from sortipy.config.musicbrainz import MusicBrainzConfig
    from sortipy.domain.ports.enrichment import RecordingEnrichmentUpdate


class FakeMusicBrainzClient:
    def __init__(
        self,
        payload: MusicBrainzRecording | dict[str, MusicBrainzRecording],
        search_results: MusicBrainzRecordingSearch,
    ) -> None:
        if isinstance(payload, dict):
            self._payloads = payload
            self._payload = next(iter(payload.values()))
        else:
            self._payloads = None
            self._payload = payload
        self._search_results = search_results
        self.fetch_mbid: str | None = None
        self.search_query: str | None = None

    def fetch_recording(
        self, *, mbid: str, inc: tuple[str, ...] | None = None
    ) -> MusicBrainzRecording:
        del inc
        self.fetch_mbid = mbid
        if self._payloads is None:
            return self._payload
        return self._payloads.get(mbid, self._payload)

    def search_recordings(
        self,
        *,
        query: str,
        limit: int = 1,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MusicBrainzRecordingSearch:
        del limit, offset, inc
        self.search_query = query
        return self._search_results


def _domain_recording(*, title: str, artist_name: str | None = None) -> Recording:
    recording = Recording(title=title)
    if artist_name:
        artist = Artist(name=artist_name)
        recording.add_artist(artist)
    return recording


def test_enrich_recordings_prefers_mbid(
    recordings: list[MusicBrainzRecording],
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
            recording,
            MusicBrainzRecordingSearch(recordings=[recording]),
        )

        updates = enrich_recordings(
            [domain_recording],
            config=musicbrainz_config,
            client=fake,
        )

        assert fake.fetch_mbid == recording.id
        assert fake.search_query is None
        assert len(updates) == 1


def test_enrich_recordings_searches_without_mbid(
    recordings: list[MusicBrainzRecording],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    for recording in recordings:
        artist_name = recording.artist_credit[0].artist.name if recording.artist_credit else None
        domain_recording = _domain_recording(title=recording.title, artist_name=artist_name)
        fake = FakeMusicBrainzClient(
            recording,
            MusicBrainzRecordingSearch(recordings=[recording]),
        )

        updates = enrich_recordings(
            [domain_recording],
            config=musicbrainz_config,
            client=fake,
        )

        assert fake.fetch_mbid is None
        assert fake.search_query is not None
        assert "recording" in fake.search_query
        if recording.artist_credit:
            assert "artist" in fake.search_query
        assert len(updates) == 1


def test_enrich_recordings_skips_on_empty_search(
    recordings: list[MusicBrainzRecording],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    for recording in recordings:
        artist_name = recording.artist_credit[0].artist.name if recording.artist_credit else None
        domain_recording = _domain_recording(title=recording.title, artist_name=artist_name)
        fake = FakeMusicBrainzClient(
            recording,
            MusicBrainzRecordingSearch(recordings=[]),
        )

        updates = enrich_recordings(
            [domain_recording],
            config=musicbrainz_config,
            client=fake,
        )

        assert updates == []


def test_enrich_recordings_full_adapter(
    recording_payloads_by_id: dict[str, dict[str, object]],
    expected_enrichment_updates: dict[str, RecordingEnrichmentUpdate],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    payloads = {
        mbid: MusicBrainzRecording.model_validate(payload)
        for mbid, payload in recording_payloads_by_id.items()
    }
    domain_recordings: list[Recording] = []
    for mbid, payload in payloads.items():
        artist_name = payload.artist_credit[0].artist.name if payload.artist_credit else None
        recording_id = uuid5(NAMESPACE_URL, mbid)
        domain_recording = Recording(id=recording_id, title=payload.title)
        if artist_name:
            domain_recording.add_artist(Artist(name=artist_name))
        domain_recording.add_external_id(
            ExternalNamespace.MUSICBRAINZ_RECORDING,
            mbid,
            replace=True,
        )
        domain_recordings.append(domain_recording)

    fake = FakeMusicBrainzClient(
        payloads,
        MusicBrainzRecordingSearch(recordings=list(payloads.values())),
    )

    updates = enrich_recordings(
        domain_recordings,
        config=musicbrainz_config,
        client=fake,
    )
    updates_by_mbid = {update.mbid: update for update in updates if update.mbid is not None}

    for mbid, expected in expected_enrichment_updates.items():
        assert updates_by_mbid[mbid] == expected

    assert updates_by_mbid == expected_enrichment_updates
