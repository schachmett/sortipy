"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from sortipy.adapters.sqlalchemy.mappings import (
    CANONICAL_TYPE_BY_CLASS,
    CLASS_BY_CANONICAL_TYPE,
    external_id_table,
)
from sortipy.adapters.sqlalchemy.sidecar_mappings import normalization_sidecar_table
from sortipy.domain.ingest_pipeline.ingest_ports import NormalizationSidecarRepository
from sortipy.domain.types import (
    Artist,
    CanonicalEntity,
    CanonicalEntityType,
    Label,
    Namespace,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    Track,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import InstrumentedAttribute, Session

    from sortipy.domain.ingest_pipeline.state import NormalizationData


class SqlAlchemyPlayEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: PlayEvent) -> None:
        self._prepare_event(entity)
        self.session.add(entity)

    def exists(self, timestamp: datetime) -> bool:
        played_at_column = cast("InstrumentedAttribute[datetime]", PlayEvent.played_at)
        stmt = select(PlayEvent).where(played_at_column == timestamp)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def latest_timestamp(self) -> datetime | None:
        played_at_column = cast("InstrumentedAttribute[datetime]", PlayEvent.played_at)
        stmt = select(played_at_column).order_by(played_at_column.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def _prepare_event(self, event: PlayEvent) -> None:
        _ = event


class SqlAlchemyCanonicalRepository[TCanonical: CanonicalEntity]:
    """Shared helpers for repositories managing canonical catalog entities."""

    def __init__(self, session: Session, entity_cls: type[TCanonical]) -> None:
        self.session = session
        self._entity_cls = entity_cls
        self._entity_type = CANONICAL_TYPE_BY_CLASS[entity_cls]

    def add(self, entity: TCanonical) -> None:
        self.session.add(entity)

    def get_by_external_id(self, namespace: Namespace, value: str) -> TCanonical | None:
        stmt = (
            select(external_id_table.c.entity_id)
            .where(external_id_table.c.namespace == namespace)
            .where(external_id_table.c.value == value)
            .where(external_id_table.c.entity_type == self._entity_type)
            .limit(1)
        )
        entity_id = self.session.execute(stmt).scalar_one_or_none()
        if not isinstance(entity_id, uuid.UUID):
            return None
        return self.session.get(self._entity_cls, entity_id)


class SqlAlchemyArtistRepository(SqlAlchemyCanonicalRepository[Artist]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Artist)


class SqlAlchemyReleaseSetRepository(SqlAlchemyCanonicalRepository[ReleaseSet]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ReleaseSet)


class SqlAlchemyReleaseRepository(SqlAlchemyCanonicalRepository[Release]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Release)


class SqlAlchemyRecordingRepository(SqlAlchemyCanonicalRepository[Recording]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Recording)


class SqlAlchemyTrackRepository(SqlAlchemyCanonicalRepository[Track]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Track)


class SqlAlchemyLabelRepository(SqlAlchemyCanonicalRepository[Label]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Label)


class SqlAlchemyNormalizationSidecarRepository(NormalizationSidecarRepository):
    """Persist and query normalization sidecars for canonicalization."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, entity: CanonicalEntity, data: NormalizationData[CanonicalEntity]) -> None:
        if not data.priority_keys:
            return
        if entity.id is None:
            entity.id = uuid.uuid4()
        for key in data.priority_keys:
            self._insert(entity.entity_type, entity.id, key)

    def find_by_keys(
        self,
        entity_type: CanonicalEntityType,
        keys: tuple[tuple[object, ...], ...],
    ) -> dict[tuple[object, ...], CanonicalEntity]:
        if not keys:
            return {}
        key_strings = [self._serialize_key(key) for key in keys]
        stmt = (
            select(normalization_sidecar_table.c.key, normalization_sidecar_table.c.entity_id)
            .where(normalization_sidecar_table.c.entity_type == entity_type)
            .where(normalization_sidecar_table.c.key.in_(key_strings))
        )
        rows = self.session.execute(stmt).all()
        entity_cls = CLASS_BY_CANONICAL_TYPE[entity_type]
        results: dict[tuple[object, ...], CanonicalEntity] = {}
        for key_str, entity_id in rows:
            entity_obj = self.session.get(entity_cls, entity_id)
            if entity_obj is None:
                continue
            try:
                key_tuple = self._deserialize_key(key_str)
            except ValueError:
                continue
            results[key_tuple] = entity_obj
        return results

    def _insert(
        self,
        entity_type: CanonicalEntityType,
        entity_id: uuid.UUID,
        key: tuple[object, ...],
    ) -> None:
        key_str = self._serialize_key(key)
        stmt = (
            normalization_sidecar_table.insert()
            .prefix_with("OR IGNORE")
            .values(
                entity_type=entity_type,
                entity_id=entity_id,
                key=key_str,
            )
        )
        self.session.execute(stmt)

    @staticmethod
    def _serialize_key(key: tuple[object, ...]) -> str:
        return json.dumps(key, default=str, separators=(",", ":"))

    @staticmethod
    def _deserialize_key(value: str) -> tuple[object, ...]:
        loaded_raw = json.loads(value)
        if not isinstance(loaded_raw, list):
            raise TypeError("Invalid key format")
        loaded = cast(list[object], loaded_raw)
        return tuple(loaded)


if TYPE_CHECKING:
    from sortipy.domain.ports.persistence import (
        ArtistRepository,
        PlayEventRepository,
        RecordingRepository,
        ReleaseRepository,
        ReleaseSetRepository,
        TrackRepository,
    )

    _session_stub = cast("Session", object())
    _repo_check: PlayEventRepository = SqlAlchemyPlayEventRepository(_session_stub)
    _artist_repo: ArtistRepository = SqlAlchemyArtistRepository(_session_stub)
    _release_set_repo: ReleaseSetRepository = SqlAlchemyReleaseSetRepository(_session_stub)
    _release_repo: ReleaseRepository = SqlAlchemyReleaseRepository(_session_stub)
    _recording_repo: RecordingRepository = SqlAlchemyRecordingRepository(_session_stub)
    _track_repo: TrackRepository = SqlAlchemyTrackRepository(_session_stub)
