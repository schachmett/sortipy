"""Schema checks for MusicBrainz payloads."""

from __future__ import annotations

from sortipy.adapters.musicbrainz.schema import MusicBrainzRecording


def test_recording_payload_parses(recording_payloads: list[dict[str, object]]) -> None:
    for recording_payload in recording_payloads:
        recording = MusicBrainzRecording.model_validate(recording_payload)
        assert recording.id
        assert recording.title
        assert recording.artist_credit
        assert recording.releases
