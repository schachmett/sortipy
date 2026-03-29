"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, ClassVar, cast

from sqlalchemy import select
from sqlalchemy.orm import attributes, object_session

from sortipy.domain.model import (
    Artist,
    Label,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    ReleaseTrack,
    User,
)
from sortipy.domain.ports.persistence import (
    ExternalIdRedirectRepository,
    MutationRepository,
    NormalizationSidecarRepository,
)

from .mappings import (
    CLASS_BY_ENTITY_TYPE,
    ENTITY_TYPE_BY_CLASS,
    external_id_redirect_table,
    external_id_table,
    library_item_table,
    normalization_sidecar_table,
    play_event_table,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import InstrumentedAttribute, Session

    from sortipy.domain.model import (
        Entity,
        EntityType,
        IdentifiedEntity,
        LibraryItem,
        Namespace,
        Provider,
    )
    from sortipy.domain.ports.persistence import PriorityKeysData


class MissingParentError(Exception): ...


type _CanonicalEntity = Artist | Label | ReleaseSet | Release | Recording


def _serialize_normalized_key(key: tuple[object, ...]) -> str:
    return json.dumps(key, default=str, separators=(",", ":"))


def _deserialize_normalized_key(value: str) -> tuple[object, ...]:
    loaded_raw = json.loads(value)
    if not isinstance(loaded_raw, list):
        raise TypeError("Invalid key format")
    loaded = cast("list[object]", loaded_raw)
    return tuple(loaded)


class SqlAlchemyPlayEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: PlayEvent) -> None:
        # Re-bind the event and its catalog references into this session before
        # flush so SQLAlchemy does not need to infer transient relationship state.
        with self.session.no_autoflush:
            self.session.add(entity)
            attached_user = self._ensure_user_attached(entity.user)
            attached_user.rehydrate_play_event(entity)
            self._prepare_event(entity, user=attached_user)

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

    def _prepare_event(self, event: PlayEvent, *, user: User) -> None:
        if event.track is not None:
            attached_track = self._ensure_track_attached(event.track)
            user.rebind_play_event(
                event,
                recording=attached_track.recording,
                track=attached_track,
            )
            return

        recording_ref = event.recording_ref
        if recording_ref is None:
            raise ValueError("play event requires a recording reference when track is absent")
        attached_recording = self._ensure_recording_attached(recording_ref)
        user.rebind_play_event(
            event,
            recording=attached_recording,
            track=None,
        )

    def _ensure_user_attached(self, user: User) -> User:
        if object_session(user) is self.session:
            return user
        attached = self.session.get(User, user.id)
        if attached is None:
            raise MissingParentError(f"User {user.id} does not exist")
        return attached

    def _ensure_track_attached(self, track: ReleaseTrack) -> ReleaseTrack:
        if object_session(track) is self.session:
            return track
        attached = self.session.get(ReleaseTrack, track.id)
        if attached is None:
            raise MissingParentError(f"ReleaseTrack {track.id} does not exist")
        return attached

    def _ensure_recording_attached(self, recording: Recording) -> Recording:
        if object_session(recording) is self.session:
            return recording
        attached = self.session.get(Recording, recording.id)
        if attached is None:
            raise MissingParentError(f"Recording {recording.id} does not exist")
        return attached


class SqlAlchemyCanonicalRepository[TEntity: _CanonicalEntity]:
    """Shared helpers for repositories managing catalog entities with external IDs."""

    def __init__(self, session: Session, entity_cls: type[TEntity]) -> None:
        self.session = session
        self._entity_cls = entity_cls
        self._entity_type = ENTITY_TYPE_BY_CLASS[entity_cls]

    def add(self, entity: TEntity) -> None:
        self.session.add(entity)

    def get_by_external_id(self, namespace: Namespace, value: str) -> TEntity | None:
        in_session = self._find_in_session_by_external_id(namespace, value)
        if in_session is not None:
            return in_session
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

    def _find_in_session_by_external_id(self, namespace: Namespace, value: str) -> TEntity | None:
        attached = tuple(self.session.identity_map.values()) + tuple(self.session.new)
        for entity in attached:
            if not isinstance(entity, self._entity_cls):
                continue
            entry = entity.external_ids_by_namespace.get(namespace)
            if entry is None or entry.value != value:
                continue
            return entity
        return None


class SqlAlchemyArtistRepository(SqlAlchemyCanonicalRepository[Artist]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Artist)


class SqlAlchemyReleaseSetRepository(SqlAlchemyCanonicalRepository[ReleaseSet]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ReleaseSet)


