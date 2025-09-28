"""
SQLAlchemy mappings for the domain model
sql.func.now() uses UTC for sqlite databases
-> see https://www.sqlite.org/lang_datefunc.html
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    orm,
    select,
)
from sqlalchemy import engine as sa_engine
from sqlalchemy.orm import Session, configure_mappers, relationship

from sortipy.common.repository import Repository
from sortipy.domain.data_integration import ScrobbleRepository
from sortipy.domain.types import Album, Artist, Scrobble, Track

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

log = logging.getLogger(__name__)


mapper_registry = orm.registry()
mapper_registry.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_label)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_label)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

lastfm_artist_table = Table(
    "lastfm_artist",
    mapper_registry.metadata,
    Column("id", Uuid, primary_key=True, default=uuid.uuid4),  # type: ignore[reportUnknownArgumentType]
    Column("mbid", String, unique=True),
    Column("name", String, nullable=False, unique=True),
    Column("playcount", Integer),
)

lastfm_album_table = Table(
    "lastfm_album",
    mapper_registry.metadata,
    Column("id", Uuid, primary_key=True, default=uuid.uuid4),  # type: ignore[reportUnknownArgumentType]
    Column("mbid", String, unique=True),
    Column("name", String, nullable=False),
    Column("artist_id", Uuid, ForeignKey("lastfm_artist.id")),  # type: ignore[reportUnknownArgumentType]
    UniqueConstraint("name", "artist_id"),
    Column("playcount", Integer),
)

lastfm_track_table = Table(
    "lastfm_track",
    mapper_registry.metadata,
    Column("id", Uuid, primary_key=True, default=uuid.uuid4),  # type: ignore[reportUnknownArgumentType]
    Column("name", String, nullable=False, unique=True),
    Column("mbid", String, unique=True),
    Column("artist_id", Uuid, ForeignKey("lastfm_artist.id")),  # type: ignore[reportUnknownArgumentType]
    Column("album_id", Uuid, ForeignKey("lastfm_album.id")),  # type: ignore[reportUnknownArgumentType]
    UniqueConstraint("name", "artist_id", "album_id"),
    Column("playcount", Integer),
)

lastfm_scrobble_table = Table(
    "lastfm_scrobble",
    mapper_registry.metadata,
    Column("timestamp", DateTime, primary_key=True, nullable=False),
    Column("track_id", Uuid, ForeignKey("lastfm_track.id")),  # type: ignore[reportUnknownArgumentType]
)


def start_mappers() -> orm.registry:
    """Start the mappers."""
    if getattr(start_mappers, "_started", False):
        return mapper_registry
    log.info("Starting mappers")
    mapper_registry.map_imperatively(
        Artist,
        lastfm_artist_table,
        exclude_properties={"sources"},
    )
    mapper_registry.map_imperatively(
        Album,
        lastfm_album_table,
        properties={
            "artist": relationship(Artist, backref="albums"),
        },
        exclude_properties={"sources"},
    )
    mapper_registry.map_imperatively(
        Track,
        lastfm_track_table,
        properties={
            "artist": relationship(Artist, backref="tracks"),
            "album": relationship(Album, backref="tracks"),
        },
        exclude_properties={"sources"},
    )
    mapper_registry.map_imperatively(
        Scrobble,
        lastfm_scrobble_table,
        properties={
            "track": relationship(Track, backref="scrobbles"),
        },
        exclude_properties={"provider"},
    )
    configure_mappers()
    start_mappers.__dict__["_started"] = True
    return mapper_registry


def create_all_tables(engine: sa_engine.Engine) -> None:
    """Create all tables."""
    log.info("Creating all tables")
    mapper_registry.metadata.create_all(engine)


class SQLAlchemyRepository[T](Repository[T]):
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: T) -> None:
        self.session.add(item)

    def remove(self, item: T) -> None:
        self.session.delete(item)

    def update(self, item: T) -> None:
        self.session.merge(item)


class SqlAlchemyScrobbleRepository(ScrobbleRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def _complete_artist(
        self, artist: Artist, candidate: Artist | None = None
    ) -> Artist:
        # if we have an id, we can use it to complete the artist
        if artist.id is not None:
            if candidate is not None and candidate.id == artist.id:
                return candidate
            artist_db = self.session.get_one(Artist, artist.id)
            if artist_db.mbid != artist.mbid or artist_db.name != artist.name:
                raise ValueError(f"Artist {artist.id} has changed")
            return artist_db

        # if we have a candidate, we can use it to complete the artist
        if (
            candidate is not None
            and candidate.id is not None
            and ((artist.mbid == candidate.mbid is not None) or artist.name == candidate.name)
        ):
            artist = candidate

        # if we don't have a candidate, we need to find the artist in the database
        else:
            if artist.mbid is not None:
                stmt = select(Artist).where(Artist.mbid == artist.mbid)  # type: ignore[arg-type]
            else:
                stmt = select(Artist).where(Artist.name == artist.name)  # type: ignore[arg-type]
            artist_db = self.session.execute(stmt).scalar_one_or_none()
            if artist_db is not None:
                artist = artist_db

        # if artist not in self.session:
        #     self.session.add(artist)
        return artist

    def _complete_album(self, album: Album) -> Album:
        if album.id is not None:
            album_db = self.session.get_one(Album, album.id)
            if (
                album_db.mbid != album.mbid
                or album_db.name != album.name
                or album_db.artist.id != album.artist.id
            ):
                raise ValueError(f"Album {album.id} has changed")
            return album_db

        if album.mbid is not None:
            stmt = select(Album).where(Album.mbid == album.mbid)  # type: ignore[arg-type]
        else:
            stmt = select(Album).where(
                (Album.name == album.name) & (Album.artist_id == album.artist.id)  # type: ignore[arg-type]
            )
        album_db = self.session.execute(stmt).scalar_one_or_none()
        if album_db is not None:
            album = album_db
        # if album not in self.session:
        #     self.session.add(album)
        return album

    def _complete_track(self, track: Track) -> Track:
        if track.id is not None:
            track_db = self.session.get_one(Track, track.id)
            if (
                track_db.mbid != track.mbid
                or track_db.name != track.name
                or track_db.artist.id != track.artist.id
                or track_db.album.id != track.album.id
            ):
                raise ValueError(f"Track {track.id} has changed")
            return track_db

        if track.mbid is not None:
            stmt = select(Track).where(Track.mbid == track.mbid)  # type: ignore[arg-type]
        else:
            stmt = select(Track).where(
                (Track.name == track.name)  # type: ignore[arg-type]
                & (Track.artist_id == track.artist.id)  # type: ignore[arg-type]
                & (Track.album_id == track.album.id)  # type: ignore[arg-type]
            )
        track_db = self.session.execute(stmt).scalar_one_or_none()
        if track_db is not None:
            track = track_db
        # if track not in self.session:
        #     self.session.add(track)
        return track

    def add(self, scrobble: Scrobble) -> None:
        # with self.session.no_autoflush:
        artist = self._complete_artist(scrobble.track.artist)
        scrobble.track.artist = artist
        album_artist = self._complete_artist(scrobble.track.album.artist, artist)
        scrobble.track.album.artist = album_artist
        album = self._complete_album(scrobble.track.album)
        scrobble.track.album = album
        track = self._complete_track(scrobble.track)
        scrobble.track = track

        self.session.add(scrobble)
        # self.session.flush()

    def get(self, key: str) -> Scrobble:
        stmt = select(Scrobble).where(Scrobble.timestamp == key)  # type: ignore[arg-type]
        scrobble = self.session.execute(stmt).scalar_one_or_none()
        if scrobble is None:
            raise ValueError(f"Scrobble with timestamp {key} not found")
        return scrobble

    def query(self, **kwargs: object) -> Sequence[Scrobble]:
        stmt = select(Scrobble).filter_by(**kwargs)
        return self.session.execute(stmt).scalars().all()

    def exists(self, timestamp: datetime) -> bool:
        stmt = select(lastfm_scrobble_table.c.timestamp).where(
            lastfm_scrobble_table.c.timestamp == timestamp
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def latest_timestamp(self) -> datetime | None:
        stmt = (
            select(lastfm_scrobble_table.c.timestamp)
            .order_by(lastfm_scrobble_table.c.timestamp.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()
