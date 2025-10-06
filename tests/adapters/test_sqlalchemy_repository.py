"""Exercise SQLAlchemy scrobble repository helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Never, cast

import pytest
from sqlalchemy.orm import Session

from sortipy.adapters.sqlalchemy import SqlAlchemyScrobbleRepository
from sortipy.domain.types import Artist


class _StubSession:
    """Minimal session stub that raises if database access occurs."""

    def execute(self, *_args: object, **_kwargs: object) -> Never:
        raise AssertionError("Session.execute should not be called")

    def get_one(self, *_args: object, **_kwargs: object) -> Never:
        raise AssertionError("Session.get_one should not be called")


@pytest.mark.parametrize(
    ("artist_name", "candidate_name"),
    [
        ("New Alias", "Stored Name"),
        ("Stored Name", "Stored Name"),
    ],
)
def test_complete_artist_reuses_candidate_when_mbid_matches(
    artist_name: str,
    candidate_name: str,
) -> None:
    repository = SqlAlchemyScrobbleRepository(cast(Session, _StubSession()))
    candidate = Artist(name=candidate_name, id=uuid.uuid4(), mbid="mbid-123")
    artist = Artist(name=artist_name, mbid="mbid-123")

    complete_artist = cast(
        Callable[[Artist, Artist | None], Artist],
        repository._complete_artist,  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    )
    result = complete_artist(artist, candidate)

    assert result is candidate
