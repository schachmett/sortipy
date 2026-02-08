"""Shared fixtures for MusicBrainz adapter tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sortipy.adapters.musicbrainz.schema import MBRecording, MBRelease
from sortipy.config.http_resilience import ResilienceConfig
from sortipy.config.musicbrainz import MusicBrainzConfig

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


def _load_release_payloads() -> list[MusicBrainzPayload]:
    path = FIXTURES / "releases.jsonl"
    payloads: list[MusicBrainzPayload] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        payloads.append(json.loads(line))
    return payloads


@pytest.fixture
def recording_payloads() -> list[MusicBrainzPayload]:
    return _load_recording_payloads()


@pytest.fixture
def recording_payloads_by_id(
    recording_payloads: list[MusicBrainzPayload],
) -> dict[str, MusicBrainzPayload]:
    return {str(payload["id"]): payload for payload in recording_payloads}


@pytest.fixture
def recordings(recording_payloads: list[MusicBrainzPayload]) -> list[MBRecording]:
    return [MBRecording.model_validate(payload) for payload in recording_payloads]


@pytest.fixture
def recording(recordings: list[MBRecording]) -> MBRecording:
    return recordings[0]


@pytest.fixture
def release_payloads(recording_payloads: list[MusicBrainzPayload]) -> list[MusicBrainzPayload]:
    _ = recording_payloads
    return _load_release_payloads()


@pytest.fixture
def release_payloads_by_id(
    release_payloads: list[MusicBrainzPayload],
) -> dict[str, MusicBrainzPayload]:
    return {str(payload["id"]): payload for payload in release_payloads}


@pytest.fixture
def releases(release_payloads: list[MusicBrainzPayload]) -> list[MBRelease]:
    return [MBRelease.model_validate(payload) for payload in release_payloads]


@pytest.fixture
def release(releases: list[MBRelease]) -> MBRelease:
    return releases[0]


@pytest.fixture
def musicbrainz_config() -> MusicBrainzConfig:
    return MusicBrainzConfig(
        resilience=ResilienceConfig(name="musicbrainz", base_url="http://example.com")
    )
