"""SQLAlchemy mapping metadata for the Sortipy domain model."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from functools import cache
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import (
    Column,
    DateTime,
    Dialect,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
    and_,
    func,
    orm,
)
from sqlalchemy.orm import composite, configure_mappers, relationship

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    EntityMerge,
    EntityType,
    ExternalID,
    IdentifiedEntity,
    Label,
    LibraryItem,
    MergeReason,
    PartialDate,
    PlayEvent,
    Provenance,
    Provider,
    Recording,
    RecordingContribution,
    Release,
    ReleaseSet,
    ReleaseSetContribution,
    ReleaseSetType,
    ReleaseTrack,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

UUIDColumnType = Uuid[uuid.UUID]


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        _ = dialect
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        _ = dialect
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class ProviderSetType(TypeDecorator[set[Provider]]):
    impl = String
    cache_ok = True

    def process_bind_param(self, value: set[Provider] | None, dialect: Dialect) -> str | None:
        _ = dialect
        if value is None:
            return None
        payload = sorted(source.value for source in value)
        return json.dumps(payload)

    def process_result_value(self, value: str | None, dialect: Dialect) -> set[Provider]:
        _ = dialect
        if value is None:
            return set()
        loaded = json.loads(value)
        if not isinstance(loaded, list):
            return set()
        items = cast(list[Any], loaded)
        providers: set[Provider] = set()
        for item in items:
            if isinstance(item, str):
                providers.add(Provider(item))
        return providers


mapper_registry = orm.registry()
mapper_registry.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_label)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_label)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Core tables -----------------------------------------------------------------

artist_table = Table(
    "artist",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("canonical_id", UUIDColumnType, key="_canonical_id", nullable=True),
    Column("name", String, nullable=False),
    Column("sort_name", String, nullable=True),
    Column("country", String(3), nullable=True),
    Column("formed_year", Integer, nullable=True),
    Column("disbanded_year", Integer, nullable=True),
)

label_table = Table(
    "label",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("canonical_id", UUIDColumnType, key="_canonical_id", nullable=True),
    Column("name", String, nullable=False),
    Column("country", String(3), nullable=True),
)

release_set_table = Table(
    "release_set",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("canonical_id", UUIDColumnType, key="_canonical_id", nullable=True),
    Column("title", String, nullable=False),
    Column("primary_type", Enum(ReleaseSetType, native_enum=False), nullable=True),
    Column("first_release_year", Integer, nullable=True),
    Column("first_release_month", Integer, nullable=True),
    Column("first_release_day", Integer, nullable=True),
)

release_table = Table(
    "release",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("canonical_id", UUIDColumnType, key="_canonical_id", nullable=True),
    Column("title", String, nullable=False),
    Column(
        "release_set_id",
        UUIDColumnType,
        ForeignKey("release_set.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("release_year", Integer, nullable=True),
    Column("release_month", Integer, nullable=True),
    Column("release_day", Integer, nullable=True),
    Column("country", String(3), nullable=True),
    Column("format", String, nullable=True),
    Column("medium_count", Integer, nullable=True),
)

release_label_table = Table(
    "release_label",
    mapper_registry.metadata,
    Column(
        "release_id", UUIDColumnType, ForeignKey("release.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "label_id", UUIDColumnType, ForeignKey("label.id", ondelete="CASCADE"), primary_key=True
    ),
)

release_set_contribution_table = Table(
    "release_set_contribution",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "release_set_id",
        UUIDColumnType,
        ForeignKey("release_set.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "artist_id", UUIDColumnType, ForeignKey("artist.id", ondelete="CASCADE"), nullable=False
    ),
    Column("role", Enum(ArtistRole, native_enum=False), nullable=True),
    Column("credit_order", Integer, nullable=True),
    Column("credited_as", String, nullable=True),
    Column("join_phrase", String, nullable=True),
)

recording_table = Table(
    "recording",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("canonical_id", UUIDColumnType, key="_canonical_id", nullable=True),
    Column("title", String, nullable=False),
    Column("duration_ms", Integer, nullable=True),
    Column("version", String, nullable=True),
)

recording_contribution_table = Table(
    "recording_contribution",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "recording_id",
        UUIDColumnType,
        ForeignKey("recording.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "artist_id", UUIDColumnType, ForeignKey("artist.id", ondelete="CASCADE"), nullable=False
    ),
    Column("role", Enum(ArtistRole, native_enum=False), nullable=True),
    Column("instrument", String, nullable=True),
    Column("credit_order", Integer, nullable=True),
    Column("credited_as", String, nullable=True),
)

release_track_table = Table(
    "release_track",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "release_id",
        UUIDColumnType,
        ForeignKey("release.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "recording_id",
        UUIDColumnType,
        ForeignKey("recording.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("disc_number", Integer, nullable=True),
    Column("track_number", Integer, nullable=True),
    Column("title_override", String, nullable=True),
    Column("duration_ms", Integer, nullable=True),
)

user_table = Table(
    "user_account",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("display_name", String, nullable=False),
    Column("email", String, nullable=True),
    Column("spotify_user_id", String, nullable=True),
    Column("lastfm_user", String, nullable=True),
)

library_item_table = Table(
    "library_item",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "user_id", UUIDColumnType, ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    ),
    Column("target_type", Enum(EntityType, native_enum=False), key="_target_type", nullable=False),
    Column("target_id", UUIDColumnType, key="_target_id", nullable=False),
    Column("source", Enum(Provider, native_enum=False), nullable=True),
    Column("saved_at", UTCDateTime(), nullable=True),
    UniqueConstraint("user_id", "_target_type", "_target_id", name="uq_library_item_entity"),
)

play_event_table = Table(
    "play_event",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "user_id", UUIDColumnType, ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    ),
    Column("played_at", UTCDateTime(), nullable=False),
    Column("source", Enum(Provider, native_enum=False), nullable=False),
    Column("track_id", UUIDColumnType, ForeignKey("release_track.id"), nullable=True),
    Column("recording_id", UUIDColumnType, ForeignKey("recording.id"), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    UniqueConstraint("user_id", "source", "played_at", name="uq_play_event_identity"),
)

entity_merge_table = Table(
    "entity_merge",
    mapper_registry.metadata,
    Column("entity_type", Enum(EntityType, native_enum=False), primary_key=True),
    Column("source_id", UUIDColumnType, primary_key=True),
    Column("target_id", UUIDColumnType, primary_key=True),
    Column("reason", Enum(MergeReason, native_enum=False), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False, server_default=func.now()),
    Column("created_by", String, nullable=True),
)

external_id_table = Table(
    "external_id",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("namespace", String, nullable=False),
    Column("value", String, nullable=False),
    Column(
        "owner_type",
        Enum(EntityType, native_enum=False),
        key="_owner_type",
        nullable=False,
    ),
    Column("owner_id", UUIDColumnType, key="_owner_id", nullable=False),
    Column("provider", Enum(Provider, native_enum=False), nullable=True),
    Column("created_at", UTCDateTime(), nullable=True, server_default=func.now()),
    UniqueConstraint("namespace", "value", "_owner_type"),
    Index("ix_external_id_owner", "_owner_type", "_owner_id"),
)

provenance_table = Table(
    "provenance",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "owner_type",
        Enum(EntityType, native_enum=False),
        key="_owner_type",
        nullable=False,
    ),
    Column("owner_id", UUIDColumnType, key="_owner_id", nullable=False),
    Column("sources", ProviderSetType(), nullable=False, default=set),
    UniqueConstraint("_owner_type", "_owner_id"),
    Index("ix_provenance_owner", "_owner_type", "_owner_id"),
)

ENTITY_TYPE_BY_CLASS: Final[dict[type[IdentifiedEntity], EntityType]] = {
    Artist: EntityType.ARTIST,
    ReleaseSet: EntityType.RELEASE_SET,
    Release: EntityType.RELEASE,
    Recording: EntityType.RECORDING,
    ReleaseTrack: EntityType.RELEASE_TRACK,
    Label: EntityType.LABEL,
}

CLASS_BY_ENTITY_TYPE: Final[dict[EntityType, type[IdentifiedEntity]]] = {
    value: key for key, value in ENTITY_TYPE_BY_CLASS.items()
}


def _external_ids_relationship(
    entity_table: Table, entity_type: EntityType
) -> orm.RelationshipProperty[ExternalID]:
    return relationship(
        ExternalID,
        cascade="all, delete-orphan",
        primaryjoin=and_(
            external_id_table.c._owner_id == entity_table.c.id,  # noqa: SLF001
            external_id_table.c._owner_type == entity_type,  # noqa: SLF001
        ),
        foreign_keys=[external_id_table.c._owner_id],  # noqa: SLF001
        overlaps="_external_ids",
    )


def _provenance_relationship(
    entity_table: Table, entity_type: EntityType
) -> orm.RelationshipProperty[Provenance]:
    return relationship(
        Provenance,
        cascade="all, delete-orphan",
        primaryjoin=and_(
            provenance_table.c._owner_id == entity_table.c.id,  # noqa: SLF001
            provenance_table.c._owner_type == entity_type,  # noqa: SLF001
        ),
        foreign_keys=[provenance_table.c._owner_id],  # noqa: SLF001
        uselist=False,
        single_parent=True,
        overlaps="_provenance",
    )


@cache
def start_mappers() -> orm.registry:
    """Configure SQLAlchemy mappers for the domain model."""

    log.info("Starting SQLAlchemy mappers")

    mapper_registry.map_imperatively(
        Artist,
        artist_table,
        properties={
            "_external_ids": _external_ids_relationship(artist_table, EntityType.ARTIST),
            "_provenance": _provenance_relationship(artist_table, EntityType.ARTIST),
            "_release_set_contributions": relationship(
                ReleaseSetContribution,
                back_populates="_artist",
            ),
            "_recording_contributions": relationship(
                RecordingContribution,
                back_populates="_artist",
            ),
        },
    )

    mapper_registry.map_imperatively(
        ReleaseSet,
        release_set_table,
        properties={
            "_external_ids": _external_ids_relationship(
                release_set_table,
                EntityType.RELEASE_SET,
            ),
            "_provenance": _provenance_relationship(release_set_table, EntityType.RELEASE_SET),
            "_releases": relationship(
                Release,
                back_populates="_release_set",
                cascade="all, delete-orphan",
            ),
            "_contributions": relationship(
                ReleaseSetContribution,
                back_populates="_release_set",
                cascade="all, delete-orphan",
            ),
            "first_release": composite(
                PartialDate,
                release_set_table.c.first_release_year,
                release_set_table.c.first_release_month,
                release_set_table.c.first_release_day,
            ),
        },
    )

    mapper_registry.map_imperatively(
        ReleaseSetContribution,
        release_set_contribution_table,
        properties={
            "_release_set": relationship(
                ReleaseSet,
                back_populates="_contributions",
            ),
            "_artist": relationship(
                Artist,
                back_populates="_release_set_contributions",
            ),
            "_provenance": _provenance_relationship(
                release_set_contribution_table,
                EntityType.RELEASE_SET_CONTRIBUTION,
            ),
        },
    )

    mapper_registry.map_imperatively(
        RecordingContribution,
        recording_contribution_table,
        properties={
            "_recording": relationship(
                Recording,
                back_populates="_contributions",
            ),
            "_artist": relationship(
                Artist,
                back_populates="_recording_contributions",
            ),
            "_provenance": _provenance_relationship(
                recording_contribution_table,
                EntityType.RECORDING_CONTRIBUTION,
            ),
        },
    )

    mapper_registry.map_imperatively(
        Label,
        label_table,
        properties={
            "_external_ids": _external_ids_relationship(label_table, EntityType.LABEL),
            "_provenance": _provenance_relationship(label_table, EntityType.LABEL),
        },
    )

    mapper_registry.map_imperatively(
        Release,
        release_table,
        properties={
            "_external_ids": _external_ids_relationship(release_table, EntityType.RELEASE),
            "_provenance": _provenance_relationship(release_table, EntityType.RELEASE),
            "_release_set": relationship(
                ReleaseSet,
                back_populates="_releases",
            ),
            "release_date": composite(
                PartialDate,
                release_table.c.release_year,
                release_table.c.release_month,
                release_table.c.release_day,
            ),
            "_labels": relationship(
                Label,
                secondary=release_label_table,
            ),
            "_tracks": relationship(
                ReleaseTrack,
                back_populates="_release",
                cascade="all, delete-orphan",
            ),
        },
    )

    mapper_registry.map_imperatively(
        Recording,
        recording_table,
        properties={
            "_external_ids": _external_ids_relationship(
                recording_table,
                EntityType.RECORDING,
            ),
            "_provenance": _provenance_relationship(recording_table, EntityType.RECORDING),
            "_contributions": relationship(
                RecordingContribution,
                back_populates="_recording",
                cascade="all, delete-orphan",
            ),
            "_release_tracks": relationship(
                ReleaseTrack,
                back_populates="_recording",
            ),
        },
    )

    mapper_registry.map_imperatively(
        ReleaseTrack,
        release_track_table,
        properties={
            "_external_ids": _external_ids_relationship(
                release_track_table,
                EntityType.RELEASE_TRACK,
            ),
            "_provenance": _provenance_relationship(
                release_track_table,
                EntityType.RELEASE_TRACK,
            ),
            "_release": relationship(
                Release,
                back_populates="_tracks",
            ),
            "_recording": relationship(
                Recording,
                back_populates="_release_tracks",
            ),
        },
    )

    mapper_registry.map_imperatively(
        LibraryItem,
        library_item_table,
        properties={
            "_user": relationship(
                User,
                back_populates="_library_items",
            ),
            "_provenance": _provenance_relationship(library_item_table, EntityType.LIBRARY_ITEM),
        },
        exclude_properties={"_target"},
    )

    mapper_registry.map_imperatively(
        PlayEvent,
        play_event_table,
        properties={
            "_user": relationship(
                User,
                back_populates="_play_events",
            ),
            "_track": relationship(
                ReleaseTrack,
                foreign_keys=[play_event_table.c.track_id],
            ),
            "_recording_ref": relationship(
                Recording,
                foreign_keys=[play_event_table.c.recording_id],
            ),
            "_provenance": _provenance_relationship(play_event_table, EntityType.PLAY_EVENT),
        },
    )

    mapper_registry.map_imperatively(
        User,
        user_table,
        properties={
            "_library_items": relationship(
                LibraryItem,
                back_populates="_user",
                cascade="all, delete-orphan",
            ),
            "_play_events": relationship(
                PlayEvent,
                back_populates="_user",
                cascade="all, delete-orphan",
            ),
            "_provenance": _provenance_relationship(user_table, EntityType.USER),
        },
    )

    mapper_registry.map_imperatively(
        EntityMerge,
        entity_merge_table,
    )

    mapper_registry.map_imperatively(
        ExternalID,
        external_id_table,
    )

    mapper_registry.map_imperatively(
        Provenance,
        provenance_table,
    )

    configure_mappers()
    return mapper_registry


def create_all_tables(engine: Engine) -> None:
    """Create database tables for the mapped metadata."""

    log.info("Creating all tables")
    mapper_registry.metadata.create_all(engine)
