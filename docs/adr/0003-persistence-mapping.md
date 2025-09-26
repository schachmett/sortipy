# ADR 0003: Persistence via SQLAlchemy with Imperative Mappers

- Status: Proposed
- Date: 2025-03-05

## Context
We need relational persistence with SQLAlchemy while keeping domain entities free of ORM concerns. Declarative models would couple SQLAlchemy types to domain classes.

## Decision
Use SQLAlchemy Core/ORM with imperative (classical) mappings defined inside the `adapters.sqlalchemy` package. Domain entities remain pure dataclasses/objects. Repository implementations within the adapter configure table metadata and `mapper` bindings, exposing repository ports to the domain via unit-of-work factories.

## Consequences
- Domain model stays decoupled from SQLAlchemy, aligning with ports-and-adapters goals.
- Mapping code lives in the adapter, which can evolve independently (e.g., different database engines, schema tweaks).
- Requires additional boilerplate compared to declarative models, but improves testability and limits cross-layer dependencies.
