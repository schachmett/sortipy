"""Entity ingestion pipeline scaffolding for Sortipy.

This package separates the ingestion pipeline into explicit, testable phases that
mirror the documentation in ``docs/data_pipeline.md``. Each phase operates on an
``IngestGraph`` and communicates through a shared ``PipelineContext`` so domain
rules remain explicit and adapter-free.
"""

from __future__ import annotations

from .context import NormalizationData
from .ingest_ports import (
    IngestionRepositories,
    IngestionUnitOfWork,
    LibraryItemSyncRepositories,
    LibraryItemSyncUnitOfWork,
    NormalizationSidecarRepository,
    PlayEventSyncRepositories,
    PlayEventSyncUnitOfWork,
)
from .runner import ingest_graph_from_events, ingest_graph_from_library_items, run_ingest_pipeline

__all__ = [
    "IngestionRepositories",
    "IngestionUnitOfWork",
    "LibraryItemSyncRepositories",
    "LibraryItemSyncUnitOfWork",
    "NormalizationData",
    "NormalizationSidecarRepository",
    "PlayEventSyncRepositories",
    "PlayEventSyncUnitOfWork",
    "ingest_graph_from_events",
    "ingest_graph_from_library_items",
    "run_ingest_pipeline",
]
