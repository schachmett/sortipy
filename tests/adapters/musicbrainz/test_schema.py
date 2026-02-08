"""Schema checks for MusicBrainz payloads."""

from __future__ import annotations

from sortipy.adapters.musicbrainz.schema import MBRecording, MBRelease


def test_recording_payload_parses(recording_payloads: list[dict[str, object]]) -> None:
    for recording_payload in recording_payloads:
        recording = MBRecording.model_validate(recording_payload)
        assert recording.id
        assert recording.title
        assert recording.artist_credit
        assert recording.releases


def test_release_payload_parses(release_payloads: list[dict[str, object]]) -> None:
    for release_payload in release_payloads:
        release = MBRelease.model_validate(release_payload)
        assert release.id
        assert release.title
        assert release.artist_credit
        assert release.release_group
