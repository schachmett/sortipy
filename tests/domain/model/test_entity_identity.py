from __future__ import annotations

import uuid

import pytest

from sortipy.domain.model import Artist, EntityType, Label


def test_canonicalizable_defaults_to_canonical() -> None:
    artist = Artist(name="Radiohead")
    assert artist.is_canonical is True
    assert artist.canonical_id is None
    assert artist.resolved_id == artist.id


def test_point_to_canonical_sets_pointer_and_resolves() -> None:
    canonical = Artist(name="Radiohead")
    duplicate = Artist(name="Radiohead (dup)")

    duplicate.point_to_canonical(canonical)

    assert duplicate.is_canonical is False
    assert duplicate.canonical_id == canonical.id
    assert duplicate.resolved_id == canonical.id


def test_point_to_canonical_normalizes_self_pointer_to_none() -> None:
    duplicate = Artist(name="Radiohead (dup)")
    duplicate.point_to_canonical(duplicate)

    assert duplicate.is_canonical is True
    assert duplicate.canonical_id is None
    assert duplicate.resolved_id == duplicate.id


def test_point_to_canonical_requires_same_entity_type() -> None:
    artist = Artist(name="Radiohead")
    label = Label(name="XL")

    with pytest.raises(ValueError, match="same entity_type"):
        artist.point_to_canonical(label)


def test_point_to_canonical_accepts_any_entity_ref_of_same_type() -> None:
    # A minimal EntityRef-like object (not an Entity).
    class _ArtistRef:
        entity_type = EntityType.ARTIST
        resolved_id = uuid.uuid4()

    duplicate = Artist(name="Radiohead (dup)")
    duplicate.point_to_canonical(_ArtistRef())
    assert duplicate.canonical_id == _ArtistRef.resolved_id


def test_clear_canonical_resets_pointer() -> None:
    canonical = Artist(name="Radiohead")
    duplicate = Artist(name="Radiohead (dup)")
    duplicate.point_to_canonical(canonical)

    duplicate.clear_canonical()

    assert duplicate.is_canonical is True
    assert duplicate.canonical_id is None
    assert duplicate.resolved_id == duplicate.id
