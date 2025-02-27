"""Common domain types used throughout the application."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Album:
    """Represents a Spotify album with essential metadata."""

    release_date: str
    title: str
    artists: str

    def __str__(self) -> str:
        """Return a formatted string representation of the album."""
        return f"{self.release_date} - {self.title} - {self.artists}"
