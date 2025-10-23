"""Spotify adapter placeholder.

This module previously exposed helpers built around the legacy Album/Track domain
types. The canonical model has since moved to ReleaseSet/Release/Recording/Track,
so the Spotify ingestion flow needs a full rewrite before it can be re-enabled.

The implementation here intentionally raises ``NotImplementedError`` to surface
that gap explicitly while avoiding import-time crashes due to outdated domain
references. A follow-up task will rebuild the adapter against the new entities.
"""

from __future__ import annotations

from typing import Never


def fetch_spotify_saved_albums(*args, **kwargs) -> Never:  # type: ignore[unused-argument]  # noqa: ANN002, ANN003
    """Temporary stub for the Spotify saved-albums ingestion pipeline."""

    raise NotImplementedError("Spotify adapter pending rewrite for the new domain model")
