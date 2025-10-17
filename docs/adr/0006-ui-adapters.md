# ADR 0006: Initial UI via CLI Adapter

- Status: Accepted
- Date: 2025-03-05

## Context
The long-term goal includes an interactive visualization, but no concrete UI stack is chosen yet. We still need a way to exercise domain services and present results.

## Decision
Implement a CLI adapter as the first primary adapter. Command-line commands trigger domain use cases (e.g., sync scrobbles, list albums). The CLI will output tabular/text data, serving both as a developer tool and a reference implementation. Future ADRs can introduce richer UIs (web, desktop) that consume the same domain ports.

## Consequences
- Enables immediate feedback and testing without front-end investment.
- Keeps API surface minimal while the domain evolves.
- Provides a template for future adapters, ensuring they stay at arm’s length from core logic.
