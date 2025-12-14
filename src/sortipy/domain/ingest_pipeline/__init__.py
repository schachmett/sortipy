"""Entity ingestion pipeline scaffolding for Sortipy.

This package separates the ingestion pipeline into explicit, testable phases that
mirror the documentation in ``docs/data_pipeline.md``. Each phase operates on an
``IngestGraph`` and communicates through a shared ``PipelineContext`` so domain
rules remain explicit and adapter-free.
"""

from __future__ import annotations

from .canonicalization import CanonicalizationPhase
from .deduplication import DeduplicationPhase
from .ingest_ports import NormalizationSidecarRepository
from .normalization import NormalizationPhase
from .orchestrator import IngestGraph, IngestionPipeline, PipelineContext, PipelinePhase
from .state import NormalizationState

__all__ = [
    "CanonicalizationPhase",
    "DeduplicationPhase",
    "IngestGraph",
    "IngestionPipeline",
    "NormalizationPhase",
    "NormalizationSidecarRepository",
    "NormalizationState",
    "PipelineContext",
    "PipelinePhase",
]
