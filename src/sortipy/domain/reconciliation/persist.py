"""Persistence contracts for reconciliation output.

Responsibilities of this stage:
- persist newly created canonical entities
- flush domain mutations performed by the applier
- persist sidecar/provenance event records
- commit/rollback transaction boundaries

This stage is adapter-facing; implementations will usually require a UoW.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .apply import ApplyResult
    from .plan import ResolutionPlan


@dataclass(slots=True)
class PersistenceResult:
    """Summary of persisted changes for one reconciliation run."""

    committed: bool
    persisted_entities: int = 0
    persisted_events: int = 0


class PersistReconciliation(Protocol):
    """Persist applied reconciliation changes and commit transaction state."""

    def __call__(self, *, plan: ResolutionPlan, apply_result: ApplyResult) -> PersistenceResult: ...
