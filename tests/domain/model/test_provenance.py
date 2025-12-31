from __future__ import annotations

from sortipy.domain.model import Artist, Provenance, Provider


def test_provenance_is_optional_by_default() -> None:
    artist = Artist(name="Radiohead")
    assert artist.provenance is None


def test_add_source_creates_provenance_on_demand() -> None:
    artist = Artist(name="Radiohead")
    artist.add_source(Provider.LASTFM)

    assert artist.provenance is not None
    assert artist.provenance.sources == {Provider.LASTFM}


def test_set_provenance_sets_and_clears() -> None:
    artist = Artist(name="Radiohead")
    provenance = Provenance(sources={Provider.SPOTIFY})
    artist.set_provenance(provenance)

    current = artist.provenance
    assert current is provenance
    assert current is not None
    assert current.sources == {Provider.SPOTIFY}

    artist.set_provenance(None)
    assert artist.provenance is None


def test_ensure_provenance_recreates_after_clear() -> None:
    artist = Artist(name="Radiohead")
    artist.add_source(Provider.LASTFM)
    artist.set_provenance(None)

    provenance = artist.ensure_provenance()
    assert provenance is artist.provenance
    assert provenance.sources == set()
