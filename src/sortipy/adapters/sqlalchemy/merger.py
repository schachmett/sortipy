from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, TypeVar, cast

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, class_mapper

from sortipy.adapters.sqlalchemy.mappings import (
    CANONICAL_TYPE_BY_CLASS,
    external_id_table,
    track_table,
)
from sortipy.domain.types import (
    Artist,
    CanonicalEntity,
    CanonicalEntityType,
    Label,
    Recording,
    Release,
    ReleaseSet,
    Track,
    User,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

T = TypeVar("T", bound=CanonicalEntity)


class CanonicalEntityMerger:
    """Utility to deduplicate canonical entities before persistence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def merge_artist(self, artist: Artist) -> Artist:
        return cast(Artist, self._merge_canonical(artist, ()))

    def merge_release_set(self, release_set: ReleaseSet) -> ReleaseSet:
        for link in release_set.artists:
            link.artist = self.merge_artist(link.artist)
        merged = cast(ReleaseSet, self._merge_canonical(release_set, ()))
        existing_keys: set[tuple[uuid.UUID, str | None, int | None]] = set()
        for existing in merged.artists:
            artist = existing.artist
            if artist.id is not None:
                existing_keys.add((artist.id, existing.role, existing.credit_order))
        for link in release_set.artists:
            link.release_set = merged
            artist = link.artist
            if artist.id is not None:
                key = (artist.id, link.role, link.credit_order)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
            merged.artists.append(link)
        return merged

    def merge_label(self, label: Label) -> Label:
        return cast(Label, self._merge_canonical(label, ()))

    def merge_release(self, release: Release) -> Release:
        release_set = self.merge_release_set(release.release_set)
        release.release_set = release_set
        release.labels[:] = [self.merge_label(label) for label in release.labels]
        merged = cast(Release, self._merge_canonical(release, ()))
        merged.release_set = release_set
        return merged

    def merge_recording(self, recording: Recording) -> Recording:
        for link in recording.artists:
            link.artist = self.merge_artist(link.artist)
        merged = cast(Recording, self._merge_canonical(recording, ()))
        existing_keys: set[tuple[uuid.UUID, str | None, str | None, int | None]] = set()
        for existing in merged.artists:
            artist = existing.artist
            if artist.id is not None:
                existing_keys.add(
                    (artist.id, existing.role, existing.instrument, existing.credit_order)
                )
        for link in recording.artists:
            link.recording = merged
            artist = link.artist
            if artist.id is not None:
                key = (artist.id, link.role, link.instrument, link.credit_order)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
            merged.artists.append(link)
        return merged

    def merge_track(self, track: Track) -> Track:
        existing = None
        if track.id is not None:
            existing = self.session.get(Track, track.id)
        if existing is None and track.canonical_id is not None:
            existing = self.session.get(Track, track.canonical_id)
        if existing is None and track.release.id is not None and track.recording.id is not None:
            release_id_column = track_table.c.release_id
            recording_id_column = track_table.c.recording_id
            criteria = [
                release_id_column == track.release.id,
                recording_id_column == track.recording.id,
            ]
            if track.track_number is not None:
                criteria.append(track_table.c.track_number == track.track_number)
            stmt = select(Track).where(and_(*criteria))
            existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing

        if track.id is None:
            track.id = uuid.uuid4()
        self.session.add(track)
        return track

    def merge_user(self, user: User) -> User:
        if user.id is not None:
            existing = self.session.get(User, user.id)
            if existing is not None:
                return existing

        for column_name in ("spotify_user_id", "lastfm_user", "display_name"):
            value = getattr(user, column_name, None)
            if value:
                column = getattr(User, column_name)
                stmt = select(User).where(column == value)
                existing = self.session.execute(stmt).scalar_one_or_none()
                if existing is not None:
                    return existing

        if user.id is None:
            user.id = uuid.uuid4()
        self.session.add(user)
        return user

    def _merge_canonical(
        self,
        entity: CanonicalEntity | None,
        unique_fields: Sequence[str] = (),
    ) -> CanonicalEntity | None:
        if entity is None:
            return None

        entity_cls = type(entity)
        existing = self._existing_by_identity(entity, entity_cls)
        if existing is not None:
            self._merge_external_ids(entity, existing)
            return existing

        with self.session.no_autoflush:
            existing = self._lookup_by_external_ids(entity, entity_cls)
            if existing is not None:
                self._merge_external_ids(entity, existing)
                return existing

            existing = self._existing_by_unique_columns(entity, entity_cls, unique_fields)
            if existing is not None:
                self._merge_external_ids(entity, existing)
                return existing

        if entity.id is None:
            entity.id = uuid.uuid4()
        self.session.add(entity)
        return entity

    def _existing_by_identity(
        self,
        entity: CanonicalEntity,
        entity_cls: type[CanonicalEntity],
    ) -> CanonicalEntity | None:
        if entity.id is not None:
            existing = self.session.get(entity_cls, entity.id)
            if existing is not None:
                return existing
        if entity.canonical_id is not None:
            existing = self.session.get(entity_cls, entity.canonical_id)
            if existing is not None:
                return existing
        return None

    def _lookup_by_external_ids(
        self,
        entity: CanonicalEntity,
        entity_cls: type[CanonicalEntity],
    ) -> CanonicalEntity | None:
        if not entity.external_ids:
            return None
        entity_type: CanonicalEntityType = CANONICAL_TYPE_BY_CLASS[entity_cls]
        entity_id_column = external_id_table.c.entity_id
        for external_id in entity.external_ids:
            stmt = (
                select(entity_id_column)
                .where(external_id_table.c.namespace == external_id.namespace)
                .where(external_id_table.c.value == external_id.value)
                .where(external_id_table.c.entity_type == entity_type)
                .limit(1)
            )
            existing_id = self.session.execute(stmt).scalar_one_or_none()
            if isinstance(existing_id, uuid.UUID):
                return self.session.get(entity_cls, existing_id)
        return None

    def _existing_by_unique_columns(
        self,
        entity: CanonicalEntity,
        entity_cls: type[CanonicalEntity],
        unique_fields: Sequence[str],
    ) -> CanonicalEntity | None:
        if not unique_fields:
            return None
        mapper = class_mapper(entity_cls)
        for field in unique_fields:
            if field in mapper.columns:
                value = getattr(entity, field, None)
                if value:
                    column = mapper.columns[field]
                    stmt = select(entity_cls).where(column == value).limit(1)
                    existing = self.session.execute(stmt).scalar_one_or_none()
                    if existing is not None:
                        return existing
        return None

    @staticmethod
    def _merge_external_ids(source: CanonicalEntity, target: CanonicalEntity) -> None:
        existing = {(eid.namespace, eid.value) for eid in target.external_ids}
        for external_id in source.external_ids:
            key = (external_id.namespace, external_id.value)
            if key not in existing:
                target.external_ids.append(external_id)
                existing.add(key)
