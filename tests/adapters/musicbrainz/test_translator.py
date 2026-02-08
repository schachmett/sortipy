"""Translator checks for MusicBrainz releases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.adapters.musicbrainz.translator import translate_release
from sortipy.domain.model import ArtistRole, ExternalNamespace

if TYPE_CHECKING:
    from sortipy.adapters.musicbrainz.schema import MBArtistCredit, MBRelease


def test_translate_release_roles(releases: list[MBRelease]) -> None:
    for release in releases:
        update = translate_release(release)
        mbid = next(
            ext.value
            for ext in update.external_ids
            if ext.namespace == ExternalNamespace.MUSICBRAINZ_RELEASE
        )
        assert mbid == release.id

        if release.release_group is None or not release.release_group.artist_credit:
            continue

        release_set = update.release_set
        assert release_set is not None
        assert len(release_set.contributions) == len(release.release_group.artist_credit)

        expected_roles = _expected_roles(release.release_group.artist_credit)
        for credit, expected in zip(release_set.contributions, expected_roles, strict=True):
            assert credit.role is expected
            assert credit.credit_order is not None
            original = release.release_group.artist_credit[credit.credit_order]
            if original.name != original.artist.name:
                assert credit.credited_as == original.name
            else:
                assert credit.credited_as is None


def _expected_roles(credits_: list[MBArtistCredit]) -> list[ArtistRole]:
    roles: list[ArtistRole] = []
    prev_join: str | None = None
    for index, credit in enumerate(credits_):
        if index == 0:
            roles.append(ArtistRole.PRIMARY)
        elif _is_featuring(prev_join):
            roles.append(ArtistRole.FEATURED)
        else:
            roles.append(ArtistRole.UNKNOWN)
        prev_join = credit.join_phrase
    return roles


def _is_featuring(join_phrase: str | None) -> bool:
    if join_phrase is None:
        return False
    lowered = join_phrase.lower()
    return "feat" in lowered or "ft." in lowered
