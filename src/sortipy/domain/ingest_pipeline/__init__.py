"""Entity ingestion pipeline scaffolding for Sortipy.

This package separates the ingestion pipeline into explicit, testable phases that
mirror the documentation in ``docs/data_pipeline.md``. Each phase operates on an
``IngestGraph`` and communicates through a shared ``PipelineContext`` so domain
rules remain explicit and adapter-free.
"""

from __future__ import annotations

from .canonicalization import CanonicalizationPhase
from .context import (
    EntityCounters,
    IngestGraph,
    NormalizationData,
    PipelineContext,
)
from .deduplication import DeduplicationPhase
from .ingest_ports import (
    IngestionRepositories,
    IngestionUnitOfWork,
    LibraryItemSyncRepositories,
    LibraryItemSyncUnitOfWork,
    NormalizationSidecarRepository,
    PlayEventSyncRepositories,
    PlayEventSyncUnitOfWork,
)
from .normalization import NormalizationPhase
from .orchestrator import (
    IngestionPipeline,
    ingest_graph_from_events,
    ingest_graph_from_library_items,
)

__all__ = [
    "CanonicalizationPhase",
    "DeduplicationPhase",
    "EntityCounters",
    "IngestGraph",
    "IngestionPipeline",
    "IngestionRepositories",
    "IngestionUnitOfWork",
    "LibraryItemSyncRepositories",
    "LibraryItemSyncUnitOfWork",
    "NormalizationData",
    "NormalizationPhase",
    "NormalizationSidecarRepository",
    "PipelineContext",
    "PlayEventSyncRepositories",
    "PlayEventSyncUnitOfWork",
    "ingest_graph_from_events",
    "ingest_graph_from_library_items",
]
