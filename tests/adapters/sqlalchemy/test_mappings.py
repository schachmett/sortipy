from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Table, func, insert, inspect, select

from sortipy.adapters.sqlalchemy import create_all_tables, start_mappers
from sortipy.adapters.sqlalchemy.mappings import (
    artist_table,
    external_id_table,
    label_table,
    library_item_table,
    play_event_table,
    provenance_table,
    recording_contribution_table,
    recording_table,
    release_label_table,
    release_set_contribution_table,
    release_set_table,
    release_table,
    release_track_table,
    user_table,
)
from sortipy.domain.model import (
    Artist,
    ArtistRole,
    EntityType,
    ExternalNamespace,
    Label,
    Provider,
    Recording,
    ReleaseSet,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session


def test_start_mappers_is_idempotent() -> None:
    # First invocation happens in the sqlite_engine fixture; calling again should be harmless.
    start_mappers()
    start_mappers()


def test_create_all_tables_registers_core_tables(sqlite_engine: Engine) -> None:
    create_all_tables(sqlite_engine)
    inspector = inspect(sqlite_engine)
    table_names = set(inspector.get_table_names())
    for required in ("artist", "recording", "release", "play_event"):
        assert required in table_names


def test_mappings_round_trip_entity_graph(sqlite_session: Session) -> None:
    def _row_count(table: Table) -> int:
        return sqlite_session.execute(select(func.count()).select_from(table)).scalar_one()

    artist = Artist(name="Radiohead")
    artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-artist-1")
    artist.add_source(Provider.MUSICBRAINZ)

    release_set = ReleaseSet(title="OK Computer")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    release_set.add_source(Provider.MUSICBRAINZ)

    release = release_set.create_release(title="OK Computer")
    recording = Recording(title="Paranoid Android", duration_ms=387000)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)

    track = release.add_track(recording, track_number=2, disc_number=1)
    track.add_external_id(ExternalNamespace.MUSICBRAINZ_RECORDING, "mbid-track-1")

    label = Label(name="Parlophone")
    release.add_label(label)

    user = User(display_name="Ada")
    user.add_source(Provider.LASTFM)
    user.save_entity(artist, source=Provider.LASTFM)
    user.log_play(
        played_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        duration_ms=387000,
    )

    sqlite_session.add_all([artist, release_set, recording, label, user])
    sqlite_session.commit()

    assert _row_count(artist_table) == 1
    assert _row_count(release_set_table) == 1
    assert _row_count(release_table) == 1
    assert _row_count(release_track_table) == 1
    assert _row_count(recording_table) == 1
    assert _row_count(label_table) == 1
    assert _row_count(release_label_table) == 1
    assert _row_count(external_id_table) == 2
    assert _row_count(provenance_table) == 3

    sqlite_session.expire_all()
    loaded_release_set = sqlite_session.get(ReleaseSet, release_set.id)
    assert loaded_release_set is not None
    assert loaded_release_set.releases[0].tracks[0].recording.title == "Paranoid Android"
    assert loaded_release_set.artists[0].name == "Radiohead"


def test_mappings_load_entity_graph_from_core(sqlite_session: Session) -> None:
    artist_id = uuid4()
    release_set_id = uuid4()
    release_id = uuid4()
    recording_id = uuid4()
    track_id = uuid4()
    label_id = uuid4()
    user_id = uuid4()
    library_item_id = uuid4()
    play_event_id = uuid4()

    def _insert_row(table: Table, **values: object) -> None:
        sqlite_session.execute(insert(table).values(values))

    _insert_row(artist_table, id=artist_id, name="Massive Attack")
    _insert_row(release_set_table, id=release_set_id, title="Mezzanine")
    _insert_row(
        release_set_contribution_table,
        id=uuid4(),
        release_set_id=release_set_id,
        artist_id=artist_id,
        role=ArtistRole.PRIMARY,
    )
    _insert_row(release_table, id=release_id, title="Mezzanine", release_set_id=release_set_id)
    _insert_row(recording_table, id=recording_id, title="Teardrop")
    _insert_row(
        recording_contribution_table,
        id=uuid4(),
        recording_id=recording_id,
        artist_id=artist_id,
        role=ArtistRole.PRIMARY,
    )
    _insert_row(
        release_track_table,
        id=track_id,
        release_id=release_id,
        recording_id=recording_id,
        track_number=1,
    )
    _insert_row(label_table, id=label_id, name="Virgin")
    _insert_row(release_label_table, release_id=release_id, label_id=label_id)
    _insert_row(user_table, id=user_id, display_name="Listener")
    _insert_row(
        library_item_table,
        id=library_item_id,
        user_id=user_id,
        _target_type=EntityType.ARTIST,
        _target_id=artist_id,
        source=Provider.LASTFM,
        saved_at=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
    )
    _insert_row(
        play_event_table,
        id=play_event_id,
        user_id=user_id,
        played_at=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        source=Provider.LASTFM,
        recording_id=recording_id,
    )
    _insert_row(
        external_id_table,
        id=uuid4(),
        namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
        value="mbid-artist-2",
        _owner_type=EntityType.ARTIST,
        _owner_id=artist_id,
        provider=Provider.MUSICBRAINZ,
    )
    _insert_row(
        provenance_table,
        id=uuid4(),
        _owner_type=EntityType.RELEASE_SET,
        _owner_id=release_set_id,
        sources={Provider.MUSICBRAINZ, Provider.LASTFM},
    )
    sqlite_session.commit()

    artist = sqlite_session.get(Artist, artist_id)
    assert artist is not None
    assert artist.external_ids[0].value == "mbid-artist-2"
    assert artist.release_sets[0].title == "Mezzanine"

    release_set = sqlite_session.get(ReleaseSet, release_set_id)
    assert release_set is not None
    assert release_set.provenance is not None
    assert Provider.MUSICBRAINZ in release_set.provenance.sources

    user = sqlite_session.get(User, user_id)
    assert user is not None
    assert user.library_items[0].target_type == EntityType.ARTIST
    assert user.play_events[0].recording.title == "Teardrop"
