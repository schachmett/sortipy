"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from sortipy.domain.ingest_pipeline import NormalizationSidecarRepository
from sortipy.domain.model import (
    Artist,
    IdentifiedEntity,
    Label,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    User,
)

from .mappings import (
    CLASS_BY_ENTITY_TYPE,
    ENTITY_TYPE_BY_CLASS,
    external_id_table,
    normalization_sidecar_table,
    play_event_table,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import InstrumentedAttribute, Session

    from sortipy.domain.ingest_pipeline import NormalizationData
    from sortipy.domain.model import (
        EntityType,
        LibraryItem,
        Namespace,
    )


class MissingParentError(Exception): ...


class SqlAlchemyPlayEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: PlayEvent) -> None:
        # Re-bind the owning user to this session. Detached user objects won't
        # populate the FK, and we explicitly avoid cascade persistence.
        attached_user = self._ensure_user_attached(entity.user)
        attached_user.rehydrate_play_event(entity)
        self._prepare_event(entity)
        self.session.add(entity)

    def exists(self, event: PlayEvent) -> bool:
        stmt = (
            select(PlayEvent)
            .where(play_event_table.c.user_id == event.user.id)
            .where(play_event_table.c.source == event.source)
            .where(play_event_table.c.played_at == event.played_at)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def latest_timestamp(self) -> datetime | None:
        played_at_column = cast("InstrumentedAttribute[datetime]", PlayEvent.played_at)
        stmt = select(played_at_column).order_by(played_at_column.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def _prepare_event(self, event: PlayEvent) -> None:
        _ = event

    def _ensure_user_attached(self, user: User) -> User:
        attached = self.session.get(User, user.id)
        if attached is None:
            raise MissingParentError(f"User {user.id} does not exist")
        return attached


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

    def list(self, *, limit: int | None = None) -> list[Recording]:
        stmt = select(Recording)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars())


class SqlAlchemyLabelRepository(SqlAlchemyCanonicalRepository[Label]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Label)


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: User) -> None:
        self.session.add(entity)

    def get(self, user_id: uuid.UUID) -> User | None:
        user = self.session.get(User, user_id)
        if user is None:
            return None
        return User(
            id=user.id,
            display_name=user.display_name,
            email=user.email,
            lastfm_user=user.lastfm_user,
            spotify_user_id=user.spotify_user_id,
        )


class SqlAlchemyLibraryItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: LibraryItem) -> None:
        attached = self.session.get(User, entity.user.id)
        if attached is None:
            raise MissingParentError(f"User {entity.user.id} does not exist")
        # Re-bind the owning user to this session. Detached user objects won't
        # populate the FK, and we explicitly avoid cascade persistence.
        attached.rehydrate_library_item(entity)
        self.session.add(entity)


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
        loaded = cast("list[object]", loaded_raw)
        return tuple(loaded)


if TYPE_CHECKING:
    from sortipy.domain.ports import (
        ArtistRepository,
        LibraryItemRepository,
        PlayEventRepository,
        RecordingRepository,
        ReleaseRepository,
        ReleaseSetRepository,
        UserRepository,
    )

    _session_stub = cast("Session", object())
    _repo_check: PlayEventRepository = SqlAlchemyPlayEventRepository(_session_stub)
    _artist_repo: ArtistRepository = SqlAlchemyArtistRepository(_session_stub)
    _release_set_repo: ReleaseSetRepository = SqlAlchemyReleaseSetRepository(_session_stub)
    _release_repo: ReleaseRepository = SqlAlchemyReleaseRepository(_session_stub)
    _recording_repo: RecordingRepository = SqlAlchemyRecordingRepository(_session_stub)
    _user_repo: UserRepository = SqlAlchemyUserRepository(_session_stub)
    _library_item_repo: LibraryItemRepository = SqlAlchemyLibraryItemRepository(_session_stub)
