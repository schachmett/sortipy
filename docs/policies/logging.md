# Logging Policy

This document explains how Sortipy uses logging today and what expectations new
code should follow. It favours simplicity so the team can add observability in
small increments without introducing heavy infrastructure.

## Scope

- Log adapter interactions that may fail or trigger retries (e.g. Last.fm
  status codes, request errors, parsing failures).
- Log orchestration milestones for sync operations: start, finish, and summary
  counts.
- Log boundary validation issues (CLI arguments, configuration) before exiting.
- Unexpected exceptions should be captured with traceback context via
  `log.exception` or by letting the exception propagate after logging at
  `ERROR` level.

## Levels

- `INFO` for high-level lifecycle events (sync start/completion).
- `WARNING` for retryable or transient problems we expect to recover from
  (rate-limits, 5xx responses, transport hiccups).
- `ERROR` for failures that bubble up to the user or stop the process.
- `DEBUG` is optional; prefer to keep debug-only statements behind feature
  flags or temporary troubleshooting branches.

Stick to these levels instead of using `print`.

## Style

- Use plain f-strings and keep log messages single-line when possible.
- Include actionable context (status code, retry attempt, delay, counts).
- Never log secrets (API keys, tokens). Redact or omit sensitive payloads.
- Do not introduce helper abstractions unless several call sites need the same
  formatted message.

## Routing

- Default logs go to the console (`stdout` / `stderr`) using Python's standard
  `logging` module.
- We postpone structured logging or JSON formatting until the project adopts a
  log aggregation backend. The current design keeps that door open.

## Future Work

- Add a shared logging setup module when multiple adapters/services need custom
  configuration.
- Extend this policy if we add metrics, tracing, or structured log fields.
