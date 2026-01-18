"""Synchronization defaults for ingest services."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PLAY_EVENT_BATCH_SIZE = 200
DEFAULT_LIBRARY_ITEM_BATCH_SIZE = 50


@dataclass(frozen=True, slots=True)
class SyncConfig:
    play_event_batch_size: int = DEFAULT_PLAY_EVENT_BATCH_SIZE
    library_item_batch_size: int = DEFAULT_LIBRARY_ITEM_BATCH_SIZE


def get_sync_config() -> SyncConfig:
    return SyncConfig()
