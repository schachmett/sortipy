# ADR 0001: Adopt Ports-and-Adapters Architecture

- Status: Proposed
- Date: 2025-03-05

## Context
Sortipy must ingest data from multiple external services, persist it, and present it through different UIs. We want to keep domain logic independent from vendor SDKs and leave room for alternative front-ends.

## Decision
We adopt a ports-and-adapters (hexagonal) architecture. Domain use cases and entities depend only on domain-defined ports. Secondary adapters (Spotify, Last.fm, MusicBrainz, RateYourMusic, SQL persistence) implement those ports. Primary adapters (CLI now, richer UI later) invoke domain services through ports. Code layout reflects this separation.

## Consequences
- Enables swapping adapters without touching core logic.
- Requires defining explicit interfaces and data contracts in the domain layer.
- Increases upfront structure, but improves testability via mock adapters.
