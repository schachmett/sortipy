# TODOs

- [ ] Add structured logging to reconciliation workflows and provider adapters so runs expose fetched counts, manual-review counts, and checkpoint-like context consistently.
- [ ] Investigate the remaining SQLAlchemy autoflush warnings around `PlayEvent` and `ReleaseTrack` attachment; decide whether to use `no_autoflush` or adjust the attachment flow.
- [ ] Implement ADR-0007 provenance storage: `SourceIngest` checkpoints plus raw-payload tables for replay and debugging.
- [ ] Extend repository/query helpers so canonical self-pointers from ADR-0008 are resolved consistently for read paths, not just reconciliation-time entity resolution.
- [ ] Model user-linked external accounts explicitly instead of storing provider identifiers directly on `User`.
- [ ] Decide whether adapters should eventually emit claim graphs directly instead of fresh domain aggregates.
- [ ] Evaluate schema validation and projection boundaries for adapter payloads beyond the current Pydantic coverage.
- [ ] Establish an issue-tracking workflow accessible inside the repo for both humans and agents.