class SqlAlchemyReleaseRepository(SqlAlchemyCanonicalRepository[Release]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Release)

    def list(self, *, limit: int | None = None) -> list[Release]:
        stmt = select(Release)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars())


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

    def exists(
        self,
        *,
        user_id: uuid.UUID,
        target_type: EntityType,
        target_id: uuid.UUID,
    ) -> bool:
        stmt = (
            select(library_item_table.c.id)
            .where(library_item_table.c.user_id == user_id)
            .where(library_item_table.c._target_type == target_type)  # noqa: SLF001
            .where(library_item_table.c._target_id == target_id)  # noqa: SLF001
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None


class SqlAlchemyExternalIdRedirectRepository(ExternalIdRedirectRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_redirect(
        self,
        namespace: Namespace,
        source_value: str,
        target_value: str,
        *,
        provider: Provider | None = None,
    ) -> None:
        if source_value == target_value:
            return
        stmt = (
            select(external_id_redirect_table.c.id)
            .where(external_id_redirect_table.c.namespace == str(namespace))
            .where(external_id_redirect_table.c.source_value == source_value)
            .limit(1)
        )
        existing_id = self.session.execute(stmt).scalar_one_or_none()
        if isinstance(existing_id, uuid.UUID):
            self.session.execute(
                external_id_redirect_table.update()
                .where(external_id_redirect_table.c.id == existing_id)
                .values(target_value=target_value, provider=provider)
            )
            return
        self.session.execute(
            external_id_redirect_table.insert().values(
                namespace=str(namespace),
                source_value=source_value,
                target_value=target_value,
                provider=provider,
            )
        )

    def resolve(self, namespace: Namespace, value: str) -> str | None:
        current_value = value
        visited = {value}
        while True:
            stmt = (
                select(external_id_redirect_table.c.target_value)
                .where(external_id_redirect_table.c.namespace == str(namespace))
                .where(external_id_redirect_table.c.source_value == current_value)
                .limit(1)
            )
            redirected = self.session.execute(stmt).scalar_one_or_none()
            if not isinstance(redirected, str):
                return None if current_value == value else current_value
            if redirected in visited:
                return None if current_value == value else current_value
            visited.add(redirected)
            current_value = redirected


class SqlAlchemyMutationRepository(MutationRepository):
    """Adapter for explicitly marking attached objects dirty before commit."""

    _FIELD_ATTRIBUTE_MAP: ClassVar[dict[type[object], dict[str, tuple[str, ...]]]] = {
        Artist: {
            "areas": ("areas",),
            "aliases": ("aliases",),
        },
        ReleaseSet: {
            "secondary_types": ("secondary_types",),
            "aliases": ("aliases",),
        },
        Recording: {
            "aliases": ("aliases",),
        },
    }

    _RELATIONSHIP_ONLY_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "external_ids",
            "release_set",
            "releases",
            "tracks",
            "contributions",
            "labels",
            "artist",
            "recording",
            "user",
            "target",
            "release_sets",
            "recordings",
            "library_items",
            "play_events",
            "track",
        }
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def attach_created(self, entity: Entity) -> None:
        attached_session = object_session(entity)
        if attached_session is self.session:
            return
        if attached_session is not None and attached_session is not self.session:
            raise ValueError(
                f"Cannot attach foreign-session entity {type(entity).__name__} as created"
            )
        self.session.add(entity)

    def update(self, entity: Entity, *, changed_fields: frozenset[str]) -> None:
        if not changed_fields:
            return
        attached_session = object_session(entity)
        if attached_session is None or attached_session is not self.session:
            raise ValueError(
                f"Cannot persist detached or foreign-session entity {type(entity).__name__}"
            )

        for changed_field in changed_fields:
            self._mark_field_dirty(entity, changed_field)

    def _mark_field_dirty(self, entity: Entity, changed_field: str) -> None:
        if changed_field == "provenance":
            self._mark_provenance_dirty(entity)
            return
        if changed_field in self._RELATIONSHIP_ONLY_FIELDS:
            return

        field_map = self._FIELD_ATTRIBUTE_MAP.get(type(entity), {})
        attribute_names = field_map.get(changed_field)
        if attribute_names is None:
            # Scalar assignments and composite replacements are already tracked by
            # SQLAlchemy. Explicit flagging is only needed for in-place mutation of
            # custom-typed container fields and provenance sources.
            return
        for attribute_name in attribute_names:
            attributes.flag_modified(entity, attribute_name)

    def _mark_provenance_dirty(self, entity: Entity) -> None:
        provenance = getattr(entity, "provenance", None)
        if provenance is None:
            return
        attached_session = object_session(provenance)
        if attached_session is not self.session:
            return
        attributes.flag_modified(provenance, "sources")


class SqlAlchemyNormalizationSidecarRepository(NormalizationSidecarRepository):
    """Persist and query normalization sidecars for canonicalization."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, entity: IdentifiedEntity, data: PriorityKeysData) -> None:
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
        key_strings = [_serialize_normalized_key(key) for key in keys]
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
                key_tuple = _deserialize_normalized_key(key_str)
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
        key_str = _serialize_normalized_key(key)
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


if TYPE_CHECKING:
    from sortipy.domain.ports import (
        ArtistRepository,
        LabelRepository,
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
    _label_repo: LabelRepository = SqlAlchemyLabelRepository(_session_stub)
    _release_set_repo: ReleaseSetRepository = SqlAlchemyReleaseSetRepository(_session_stub)
    _release_repo: ReleaseRepository = SqlAlchemyReleaseRepository(_session_stub)
    _recording_repo: RecordingRepository = SqlAlchemyRecordingRepository(_session_stub)
    _user_repo: UserRepository = SqlAlchemyUserRepository(_session_stub)
    _library_item_repo: LibraryItemRepository = SqlAlchemyLibraryItemRepository(_session_stub)
    _mutation_repo: MutationRepository = SqlAlchemyMutationRepository(_session_stub)
