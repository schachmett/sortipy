"""Music domain entities (canonical). Ownership lives on aggregate roots.

Aggregate roots here:
- ReleaseSet owns ReleaseSetContribution + Releases (1:n)
- Recording owns RecordingContribution
- Release owns ReleaseTrack + labels link
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from . import _internal as internal
from .associations import (
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
)
from .entity import CanonicalizableMixin
from .enums import ArtistRole, EntityType
from .external_ids import ExternallyIdentifiableMixin
from .provenance import ProvenanceTrackedMixin

if TYPE_CHECKING:
    from .enums import ReleaseSetType
    from .primitives import CountryCode, DurationMs, PartialDate
    from .user import PlayEvent


class CanonicalEntity(
    CanonicalizableMixin, ProvenanceTrackedMixin, ExternallyIdentifiableMixin
): ...


@dataclass(eq=False, kw_only=True)
class Artist(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.ARTIST

    name: str
    sort_name: str | None = None
    country: CountryCode | None = None
    formed_year: int | None = None
    disbanded_year: int | None = None

    # Bidirectional views (read-only); owned by other aggregates
    _release_set_contributions: list[ReleaseSetContribution] = field(
        default_factory=list["ReleaseSetContribution"], repr=False
    )
    _recording_contributions: list[RecordingContribution] = field(
        default_factory=list["RecordingContribution"], repr=False
    )

    @property
    def release_set_contributions(self) -> tuple[ReleaseSetContribution, ...]:
        return tuple(self._release_set_contributions)

    @property
    def release_sets(self) -> tuple[ReleaseSet, ...]:
        return tuple(c.release_set for c in self._release_set_contributions)

    @property
    def recording_contributions(self) -> tuple[RecordingContribution, ...]:
        return tuple(self._recording_contributions)

    @property
    def recordings(self) -> tuple[Recording, ...]:
        return tuple(c.recording for c in self._recording_contributions)


@dataclass(eq=False, kw_only=True)
class ReleaseSet(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RELEASE_SET

    title: str
    primary_type: ReleaseSetType | None = None
    first_release: PartialDate | None = None

    # Owned children
    _releases: list[Release] = field(default_factory=list["Release"], repr=False)
    _contributions: list[ReleaseSetContribution] = field(
        default_factory=list["ReleaseSetContribution"], repr=False
    )

    @property
    def releases(self) -> tuple[Release, ...]:
        return tuple(self._releases)

    @property
    def contributions(self) -> tuple[ReleaseSetContribution, ...]:
        return tuple(self._contributions)

    @property
    def artists(self) -> tuple[Artist, ...]:
        return tuple(c.artist for c in self._contributions)

    # Commands (ownership here)
    def add_release(self, release: Release) -> None:
        if release.release_set is not self:
            internal.set_release_release_set(release, self)
        if release not in self._releases:
            self._releases.append(release)

    def remove_release(self, release: Release) -> None:
        if release.release_set is not self:
            raise ValueError("release not owned by this release set")
        if release in self._releases:
            self._releases.remove(release)

    def create_release(
        self,
        *,
        title: str,
        release_date: PartialDate | None = None,
        country: CountryCode | None = None,
        format_: str | None = None,
        medium_count: int | None = None,
    ) -> Release:
        release = Release(
            title=title,
            _release_set=self,
            release_date=release_date,
            country=country,
            format=format_,
            medium_count=medium_count,
        )
        self.add_release(release)
        return release

    def add_artist(
        self,
        artist: Artist,
        *,
        role: ArtistRole = ArtistRole.PRIMARY,
        credit_order: int | None = None,
        credited_as: str | None = None,
        join_phrase: str | None = None,
    ) -> ReleaseSetContribution:
        c = ReleaseSetContribution(
            _release_set=self,
            _artist=artist,
            role=role,
            credit_order=credit_order,
            credited_as=credited_as,
            join_phrase=join_phrase,
        )
        internal.attach_release_set_contribution_to_release_set(self, c)
        internal.attach_release_set_contribution_to_artist(artist, c)
        return c

    def move_contributions_to(self, new_owner: ReleaseSet) -> None:
        if new_owner is self:
            return
        for c in list(self._contributions):
            internal.detach_release_set_contribution_from_release_set(self, c)
            internal.set_release_set_contribution_release_set(c, new_owner)
            internal.attach_release_set_contribution_to_release_set(new_owner, c)

    def replace_artist(self, old: Artist, new: Artist) -> None:
        if old is new:
            return
        for c in list(self._contributions):
            if c.artist is not old:
                continue
            internal.detach_release_set_contribution_from_artist(old, c)
            internal.set_release_set_contribution_artist(c, new)
            internal.attach_release_set_contribution_to_artist(new, c)

    def remove_artist(self, artist: Artist) -> None:
        for c in list(self._contributions):
            if c.artist is artist:
                internal.detach_release_set_contribution_from_release_set(self, c)
                internal.detach_release_set_contribution_from_artist(artist, c)
                return
        raise ValueError("artist not linked to this release set")


@dataclass(eq=False, kw_only=True)
class Label(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.LABEL

    name: str
    country: CountryCode | None = None


@dataclass(eq=False, kw_only=True)
class Release(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RELEASE

    title: str
    _release_set: ReleaseSet = field(repr=False)
    release_date: PartialDate | None = None
    country: CountryCode | None = None
    format: str | None = None
    medium_count: int | None = None

    # Owned children / associations
    _tracks: list[ReleaseTrack] = field(default_factory=list["ReleaseTrack"], repr=False)
    # labels: pure m:n, still managed here
    _labels: list[Label] = field(default_factory=list["Label"], repr=False)

    @property
    def release_set(self) -> ReleaseSet:
        return self._release_set

    @property
    def tracks(self) -> tuple[ReleaseTrack, ...]:
        return tuple(self._tracks)

    @property
    def recordings(self) -> tuple[Recording, ...]:
        return tuple(t.recording for t in self._tracks)

    @property
    def labels(self) -> tuple[Label, ...]:
        return tuple(self._labels)

    # Commands (ownership here)
    def add_track(
        self,
        recording: Recording,
        *,
        disc_number: int | None = None,
        track_number: int | None = None,
        title_override: str | None = None,
        duration_ms: DurationMs | None = None,
    ) -> ReleaseTrack:
        t = ReleaseTrack(
            _release=self,
            _recording=recording,
            disc_number=disc_number,
            track_number=track_number,
            title_override=title_override,
            duration_ms=duration_ms,
        )
        internal.attach_release_track_to_release(self, t)
        internal.attach_release_track_to_recording(recording, t)
        return t

    def move_tracks_to(self, new_release: Release) -> None:
        if new_release is self:
            return
        for track in list(self._tracks):
            internal.detach_release_track_from_release(self, track)
            internal.set_release_track_release(track, new_release)
            internal.attach_release_track_to_release(new_release, track)

    def move_track_to_recording(self, track: ReleaseTrack, recording: Recording) -> None:
        if track.release is not self:
            raise ValueError("track not owned by this release")
        if track.recording is recording:
            return
        old_recording = track.recording
        internal.detach_release_track_from_recording(old_recording, track)
        internal.set_release_track_recording(track, recording)
        internal.attach_release_track_to_recording(recording, track)

    def remove_track(self, track: ReleaseTrack) -> None:
        internal.detach_release_track_from_release(self, track)
        internal.detach_release_track_from_recording(track.recording, track)

    def add_label(self, label: Label) -> None:
        if label not in self._labels:
            self._labels.append(label)

    def remove_label(self, label: Label) -> None:
        self._labels.remove(label)


@dataclass(eq=False, kw_only=True)
class Recording(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RECORDING

    title: str
    duration_ms: DurationMs | None = None
    version: str | None = None

    # Owned contributions
    _contributions: list[RecordingContribution] = field(
        default_factory=list["RecordingContribution"], repr=False
    )

    # Backrefs / views (owned by Release via ReleaseTrack)
    _release_tracks: list[ReleaseTrack] = field(default_factory=list["ReleaseTrack"], repr=False)

    @property
    def contributions(self) -> tuple[RecordingContribution, ...]:
        return tuple(self._contributions)

    @property
    def artists(self) -> tuple[Artist, ...]:
        return tuple(c.artist for c in self._contributions)

    @property
    def release_tracks(self) -> tuple[ReleaseTrack, ...]:
        return tuple(self._release_tracks)

    @property
    def releases(self) -> tuple[Release, ...]:
        return tuple(rt.release for rt in self._release_tracks)

    # Commands (ownership here)
    def add_artist(
        self,
        artist: Artist,
        *,
        role: ArtistRole = ArtistRole.PRIMARY,
        credit_order: int | None = None,
        credited_as: str | None = None,
        instrument: str | None = None,
    ) -> RecordingContribution:
        c = RecordingContribution(
            _recording=self,
            _artist=artist,
            role=role,
            credit_order=credit_order,
            credited_as=credited_as,
            instrument=instrument,
        )
        internal.attach_recording_contribution_to_recording(self, c)
        internal.attach_recording_contribution_to_artist(artist, c)
        return c

    def move_contributions_to(self, new_recording: Recording) -> None:
        if new_recording is self:
            return
        for c in list(self._contributions):
            internal.detach_recording_contribution_from_recording(self, c)
            internal.set_recording_contribution_recording(c, new_recording)
            internal.attach_recording_contribution_to_recording(new_recording, c)

    def replace_artist(self, old: Artist, new: Artist) -> None:
        if old is new:
            return
        for c in list(self._contributions):
            if c.artist is not old:
                continue
            internal.detach_recording_contribution_from_artist(old, c)
            internal.set_recording_contribution_artist(c, new)
            internal.attach_recording_contribution_to_artist(new, c)

    def remove_artist(self, artist: Artist) -> None:
        for c in list(self._contributions):
            if c.artist is artist:
                internal.detach_recording_contribution_from_recording(self, c)
                internal.detach_recording_contribution_from_artist(artist, c)
                return
        raise ValueError("artist not linked to this recording")

    def move_tracks_to(self, new_recording: Recording) -> None:
        if new_recording is self:
            return
        for track in list(self._release_tracks):
            track.release.move_track_to_recording(track, new_recording)

    def move_play_event_to(self, event: PlayEvent, new_recording: Recording) -> None:
        event.user.move_play_event_to(event, new_recording)
