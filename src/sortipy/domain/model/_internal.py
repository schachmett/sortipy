"""Private helpers for mutating internal domain state.

Only domain model code should import this module.
"""

# ruff: noqa: SLF001

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sortipy.domain.model.associations import (
        RecordingContribution,
        ReleaseSetContribution,
        ReleaseTrack,
    )
    from sortipy.domain.model.music import Artist, Recording, Release, ReleaseSet
    from sortipy.domain.model.user import PlayEvent


def set_release_release_set(release: Release, release_set: ReleaseSet) -> None:
    release._release_set = release_set


def set_release_set_contribution_release_set(
    contribution: ReleaseSetContribution,
    release_set: ReleaseSet,
) -> None:
    contribution._release_set = release_set


def set_release_set_contribution_artist(
    contribution: ReleaseSetContribution,
    artist: Artist,
) -> None:
    contribution._artist = artist


def set_recording_contribution_recording(
    contribution: RecordingContribution,
    recording: Recording,
) -> None:
    contribution._recording = recording


def set_recording_contribution_artist(
    contribution: RecordingContribution,
    artist: Artist,
) -> None:
    contribution._artist = artist


def set_release_track_release(track: ReleaseTrack, release: Release) -> None:
    track._release = release


def set_release_track_recording(track: ReleaseTrack, recording: Recording) -> None:
    track._recording = recording


def set_play_event_track(event: PlayEvent, track: ReleaseTrack | None) -> None:
    event._track = track


def set_play_event_recording_ref(
    event: PlayEvent,
    recording: Recording | None,
) -> None:
    event._recording_ref = recording


def attach_release_set_contribution_to_release_set(
    release_set: ReleaseSet,
    contribution: ReleaseSetContribution,
) -> None:
    if contribution not in release_set._contributions:
        release_set._contributions.append(contribution)


def detach_release_set_contribution_from_release_set(
    release_set: ReleaseSet,
    contribution: ReleaseSetContribution,
) -> None:
    if contribution in release_set._contributions:
        release_set._contributions.remove(contribution)


def attach_release_set_contribution_to_artist(
    artist: Artist,
    contribution: ReleaseSetContribution,
) -> None:
    if contribution not in artist._release_set_contributions:
        artist._release_set_contributions.append(contribution)


def detach_release_set_contribution_from_artist(
    artist: Artist,
    contribution: ReleaseSetContribution,
) -> None:
    if contribution in artist._release_set_contributions:
        artist._release_set_contributions.remove(contribution)


def attach_recording_contribution_to_recording(
    recording: Recording,
    contribution: RecordingContribution,
) -> None:
    if contribution not in recording._contributions:
        recording._contributions.append(contribution)


def detach_recording_contribution_from_recording(
    recording: Recording,
    contribution: RecordingContribution,
) -> None:
    if contribution in recording._contributions:
        recording._contributions.remove(contribution)


def attach_recording_contribution_to_artist(
    artist: Artist,
    contribution: RecordingContribution,
) -> None:
    if contribution not in artist._recording_contributions:
        artist._recording_contributions.append(contribution)


def detach_recording_contribution_from_artist(
    artist: Artist,
    contribution: RecordingContribution,
) -> None:
    if contribution in artist._recording_contributions:
        artist._recording_contributions.remove(contribution)


def attach_release_track_to_release(release: Release, track: ReleaseTrack) -> None:
    if track not in release._tracks:
        release._tracks.append(track)


def detach_release_track_from_release(release: Release, track: ReleaseTrack) -> None:
    if track in release._tracks:
        release._tracks.remove(track)


def attach_release_track_to_recording(recording: Recording, track: ReleaseTrack) -> None:
    if track not in recording._release_tracks:
        recording._release_tracks.append(track)


def detach_release_track_from_recording(recording: Recording, track: ReleaseTrack) -> None:
    if track in recording._release_tracks:
        recording._release_tracks.remove(track)
