"""Translator checks for MusicBrainz recordings."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sortipy.adapters.musicbrainz.translator import translate_recording
from sortipy.domain.model import ArtistRole

if TYPE_CHECKING:
    from sortipy.adapters.musicbrainz.schema import MusicBrainzRecording


def test_translate_recording_roles(recordings: list[MusicBrainzRecording]) -> None:
    for recording in recordings:
        update = translate_recording(recording, recording_id=uuid4())

        assert update.mbid == recording.id
        assert update.duration_ms == recording.length
        assert update.artist_credits is not None
        assert len(update.artist_credits) == len(recording.artist_credit)

        expected_roles = _expected_roles(recording)
        for credit, expected in zip(update.artist_credits, expected_roles, strict=True):
            assert credit.role is expected
            original = recording.artist_credit[credit.credit_order]
            if original.name != original.artist.name:
                assert credit.credited_as == original.name
            else:
                assert credit.credited_as is None


def _expected_roles(recording: MusicBrainzRecording) -> list[ArtistRole]:
    roles: list[ArtistRole] = []
    prev_join: str | None = None
    for index, credit in enumerate(recording.artist_credit):
        if index == 0:
            roles.append(ArtistRole.PRIMARY)
        elif _is_featuring(prev_join):
            roles.append(ArtistRole.FEATURED)
        else:
            roles.append(ArtistRole.UNKNOWN)
        prev_join = credit.join_phrase
    return roles


def _is_featuring(join_phrase: str | None) -> bool:
    if join_phrase is None:
        return False
    lowered = join_phrase.lower()
    return "feat" in lowered or "ft." in lowered
