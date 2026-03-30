"""Fetcher checks for MusicBrainz reconciliation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.adapters.musicbrainz.candidates import MusicBrainzReleaseCandidate
from sortipy.adapters.musicbrainz.client import MusicBrainzAPIError, MusicBrainzNotFoundError
from sortipy.adapters.musicbrainz.fetcher import (
    fetch_release_candidates_from_recording,
    fetch_release_candidates_from_release,
    fetch_release_graph,
)
from sortipy.adapters.musicbrainz.schema import (
    MBRecordingSearch,
    MBRelease,
    MBReleaseRef,
    MBReleaseSearch,
)
from sortipy.adapters.musicbrainz.translator import parse_partial_date, translate_release
from sortipy.domain.model import Artist, ExternalNamespace, Recording, ReleaseSet

if TYPE_CHECKING:
    from sortipy.adapters.musicbrainz.schema import (
        MBRecording,
    )
    from sortipy.config.musicbrainz import MusicBrainzConfig
    from sortipy.domain.model import Namespace, Release


class FakeMusicBrainzClient:
    def __init__(
        self,
        *,
        recording_payload: MBRecording | dict[str, MBRecording] | None = None,
        release_payloads: dict[str, MBRelease] | None = None,
        search_results: MBRecordingSearch | None = None,
        recording_error: Exception | None = None,
    ) -> None:
        if isinstance(recording_payload, dict):
            self._recording_payloads = recording_payload
            self._recording_payload = next(iter(recording_payload.values()))
        else:
            self._recording_payloads = None
            self._recording_payload = recording_payload
        self._release_payloads = release_payloads or {}
        self._search_results = search_results or MBRecordingSearch(recordings=[])
        self._release_search_results = MBReleaseSearch(releases=[])
        self._recording_error = recording_error
        self.fetch_recording_mbid: str | None = None
        self.fetch_release_mbid: str | None = None
        self.search_query: str | None = None
        self.release_search_query: str | None = None

    def fetch_recording(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None = None,
    ) -> MBRecording:
        del inc
        if self._recording_error is not None:
            raise self._recording_error
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

    def search_releases(
        self,
        *,
        query: str,
        limit: int = 10,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch:
        del limit, offset, inc
        self.release_search_query = query
        return self._release_search_results

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


def test_fetch_release_candidates_falls_back_to_search_when_recording_mbid_is_missing(
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
            recording_error=MusicBrainzNotFoundError("missing"),
        )

        candidates = fetch_release_candidates_from_recording(
            domain_recording,
            config=musicbrainz_config,
            client=fake,
        )

        assert fake.fetch_recording_mbid is None
        assert fake.search_query is not None
        assert [candidate.mbid for candidate in candidates] == [
            release.id for release in recording.releases
        ]


def test_fetch_release_candidates_skips_on_recording_fetch_error(
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
            recording_error=MusicBrainzAPIError("boom"),
        )

        candidates = fetch_release_candidates_from_recording(
            domain_recording,
            config=musicbrainz_config,
            client=fake,
        )

        assert candidates == []


def test_fetch_release_candidates_from_release_searches_by_title_and_artist(
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    release_set = ReleaseSet(title="Two Ribbons")
    release = release_set.create_release(title="Two Ribbons")
    recording = Recording(title="Watching You Go")
    recording.add_artist(Artist(name="Let's Eat Grandma"))
    release.add_track(recording)
    release_ref = MBReleaseRef(
        id="2f06e168-8d4f-4253-8c85-4a097685ece0",
        title="Two Ribbons",
        date="2022-04-08",
    )
    fake = FakeMusicBrainzClient()
    fake._release_search_results = MBReleaseSearch(releases=[release_ref])

    candidates = fetch_release_candidates_from_release(
        release,
        config=musicbrainz_config,
        client=fake,
    )

    assert fake.release_search_query == 'release:"Two Ribbons" AND artist:"Let\'s Eat Grandma"'
    assert len(candidates) == 1
    assert candidates[0].mbid == "2f06e168-8d4f-4253-8c85-4a097685ece0"
    assert candidates[0].release_date == parse_partial_date("2022-04-08")


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


def test_fetch_release_graph_full_adapter(
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
        graph = fetch_release_graph(
            MusicBrainzReleaseCandidate(mbid=mbid),
            config=musicbrainz_config,
            client=fake,
        )
        assert fake.fetch_release_mbid == mbid
        assert graph.requested_mbid == mbid
        assert graph.resolved_mbid == release.id
        assert graph.redirected is False
        assert _release_signature(graph.release) == _release_signature(translate_release(release))


def test_fetch_release_graph_marks_redirect_when_payload_id_differs(
    release_payloads_by_id: dict[str, dict[str, object]],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    payloads = {
        mbid: MBRelease.model_validate(payload) for mbid, payload in release_payloads_by_id.items()
    }
    requested_mbid, release = next(iter(payloads.items()))
    redirected_payload = release.model_copy(update={"id": "0772539c-7916-4504-bfdd-3ea8e011bb4d"})
    fake = FakeMusicBrainzClient(release_payloads={requested_mbid: redirected_payload})

    graph = fetch_release_graph(
        MusicBrainzReleaseCandidate(mbid=requested_mbid),
        config=musicbrainz_config,
        client=fake,
    )

    assert fake.fetch_release_mbid == requested_mbid
    assert graph.requested_mbid == requested_mbid
    assert graph.resolved_mbid == "0772539c-7916-4504-bfdd-3ea8e011bb4d"
    assert graph.redirected is True


def _release_signature(release: Release) -> dict[str, object]:
    def _namespace_value(namespace: Namespace) -> str:
        return str(namespace)

    return {
        "release_title": release.title,
        "release_external_ids": sorted(
            (_namespace_value(external_id.namespace), external_id.value)
            for external_id in release.external_ids
        ),
        "release_set_title": release.release_set.title,
        "release_set_external_ids": sorted(
            (_namespace_value(external_id.namespace), external_id.value)
            for external_id in release.release_set.external_ids
        ),
        "release_set_credits": [
            (
                contribution.artist.name,
                contribution.role.value if contribution.role is not None else None,
                contribution.credit_order,
                contribution.credited_as,
                contribution.join_phrase,
            )
            for contribution in release.release_set.contributions
        ],
        "track_titles": [track.recording.title for track in release.tracks],
        "track_recording_external_ids": [
            sorted(
                (_namespace_value(external_id.namespace), external_id.value)
                for external_id in track.recording.external_ids
            )
            for track in release.tracks
        ],
        "labels": sorted(label.name for label in release.labels),
    }
