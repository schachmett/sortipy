from __future__ import annotations

from sortipy.adapters.musicbrainz.candidates import (
    MusicBrainzReleaseCandidate,
    resolve_release_candidate,
)
from sortipy.domain.model import Recording, ReleaseSet


def test_resolve_release_candidate_falls_back_to_recording_candidates_for_release() -> None:
    release_set = ReleaseSet(title="BLUSH")
    release = release_set.create_release(title="BLUSH")
    recording_a = Recording(title="A")
    recording_b = Recording(title="B")
    recording_c = Recording(title="C")
    release.add_track(recording_a)
    release.add_track(recording_b)
    release.add_track(recording_c)

    candidate_a = MusicBrainzReleaseCandidate(
        mbid="release-a",
        title="BLUSH",
        track_count=3,
    )
    candidate_b = MusicBrainzReleaseCandidate(
        mbid="release-b",
        title="Something Else",
        track_count=8,
    )
    candidate_c = MusicBrainzReleaseCandidate(
        mbid="release-c",
        title="Another Release",
        track_count=10,
    )

    candidates_by_recording = {
        recording_a: [candidate_a, candidate_b],
        recording_b: [candidate_a],
        recording_c: [candidate_a, candidate_c],
    }

    resolved = resolve_release_candidate(
        release,
        fetch_candidates_from_recording=lambda recording: candidates_by_recording[recording],
        fetch_candidates_from_release_set=lambda _release_set: [],
        fetch_candidates_from_artist=lambda _artist: [],
    )

    assert resolved is not None
    assert resolved.mbid == "release-a"


def test_resolve_release_candidate_prefers_title_match_when_recording_hits_tie() -> None:
    release_set = ReleaseSet(title="Two Ribbons")
    release = release_set.create_release(title="Two Ribbons")
    recording_a = Recording(title="A")
    recording_b = Recording(title="B")
    release.add_track(recording_a)
    release.add_track(recording_b)

    title_match = MusicBrainzReleaseCandidate(
        mbid="release-a",
        title="Two Ribbons",
        track_count=2,
    )
    miss = MusicBrainzReleaseCandidate(
        mbid="release-b",
        title="Not It",
        track_count=2,
    )

    candidates_by_recording = {
        recording_a: [title_match],
        recording_b: [miss],
    }

    resolved = resolve_release_candidate(
        release,
        fetch_candidates_from_recording=lambda recording: candidates_by_recording[recording],
        fetch_candidates_from_release_set=lambda _release_set: [],
        fetch_candidates_from_artist=lambda _artist: [],
    )

    assert resolved is not None
    assert resolved.mbid == "release-a"
