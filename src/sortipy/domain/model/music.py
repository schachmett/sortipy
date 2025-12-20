"""Music domain entities (canonical). Ownership lives on aggregate roots.

Aggregate roots here:
- ReleaseSet owns ReleaseSetContribution + Releases (1:n)
- Recording owns RecordingContribution
- Release owns ReleaseTrack + labels link
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from sortipy.domain.model.associations import (
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
)
from sortipy.domain.model.entity import CanonicalizableMixin
from sortipy.domain.model.enums import ArtistRole, EntityType
from sortipy.domain.model.external_ids import ExternallyIdentifiableMixin
from sortipy.domain.model.provenance import ProvenanceTrackedMixin

if TYPE_CHECKING:
    from sortipy.domain.model.enums import ReleaseSetType
    from sortipy.domain.model.primitives import CountryCode, DurationMs, PartialDate
    from sortipy.domain.model.user import PlayEvent


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

    # Friend primitives (called only by owners)
    def _attach_release_set_contribution(self, c: ReleaseSetContribution) -> None:
        self._release_set_contributions.append(c)

    def _detach_release_set_contribution(self, c: ReleaseSetContribution) -> None:
        self._release_set_contributions.remove(c)

    def _attach_recording_contribution(self, c: RecordingContribution) -> None:
        self._recording_contributions.append(c)

    def _detach_recording_contribution(self, c: RecordingContribution) -> None:
        self._recording_contributions.remove(c)


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
    def _add_release(self, release: Release) -> None:
        if release.release_set is not self:
            # keep graph consistent
            release._set_release_set(self)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        self._releases.append(release)

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
        self._add_release(release)
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
        self._contributions.append(c)
        artist._attach_release_set_contribution(c)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        return c

    def remove_artist(self, artist: Artist) -> None:
        for c in list(self._contributions):
            if c.artist is artist:
                self._contributions.remove(c)
                artist._detach_release_set_contribution(c)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
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

    def _set_release_set(self, rs: ReleaseSet) -> None:
        self._release_set = rs

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
        self._tracks.append(t)
        recording._attach_release_track(t)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        return t

    def remove_track(self, track: ReleaseTrack) -> None:
        self._tracks.remove(track)
        track.recording._detach_release_track(track)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

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

    # Backrefs for user events (owned by PlayEvent)
    _play_events: list[PlayEvent] = field(default_factory=list["PlayEvent"], repr=False)

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

    @property
    def play_events(self) -> tuple[PlayEvent, ...]:
        return tuple(self._play_events)

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
        self._contributions.append(c)
        artist._attach_recording_contribution(c)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        return c

    def remove_artist(self, artist: Artist) -> None:
        for c in list(self._contributions):
            if c.artist is artist:
                self._contributions.remove(c)
                artist._detach_recording_contribution(c)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
                return
        raise ValueError("artist not linked to this recording")

    # Friend primitives
    def _attach_release_track(self, rt: ReleaseTrack) -> None:
        self._release_tracks.append(rt)

    def _detach_release_track(self, rt: ReleaseTrack) -> None:
        self._release_tracks.remove(rt)

    def _attach_play_event(self, pe: PlayEvent) -> None:
        self._play_events.append(pe)

    def _detach_play_event(self, pe: PlayEvent) -> None:
        self._play_events.remove(pe)
