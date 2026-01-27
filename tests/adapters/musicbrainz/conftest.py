"""Shared fixtures for MusicBrainz adapter tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

import pytest

from sortipy.adapters.musicbrainz.schema import MusicBrainzRecording
from sortipy.config.http_resilience import ResilienceConfig
from sortipy.config.musicbrainz import MusicBrainzConfig
from sortipy.domain.model import ArtistRole, Provider
from sortipy.domain.ports.enrichment import ArtistCreditUpdate, RecordingEnrichmentUpdate

if TYPE_CHECKING:
    from uuid import UUID

MusicBrainzPayload = dict[str, object]
FIXTURES = Path("tests/data/musicbrainz")


def _load_recording_payloads() -> list[MusicBrainzPayload]:
    path = FIXTURES / "recordings.jsonl"
    payloads: list[MusicBrainzPayload] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        payloads.append(json.loads(line))
    return payloads


def _recording_id(mbid: str) -> UUID:
    return uuid5(NAMESPACE_URL, mbid)


@pytest.fixture
def recording_payloads() -> list[MusicBrainzPayload]:
    return _load_recording_payloads()


@pytest.fixture
def recording_payloads_by_id(
    recording_payloads: list[MusicBrainzPayload],
) -> dict[str, MusicBrainzPayload]:
    return {str(payload["id"]): payload for payload in recording_payloads}


@pytest.fixture
def recordings(recording_payloads: list[MusicBrainzPayload]) -> list[MusicBrainzRecording]:
    return [MusicBrainzRecording.model_validate(payload) for payload in recording_payloads]


@pytest.fixture
def recording(recordings: list[MusicBrainzRecording]) -> MusicBrainzRecording:
    return recordings[0]


@pytest.fixture
def musicbrainz_config() -> MusicBrainzConfig:
    return MusicBrainzConfig(
        resilience=ResilienceConfig(name="musicbrainz", base_url="http://example.com")
    )


@pytest.fixture
def expected_enrichment_updates() -> dict[str, RecordingEnrichmentUpdate]:
    mbid1 = "ab80a174-1b7d-41c8-bddb-5edfd849d512"
    mbid2 = "5fbaab56-3904-40fe-9ef2-be59a16c86be"
    mbid3 = "5e7029b3-f17e-4d4d-a08e-0bfd8f4a5765"
    return {
        mbid1: RecordingEnrichmentUpdate(
            recording_id=_recording_id(mbid1),
            mbid=mbid1,
            title="Welcome to the World of the Plastic Beach",
            duration_ms=215506,
            isrcs={"GBAYE1400433", "GBAYE1000004"},
            confidence=1.0,
            sources={Provider.MUSICBRAINZ},
            artist_credits=[
                ArtistCreditUpdate(
                    artist_mbid="e21857d5-3256-4547-afb3-4b6ded592596",
                    name="Gorillaz",
                    role=ArtistRole.PRIMARY,
                    credit_order=0,
                    credited_as=None,
                    join_phrase=" feat. ",
                ),
                ArtistCreditUpdate(
                    artist_mbid="f90e8b26-9e52-4669-a5c9-e28529c47894",
                    name="Snoop Dogg",
                    role=ArtistRole.FEATURED,
                    credit_order=1,
                    credited_as=None,
                    join_phrase=" & ",
                ),
                ArtistCreditUpdate(
                    artist_mbid="cc37d0c1-493d-487e-9694-3cf48ae6370d",
                    name="Hypnotic Brass Ensemble",
                    role=ArtistRole.UNKNOWN,
                    credit_order=2,
                    credited_as=None,
                    join_phrase="",
                ),
            ],
        ),
        mbid2: RecordingEnrichmentUpdate(
            recording_id=_recording_id(mbid2),
            mbid=mbid2,
            title="An Ocean in Between the Waves",
            duration_ms=431000,
            isrcs={"US38W1431004"},
            artist_credits=[
                ArtistCreditUpdate(
                    artist_mbid="87b9b3b8-ab93-426c-a200-4012d667a626",
                    name="The War on Drugs",
                    role=ArtistRole.PRIMARY,
                    credit_order=0,
                    credited_as=None,
                    join_phrase="",
                )
            ],
            confidence=1.0,
            sources={Provider.MUSICBRAINZ},
        ),
        mbid3: RecordingEnrichmentUpdate(
            recording_id=_recording_id(mbid3),
            mbid=mbid3,
            title="This Room (Four Tet & Manitoba remix)",
            disambiguation=None,
            duration_ms=488000,
            isrcs={"GBCEL0500996", "DED620219303"},
            artist_credits=[
                ArtistCreditUpdate(
                    artist_mbid="f180cec2-9421-4417-a841-c7372090d13d",
                    name="The Notwist",
                    role=ArtistRole.PRIMARY,
                    credit_order=0,
                    credited_as=None,
                    join_phrase="",
                )
            ],
            confidence=1.0,
            sources={Provider.MUSICBRAINZ},
        ),
    }
