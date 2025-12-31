"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from sortipy.adapters.sqlalchemy.mappings import (
    CLASS_BY_ENTITY_TYPE,
    ENTITY_TYPE_BY_CLASS,
    external_id_table,
    play_event_table,
)
from sortipy.adapters.sqlalchemy.sidecar_mappings import normalization_sidecar_table
from sortipy.domain.ingest_pipeline.ingest_ports import NormalizationSidecarRepository
from sortipy.domain.model import (
    Artist,
    EntityType,
    IdentifiedEntity,
    Label,
    Namespace,
    PlayEvent,
    Provider,
    Recording,
    Release,
    ReleaseSet,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import InstrumentedAttribute, Session

    from sortipy.domain.ingest_pipeline.context import NormalizationData


class SqlAlchemyPlayEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: PlayEvent) -> None:
        self._prepare_event(entity)
        self.session.add(entity)

    def exists(self, *, user_id: uuid.UUID, source: Provider, played_at: datetime) -> bool:
        stmt = (
            select(PlayEvent)
            .where(play_event_table.c.user_id == user_id)
            .where(play_event_table.c.source == source)
            .where(play_event_table.c.played_at == played_at)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def latest_timestamp(self) -> datetime | None:
        played_at_column = cast("InstrumentedAttribute[datetime]", PlayEvent.played_at)
        stmt = select(played_at_column).order_by(played_at_column.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def _prepare_event(self, event: PlayEvent) -> None:
        _ = event


class SqlAlchemyCanonicalRepository[TEntity: IdentifiedEntity]:
    """Shared helpers for repositories managing catalog entities with external IDs."""

    def __init__(self, session: Session, entity_cls: type[TEntity]) -> None:
        self.session = session
        self._entity_cls = entity_cls
        self._entity_type = ENTITY_TYPE_BY_CLASS[entity_cls]

    def add(self, entity: TEntity) -> None:
        self.session.add(entity)

    def get_by_external_id(self, namespace: Namespace, value: str) -> TEntity | None:
        stmt = (
            select(external_id_table.c._owner_id)  # noqa: SLF001
            .where(external_id_table.c.namespace == namespace)
            .where(external_id_table.c.value == value)
            .where(external_id_table.c._owner_type == self._entity_type)  # noqa: SLF001
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


class SqlAlchemyLabelRepository(SqlAlchemyCanonicalRepository[Label]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Label)


class SqlAlchemyNormalizationSidecarRepository(NormalizationSidecarRepository):
    """Persist and query normalization sidecars for canonicalization."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, entity: IdentifiedEntity, data: NormalizationData[IdentifiedEntity]) -> None:
        if not data.priority_keys:
            return
        for key in data.priority_keys:
            self._insert(entity.entity_type, entity.resolved_id, key)

    def find_by_keys(
        self,
        entity_type: EntityType,
        keys: tuple[tuple[object, ...], ...],
    ) -> dict[tuple[object, ...], IdentifiedEntity]:
        if not keys:
            return {}
        key_strings = [self._serialize_key(key) for key in keys]
        stmt = (
            select(normalization_sidecar_table.c.key, normalization_sidecar_table.c.entity_id)
            .where(normalization_sidecar_table.c.entity_type == entity_type)
            .where(normalization_sidecar_table.c.key.in_(key_strings))
        )
        rows = self.session.execute(stmt).all()
        entity_cls = CLASS_BY_ENTITY_TYPE.get(entity_type)
        if entity_cls is None:
            return {}
        results: dict[tuple[object, ...], IdentifiedEntity] = {}
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
        entity_type: EntityType,
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
    )

    _session_stub = cast("Session", object())
    _repo_check: PlayEventRepository = SqlAlchemyPlayEventRepository(_session_stub)
    _artist_repo: ArtistRepository = SqlAlchemyArtistRepository(_session_stub)
    _release_set_repo: ReleaseSetRepository = SqlAlchemyReleaseSetRepository(_session_stub)
    _release_repo: ReleaseRepository = SqlAlchemyReleaseRepository(_session_stub)
    _recording_repo: RecordingRepository = SqlAlchemyRecordingRepository(_session_stub)
