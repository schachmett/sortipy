"""Entity ingestion pipeline scaffolding for Sortipy.

This package separates the ingestion pipeline into explicit, testable phases that
mirror the documentation in ``docs/data_pipeline.md``. Each phase operates on an
``IngestGraph`` and communicates through a shared ``PipelineContext`` so domain
rules remain explicit and adapter-free.
"""

from __future__ import annotations

from .deduplication import DefaultDeduplicationPhase
from .normalization import DefaultNormalizationPhase
from .orchestrator import IngestGraph, IngestionPipeline, PipelineContext, PipelinePhase
from .state import NormalizationState

__all__ = [
    "DefaultDeduplicationPhase",
    "DefaultNormalizationPhase",
    "IngestGraph",
    "IngestionPipeline",
    "NormalizationState",
    "PipelineContext",
    "PipelinePhase",
]
