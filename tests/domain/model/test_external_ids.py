from __future__ import annotations

from sortipy.domain.model import Artist, ExternalNamespace, Provider


def test_add_external_id_infers_provider_and_sets_owner_to_resolved_id() -> None:
    artist = Artist(name="Radiohead")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "spotify-1")

    (eid,) = artist.external_ids
    assert eid.namespace is ExternalNamespace.SPOTIFY_ARTIST
    assert eid.value == "spotify-1"
    assert eid.provider is Provider.SPOTIFY
    assert eid.owner_type == artist.entity_type
    assert eid.owner_id == artist.resolved_id


def test_add_external_id_uses_resolved_id_after_canonicalization() -> None:
    canonical = Artist(name="Radiohead")
    duplicate = Artist(name="Radiohead (dup)")
    duplicate.point_to_canonical(canonical)

    duplicate.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    (eid,) = duplicate.external_ids
    assert eid.owner_id == canonical.id


def test_replace_external_id_replaces_by_namespace() -> None:
    artist = Artist(name="Radiohead")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "spotify-1")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "spotify-2", replace=True)

    assert len(artist.external_ids) == 1
    assert artist.external_ids[0].value == "spotify-2"


def test_external_ids_by_namespace_is_last_write_wins() -> None:
    artist = Artist(name="Radiohead")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "spotify-1")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "spotify-2")

    mapping = artist.external_ids_by_namespace
    assert mapping[ExternalNamespace.SPOTIFY_ARTIST].value == "spotify-2"


def test_add_external_id_allows_custom_provider() -> None:
    artist = Artist(name="Radiohead")
    artist.add_external_id("custom:catalogue", "id-1", provider=Provider.LASTFM)

    (eid,) = artist.external_ids
    assert eid.namespace == "custom:catalogue"
    assert eid.provider is Provider.LASTFM
