# ADR 0005: Configuration via dotenv Files (for now)

- Status: Proposed
- Date: 2025-03-05

## Context
During early development, contributors need a lightweight way to provide API keys and database URIs without setting up secret managers. `.env` files loaded via `python-dotenv` already exist in the project.

## Decision
Continue using `.env` files for local configuration in the short term. Domain services receive configuration through explicit settings objects or environment lookups at adapter boundaries. Document the variables required. Plan a future ADR to migrate to a more secure and user-friendly solution (e.g., keyring or managed secrets) before production deployment.

## Consequences
- Low friction setup for developers.
- Requires discipline to avoid committing `.env` files.
- Recognize the approach as temporary; schedule revisit when deployment story matures.
