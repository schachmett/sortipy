# ADR 0004: Pull-Based Periodic Ingestion

- Status: Proposed
- Date: 2025-03-05

## Context
Initial implementation needs a simple way to sync scrobbles and library snapshots without introducing messaging infrastructure. Polling the external APIs periodically is straightforward but may not scale indefinitely.

## Decision
Adopt pull-based ingestion jobs that run on demand or on a schedule. Each adapter fetches the latest data, applies idempotent inserts/updates, and records checkpoints. The architecture keeps ports generic so future event-driven or streaming ingestion can be introduced without reworking domain services.

## Consequences
- Simplifies early development and local usage.
- Requires careful rate-limit handling and checkpointing to avoid duplicates.
- May miss near real-time updates; future ADR can revisit event-driven ingestion if needed.
