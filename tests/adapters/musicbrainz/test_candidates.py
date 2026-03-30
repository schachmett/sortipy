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
        fetch_candidates_from_release=lambda _release: [],
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
    recording_c = Recording(title="C")
    recording_d = Recording(title="D")
    release.add_track(recording_a)
    release.add_track(recording_b)
    release.add_track(recording_c)
    release.add_track(recording_d)

    title_match = MusicBrainzReleaseCandidate(
        mbid="release-a",
        title="Two Ribbons",
        track_count=4,
    )
    miss = MusicBrainzReleaseCandidate(
        mbid="release-b",
        title="Not It",
        track_count=4,
    )

    candidates_by_recording = {
        recording_a: [title_match],
        recording_b: [title_match],
        recording_c: [miss],
        recording_d: [miss],
    }

    resolved = resolve_release_candidate(
        release,
        fetch_candidates_from_recording=lambda recording: candidates_by_recording[recording],
        fetch_candidates_from_release=lambda _release: [],
        fetch_candidates_from_release_set=lambda _release_set: [],
        fetch_candidates_from_artist=lambda _artist: [],
    )

    assert resolved is not None
    assert resolved.mbid == "release-a"


def test_resolve_release_candidate_accepts_single_recording_hit_with_exact_title_match() -> None:
    release_set = ReleaseSet(title="Somersaults")
    release = release_set.create_release(title="Somersaults")
    recording_a = Recording(title="Triumph")
    recording_b = Recording(title="Blank")
    release.add_track(recording_a)
    release.add_track(recording_b)

    weak_match = MusicBrainzReleaseCandidate(
        mbid="release-a",
        title="Somersaults",
        track_count=11,
    )

    candidates_by_recording = {
        recording_a: [weak_match],
        recording_b: [],
    }

    resolved = resolve_release_candidate(
        release,
        fetch_candidates_from_recording=lambda recording: candidates_by_recording[recording],
        fetch_candidates_from_release=lambda _release: [],
        fetch_candidates_from_release_set=lambda _release_set: [],
        fetch_candidates_from_artist=lambda _artist: [],
    )

    assert resolved is not None
    assert resolved.mbid == "release-a"


def test_resolve_release_candidate_rejects_ambiguous_recording_fallback() -> None:
    release_set = ReleaseSet(title="Two Ribbons")
    release = release_set.create_release(title="Two Ribbons")
    recording_a = Recording(title="Watching You Go")
    recording_b = Recording(title="Levitation")
    recording_c = Recording(title="Happy New Year")
    recording_d = Recording(title="Insect Loop")
    release.add_track(recording_a)
    release.add_track(recording_b)
    release.add_track(recording_c)
    release.add_track(recording_d)

    first_variant = MusicBrainzReleaseCandidate(
        mbid="release-a",
        title="Two Ribbons",
        track_count=4,
    )
    second_variant = MusicBrainzReleaseCandidate(
        mbid="release-b",
        title="Two Ribbons",
        track_count=4,
    )

    candidates_by_recording = {
        recording_a: [first_variant],
        recording_b: [first_variant],
        recording_c: [second_variant],
        recording_d: [second_variant],
    }

    resolved = resolve_release_candidate(
        release,
        fetch_candidates_from_recording=lambda recording: candidates_by_recording[recording],
        fetch_candidates_from_release=lambda _release: [],
        fetch_candidates_from_release_set=lambda _release_set: [],
        fetch_candidates_from_artist=lambda _artist: [],
    )

    assert resolved is None


def test_resolve_release_candidate_falls_back_to_release_search() -> None:
    release_set = ReleaseSet(title="Somersaults")
    release = release_set.create_release(title="Somersaults")
    recording = Recording(title="Triumph")
    release.add_track(recording)

    release_search_candidate = MusicBrainzReleaseCandidate(
        mbid="6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38",
        title="Somersaults",
    )

    resolved = resolve_release_candidate(
        release,
        fetch_candidates_from_recording=lambda _recording: [],
        fetch_candidates_from_release=lambda _release: [release_search_candidate],
        fetch_candidates_from_release_set=lambda _release_set: [],
        fetch_candidates_from_artist=lambda _artist: [],
    )

    assert resolved is not None
    assert resolved.mbid == "6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38"
