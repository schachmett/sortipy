"""Factories for the default reconciliation runtime."""

from __future__ import annotations

from .apply import apply_reconciliation_instructions
from .deduplicate import deduplicate_claim_graph
from .engine import ReconciliationEngine
from .normalize import normalize_claim_graph
from .persist import persist_reconciliation
from .policy import decide_apply_instructions
from .resolve import resolve_claim_graph


def create_default_reconciliation_engine() -> ReconciliationEngine:
    """Return the default reconciliation engine wiring."""

    return ReconciliationEngine(
        normalize=normalize_claim_graph,
        deduplicate=deduplicate_claim_graph,
        resolve=resolve_claim_graph,
        decide=decide_apply_instructions,
        apply=apply_reconciliation_instructions,
        persist=persist_reconciliation,
    )
