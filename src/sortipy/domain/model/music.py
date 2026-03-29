"""Music domain entities (canonical). Ownership lives on aggregate roots.

Aggregate roots here:
- ReleaseSet owns ReleaseSetContribution + Releases (1:n)
- Recording owns RecordingContribution
- Release owns ReleaseTrack + labels link
"""

# switch off type warnings because of default_factory=list or set
# pyright: reportUnknownVariableType=false

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
    from .enums import (
        ArtistKind,
        ReleasePackaging,
        ReleaseSetSecondaryType,
        ReleaseSetType,
        ReleaseStatus,
    )
    from .primitives import Area, CountryCode, DurationMs, LifeSpan, PartialDate
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
    kind: ArtistKind | None = None
    life_span: LifeSpan | None = None
    areas: list[Area] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
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

    def absorb(self, other: Artist) -> None:
        self._prefer_non_empty_string_field("name", other.name)
        self._prefer_optional_string_field("sort_name", other.sort_name)
        self._prefer_optional_value_field("country", other.country)
        self._prefer_optional_value_field("kind", other.kind)
        self._prefer_optional_value_field("life_span", other.life_span)
        self._prefer_optional_value_field("formed_year", other.formed_year)
        self._prefer_optional_value_field("disbanded_year", other.disbanded_year)
        self._merge_unique_list_field("areas", other.areas)
        self._merge_unique_list_field("aliases", other.aliases)
        self.absorb_external_ids(other)
        self.absorb_sources(other)


