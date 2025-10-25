"""SQLAlchemy mapping metadata for the Sortipy domain model."""

from __future__ import annotations

import logging
import uuid
from functools import cache
from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    and_,
    func,
    orm,
)
from sqlalchemy.orm import composite, configure_mappers, relationship

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

from sortipy.domain.types import (
    Artist,
    CanonicalEntity,
    CanonicalEntityType,
    EntityMerge,
    ExternalID,
    Label,
    LibraryItem,
    MergeReason,
    PartialDate,
    PlayEvent,
    Provider,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    ReleaseSetType,
    Track,
    User,
)

UUIDColumnType = Uuid[uuid.UUID]

log = logging.getLogger(__name__)

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
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("canonical_id", UUIDColumnType, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
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
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("canonical_id", UUIDColumnType, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("name", String, nullable=False),
    Column("country", String(3), nullable=True),
)

release_set_table = Table(
    "release_set",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("canonical_id", UUIDColumnType, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
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
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("canonical_id", UUIDColumnType, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("title", String, nullable=False),
    Column("release_set_id", UUIDColumnType, ForeignKey("release_set.id"), nullable=False),
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

release_set_artist_table = Table(
    "release_set_artist",
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
    Column("role", String, nullable=True),
    Column("credit_order", Integer, nullable=True),
)

recording_table = Table(
    "recording",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("canonical_id", UUIDColumnType, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("title", String, nullable=False),
    Column("duration_ms", Integer, nullable=True),
    Column("version", String, nullable=True),
)

recording_artist_table = Table(
    "recording_artist",
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
    Column("role", String, nullable=True),
    Column("instrument", String, nullable=True),
    Column("credit_order", Integer, nullable=True),
)

track_table = Table(
    "track",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("canonical_id", UUIDColumnType, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("release_id", UUIDColumnType, ForeignKey("release.id"), nullable=False),
    Column("recording_id", UUIDColumnType, ForeignKey("recording.id"), nullable=False),
    Column("disc_number", Integer, nullable=True),
    Column("track_number", Integer, nullable=True),
    Column("title_override", String, nullable=True),
    Column("duration_ms", Integer, nullable=True),
)

user_table = Table(
    "user_account",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("display_name", String, nullable=False),
    Column("email", String, nullable=True),
    Column("spotify_user_id", String, nullable=True),
    Column("lastfm_user", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

library_item_table = Table(
    "library_item",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column(
        "user_id", UUIDColumnType, ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    ),
    Column("entity_type", Enum(CanonicalEntityType, native_enum=False), nullable=False),
    Column("entity_id", UUIDColumnType, nullable=False),
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("source", Enum(Provider, native_enum=False), nullable=True),
    Column("saved_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_library_item_entity"),
)

play_event_table = Table(
    "play_event",
    mapper_registry.metadata,
    Column("played_at", DateTime(timezone=True), primary_key=True),
    Column("raw_payload_id", UUIDColumnType, nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("source", Enum(Provider, native_enum=False), nullable=False),
    Column("recording_id", UUIDColumnType, ForeignKey("recording.id"), nullable=False),
    Column("track_id", UUIDColumnType, ForeignKey("track.id"), nullable=True),
    Column("user_id", UUIDColumnType, ForeignKey("user_account.id"), nullable=True),
    Column("duration_ms", Integer, nullable=True),
)

entity_merge_table = Table(
    "entity_merge",
    mapper_registry.metadata,
    Column("entity_type", Enum(CanonicalEntityType, native_enum=False), primary_key=True),
    Column("source_id", UUIDColumnType, primary_key=True),
    Column("target_id", UUIDColumnType, primary_key=True),
    Column("reason", Enum(MergeReason, native_enum=False), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("created_by", String, nullable=True),
)

external_id_table = Table(
    "external_id",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("namespace", String, nullable=False),
    Column("value", String, nullable=False),
    Column("entity_type", Enum(CanonicalEntityType, native_enum=False), nullable=False),
    Column("entity_id", UUIDColumnType, nullable=False),
    Column("provider", Enum(Provider, native_enum=False), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True, server_default=func.now()),
    UniqueConstraint("namespace", "value", "entity_type"),
)

CANONICAL_TYPE_BY_CLASS: Final[dict[type[CanonicalEntity], CanonicalEntityType]] = {
    Artist: CanonicalEntityType.ARTIST,
    ReleaseSet: CanonicalEntityType.RELEASE_SET,
    Release: CanonicalEntityType.RELEASE,
    Recording: CanonicalEntityType.RECORDING,
    Track: CanonicalEntityType.TRACK,
    Label: CanonicalEntityType.LABEL,
}

CLASS_BY_CANONICAL_TYPE: Final[dict[CanonicalEntityType, type[CanonicalEntity]]] = {
    value: key for key, value in CANONICAL_TYPE_BY_CLASS.items()
}


def _external_ids_relationship(
    entity_table: Table, entity_type: CanonicalEntityType
) -> orm.RelationshipProperty[ExternalID]:
    return relationship(
        ExternalID,
        cascade="all, delete-orphan",
        primaryjoin=and_(
            external_id_table.c.entity_id == entity_table.c.id,
            external_id_table.c.entity_type == entity_type,
        ),
        foreign_keys=[external_id_table.c.entity_id],
        overlaps="external_ids",
    )


@cache
def start_mappers() -> orm.registry:
    """Configure SQLAlchemy mappers for the domain model."""

    log.info("Starting SQLAlchemy mappers")

    mapper_registry.map_imperatively(
        Artist,
        artist_table,
        properties={
            "external_ids": _external_ids_relationship(artist_table, CanonicalEntityType.ARTIST),
        },
        exclude_properties={"sources", "release_sets", "recordings"},
    )

    mapper_registry.map_imperatively(
        ReleaseSet,
        release_set_table,
        properties={
            "external_ids": _external_ids_relationship(
                release_set_table,
                CanonicalEntityType.RELEASE_SET,
            ),
            "releases": relationship(
                Release,
                back_populates="release_set",
                cascade="all, delete-orphan",
            ),
            "artists": relationship(
                ReleaseSetArtist,
                back_populates="release_set",
                cascade="all, delete-orphan",
            ),
            "first_release": composite(
                PartialDate,
                release_set_table.c.first_release_year,
                release_set_table.c.first_release_month,
                release_set_table.c.first_release_day,
            ),
        },
        exclude_properties={"sources"},
    )

    mapper_registry.map_imperatively(
        ReleaseSetArtist,
        release_set_artist_table,
        properties={
            "release_set": relationship(
                ReleaseSet,
                back_populates="artists",
            ),
            "artist": relationship(Artist),
        },
    )

    mapper_registry.map_imperatively(
        Label,
        label_table,
        properties={
            "external_ids": _external_ids_relationship(
                label_table,
                CanonicalEntityType.LABEL,
            ),
            "releases": relationship(
                Release,
                secondary=release_label_table,
                back_populates="labels",
            ),
        },
        exclude_properties={"sources"},
    )

    mapper_registry.map_imperatively(
        Release,
        release_table,
        properties={
            "external_ids": _external_ids_relationship(
                release_table,
                CanonicalEntityType.RELEASE,
            ),
            "release_set": relationship(
                ReleaseSet,
                back_populates="releases",
            ),
            "release_date": composite(
                PartialDate,
                release_table.c.release_year,
                release_table.c.release_month,
                release_table.c.release_day,
            ),
            "labels": relationship(
                Label,
                secondary=release_label_table,
                back_populates="releases",
            ),
            "tracks": relationship(
                Track,
                back_populates="release",
                cascade="all, delete-orphan",
            ),
        },
        exclude_properties={"sources"},
    )

    mapper_registry.map_imperatively(
        Recording,
        recording_table,
        properties={
            "external_ids": _external_ids_relationship(
                recording_table,
                CanonicalEntityType.RECORDING,
            ),
            "tracks": relationship(
                Track,
                back_populates="recording",
                cascade="all, delete-orphan",
            ),
            "play_events": relationship(
                PlayEvent,
                back_populates="recording",
                cascade="all, delete-orphan",
            ),
            "artists": relationship(
                RecordingArtist,
                back_populates="recording",
                cascade="all, delete-orphan",
            ),
        },
        exclude_properties={"sources"},
    )

    mapper_registry.map_imperatively(
        RecordingArtist,
        recording_artist_table,
        properties={
            "recording": relationship(
                Recording,
                back_populates="artists",
            ),
            "artist": relationship(Artist),
        },
    )

    mapper_registry.map_imperatively(
        Track,
        track_table,
        properties={
            "external_ids": _external_ids_relationship(
                track_table,
                CanonicalEntityType.TRACK,
            ),
            "release": relationship(
                Release,
                back_populates="tracks",
            ),
            "recording": relationship(
                Recording,
                back_populates="tracks",
            ),
            "play_events": relationship(
                PlayEvent,
                back_populates="track",
                cascade="all, delete-orphan",
            ),
        },
        exclude_properties={"sources"},
    )

    mapper_registry.map_imperatively(
        LibraryItem,
        library_item_table,
        properties={
            # ``entity_type``/``entity_id`` carry the polymorphic reference; ``entity`` stays
            # an optional in-memory convenience resolved by higher layers as needed.
            "user": relationship(
                User,
                back_populates="library_items",
            ),
            "entity_type": library_item_table.c.entity_type,
            "entity_id": library_item_table.c.entity_id,
        },
        exclude_properties={"entity"},
    )

    mapper_registry.map_imperatively(
        PlayEvent,
        play_event_table,
        properties={
            "recording": relationship(
                Recording,
                back_populates="play_events",
            ),
            "track": relationship(
                Track,
                back_populates="play_events",
            ),
            "user": relationship(User),
        },
    )

    mapper_registry.map_imperatively(
        User,
        user_table,
        properties={
            "library_items": relationship(
                LibraryItem,
                back_populates="user",
                cascade="all, delete-orphan",
            ),
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

    configure_mappers()
    return mapper_registry


def create_all_tables(engine: Engine) -> None:
    """Create database tables for the mapped metadata."""

    log.info("Creating all tables")
    mapper_registry.metadata.create_all(engine)

