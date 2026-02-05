from __future__ import annotations

from importlib import metadata

try:
    __version__ = metadata.version("sortipy")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0+local"