@dataclass(eq=False, kw_only=True)
class ReleaseSet(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RELEASE_SET

    title: str
    primary_type: ReleaseSetType | None = None
    secondary_types: list[ReleaseSetSecondaryType] = field(default_factory=list)
    first_release: PartialDate | None = None
    aliases: list[str] = field(default_factory=list)

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

    def absorb(self, other: ReleaseSet) -> None:
        self._prefer_non_empty_string_field("title", other.title)
        self._prefer_optional_value_field("primary_type", other.primary_type)
        self._prefer_optional_value_field("first_release", other.first_release)
        self._merge_unique_list_field("secondary_types", other.secondary_types)
        self._merge_unique_list_field("aliases", other.aliases)
        self.absorb_external_ids(other)
        self.absorb_sources(other)

    # Commands (ownership here)
    def add_release(self, release: Release) -> None:
        if release.release_set is not self:
            internal.set_release_release_set(release, self)
            release.mark_changed("release_set")
            self.mark_changed("releases")
        if release not in self._releases:
            self._releases.append(release)
            self.mark_changed("releases")

    def remove_release(self, release: Release) -> None:
        if release.release_set is not self:
            raise ValueError("release not owned by this release set")
        if release in self._releases:
            self._releases.remove(release)
            self.mark_changed("releases")

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
        self.mark_changed("contributions")
        artist.mark_changed("release_sets")
        return c

    def move_contributions_to(self, new_owner: ReleaseSet) -> None:
        if new_owner is self:
            return
        for c in list(self._contributions):
            internal.detach_release_set_contribution_from_release_set(self, c)
            internal.set_release_set_contribution_release_set(c, new_owner)
            internal.attach_release_set_contribution_to_release_set(new_owner, c)
            c.mark_changed("release_set")
        self.mark_changed("contributions")
        new_owner.mark_changed("contributions")

    def adopt_contribution(
        self,
        contribution: ReleaseSetContribution,
        *,
        artist: Artist | None = None,
    ) -> ReleaseSetContribution:
        target_artist = contribution.artist if artist is None else artist
        if contribution.release_set is self and contribution.artist is target_artist:
            return contribution
        if contribution.release_set is not self:
            internal.detach_release_set_contribution_from_release_set(
                contribution.release_set,
                contribution,
            )
            internal.set_release_set_contribution_release_set(contribution, self)
            internal.attach_release_set_contribution_to_release_set(self, contribution)
            contribution.mark_changed("release_set")
            self.mark_changed("contributions")
        if contribution.artist is not target_artist:
            internal.detach_release_set_contribution_from_artist(
                contribution.artist,
                contribution,
            )
            internal.set_release_set_contribution_artist(contribution, target_artist)
            internal.attach_release_set_contribution_to_artist(target_artist, contribution)
            contribution.mark_changed("artist")
        return contribution

    def replace_artist(self, old: Artist, new: Artist) -> None:
        if old is new:
            return
        for c in list(self._contributions):
            if c.artist is not old:
                continue
            internal.detach_release_set_contribution_from_artist(old, c)
            internal.set_release_set_contribution_artist(c, new)
            internal.attach_release_set_contribution_to_artist(new, c)
            c.mark_changed("artist")

    def remove_artist(self, artist: Artist) -> None:
        for c in list(self._contributions):
            if c.artist is artist:
                internal.detach_release_set_contribution_from_release_set(self, c)
                internal.detach_release_set_contribution_from_artist(artist, c)
                self.mark_changed("contributions")
                artist.mark_changed("release_sets")
                return
        raise ValueError("artist not linked to this release set")


@dataclass(eq=False, kw_only=True)
class Label(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.LABEL

    name: str
    country: CountryCode | None = None

    def absorb(self, other: Label) -> None:
        self._prefer_non_empty_string_field("name", other.name)
        self._prefer_optional_value_field("country", other.country)
        self.absorb_external_ids(other)
        self.absorb_sources(other)


@dataclass(eq=False, kw_only=True)
class Release(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RELEASE

    title: str
    _release_set: ReleaseSet = field(repr=False)
    release_date: PartialDate | None = None
    country: CountryCode | None = None
    status: ReleaseStatus | None = None
    packaging: ReleasePackaging | None = None
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

    def absorb(self, other: Release) -> None:
        self._prefer_non_empty_string_field("title", other.title)
        self._prefer_optional_value_field("release_date", other.release_date)
        self._prefer_optional_value_field("country", other.country)
        self._prefer_optional_value_field("status", other.status)
        self._prefer_optional_value_field("packaging", other.packaging)
        self._prefer_optional_string_field("format", other.format)
        self._prefer_optional_value_field("medium_count", other.medium_count)
        self.absorb_external_ids(other)
        self.absorb_sources(other)

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
        self.mark_changed("tracks")
        recording.mark_changed("releases")
        return t

    def move_tracks_to(self, new_release: Release) -> None:
        if new_release is self:
            return
        for track in list(self._tracks):
            internal.detach_release_track_from_release(self, track)
            internal.set_release_track_release(track, new_release)
            internal.attach_release_track_to_release(new_release, track)
            track.mark_changed("release")
        self.mark_changed("tracks")
        new_release.mark_changed("tracks")

    def adopt_track(
        self,
        track: ReleaseTrack,
        *,
        recording: Recording | None = None,
    ) -> ReleaseTrack:
        target_recording = track.recording if recording is None else recording
        if track.release is self and track.recording is target_recording:
            return track
        if track.release is not self:
            internal.detach_release_track_from_release(track.release, track)
            internal.set_release_track_release(track, self)
            internal.attach_release_track_to_release(self, track)
            track.mark_changed("release")
            self.mark_changed("tracks")
        if track.recording is not target_recording:
            internal.detach_release_track_from_recording(track.recording, track)
            internal.set_release_track_recording(track, target_recording)
            internal.attach_release_track_to_recording(target_recording, track)
            track.mark_changed("recording")
        return track

    def move_track_to_recording(self, track: ReleaseTrack, recording: Recording) -> None:
        if track.release is not self:
            raise ValueError("track not owned by this release")
        if track.recording is recording:
            return
        old_recording = track.recording
        internal.detach_release_track_from_recording(old_recording, track)
        internal.set_release_track_recording(track, recording)
        internal.attach_release_track_to_recording(recording, track)
        track.mark_changed("recording")

    def remove_track(self, track: ReleaseTrack) -> None:
        internal.detach_release_track_from_release(self, track)
        internal.detach_release_track_from_recording(track.recording, track)
        self.mark_changed("tracks")

    def add_label(self, label: Label) -> None:
        if label not in self._labels:
            self._labels.append(label)
            self.mark_changed("labels")

    def remove_label(self, label: Label) -> None:
        self._labels.remove(label)
        self.mark_changed("labels")


@dataclass(eq=False, kw_only=True)
class Recording(CanonicalEntity):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RECORDING

    title: str
    duration_ms: DurationMs | None = None
    version: str | None = None
    disambiguation: str | None = None
    aliases: list[str] = field(default_factory=list)

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

    def absorb(self, other: Recording) -> None:
        self._prefer_non_empty_string_field("title", other.title)
        self._prefer_optional_value_field("duration_ms", other.duration_ms)
        self._prefer_optional_string_field("version", other.version)
        self._prefer_optional_string_field("disambiguation", other.disambiguation)
        self._merge_unique_list_field("aliases", other.aliases)
        self.absorb_external_ids(other)
        self.absorb_sources(other)

    # Commands (ownership here)
    def add_artist(
        self,
        artist: Artist,
        *,
        role: ArtistRole = ArtistRole.PRIMARY,
        credit_order: int | None = None,
        credited_as: str | None = None,
        join_phrase: str | None = None,
    ) -> RecordingContribution:
        c = RecordingContribution(
            _recording=self,
            _artist=artist,
            role=role,
            credit_order=credit_order,
            credited_as=credited_as,
            join_phrase=join_phrase,
        )
        internal.attach_recording_contribution_to_recording(self, c)
        internal.attach_recording_contribution_to_artist(artist, c)
        self.mark_changed("contributions")
        artist.mark_changed("recordings")
        return c

    def move_contributions_to(self, new_recording: Recording) -> None:
        if new_recording is self:
            return
        for c in list(self._contributions):
            internal.detach_recording_contribution_from_recording(self, c)
            internal.set_recording_contribution_recording(c, new_recording)
            internal.attach_recording_contribution_to_recording(new_recording, c)
            c.mark_changed("recording")
        self.mark_changed("contributions")
        new_recording.mark_changed("contributions")

    def adopt_contribution(
        self,
        contribution: RecordingContribution,
        *,
        artist: Artist | None = None,
    ) -> RecordingContribution:
        target_artist = contribution.artist if artist is None else artist
        if contribution.recording is self and contribution.artist is target_artist:
            return contribution
        if contribution.recording is not self:
            internal.detach_recording_contribution_from_recording(
                contribution.recording,
                contribution,
            )
            internal.set_recording_contribution_recording(contribution, self)
            internal.attach_recording_contribution_to_recording(self, contribution)
            contribution.mark_changed("recording")
            self.mark_changed("contributions")
        if contribution.artist is not target_artist:
            internal.detach_recording_contribution_from_artist(
                contribution.artist,
                contribution,
            )
            internal.set_recording_contribution_artist(contribution, target_artist)
            internal.attach_recording_contribution_to_artist(target_artist, contribution)
            contribution.mark_changed("artist")
        return contribution

    def replace_artist(self, old: Artist, new: Artist) -> None:
        if old is new:
            return
        for c in list(self._contributions):
            if c.artist is not old:
                continue
            internal.detach_recording_contribution_from_artist(old, c)
            internal.set_recording_contribution_artist(c, new)
            internal.attach_recording_contribution_to_artist(new, c)
            c.mark_changed("artist")

    def remove_artist(self, artist: Artist) -> None:
        for c in list(self._contributions):
            if c.artist is artist:
                internal.detach_recording_contribution_from_recording(self, c)
                internal.detach_recording_contribution_from_artist(artist, c)
                self.mark_changed("contributions")
                artist.mark_changed("recordings")
                return
        raise ValueError("artist not linked to this recording")

    def move_tracks_to(self, new_recording: Recording) -> None:
        if new_recording is self:
            return
        for track in list(self._release_tracks):
            track.release.move_track_to_recording(track, new_recording)

    def move_play_event_to(self, event: PlayEvent, new_recording: Recording) -> None:
        event.user.move_play_event_to(event, new_recording)
