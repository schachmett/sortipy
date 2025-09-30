# Agent Workflow Notes

**Editing & Shell Usage**
- Prefer editor-style patch operations (`apply_patch`) for creating, updating, or deleting files. Avoid shell commands like `mkdir`, `cat`, or `echo` unless there is no alternative.
- Minimize shell usage overall to reduce redundant approval prompts.
- If a tool is unavailable or blocked, call it out explicitly and ask the user how to proceed instead of skipping it silently.

**Tooling & Testing**
- For any non-trivial edit (multi-line changes, new files, refactors), run `.venv/bin/ruff check`, `.venv/bin/pyright`, and `.venv/bin/pytest` before wrapping up.
- Minor code tweaks or documentation-only updates can skip the full test suite; note the rationale when you do.
- Fix or explain any failures those tools surface; do not leave known lint/test issues unresolved.
- If a required tool is missing or blocked, pause and ask the user how they want to fix it, offering concrete remediation steps you can take.
- When adding a Python module, place `from __future__ import annotations` at the top to satisfy Ruff's required import rule.
- If a test is known to be flaky, call that out explicitly, reference the test name, and explain the observed flake instead of chasing it endlessly; otherwise treat failures as real until proven flaky.
- Follow the logging policy in `docs/policies/logging.md` for new log statements (levels, style, and scope).

**Git Hygiene**
- Create commits proactively; keep them atomic and scoped (tooling, docs, feature, refactor, bugfix, etc.) instead of bundling unrelated changes.
- Only commit after `.venv/bin/ruff check`, `.venv/bin/pyright`, and `.venv/bin/pytest` all succeed so the history stays green (or you have explicitly justified why tests were skipped).
- If you cannot resolve a failure before committing, stop and ask for guidance instead of committing a broken state.
- After completing work, list only the commits you created during the current task (`git log --oneline -n <count>`) with brief descriptions so the user sees exactly what changed.
- If the planned work fits into a single commit—or multiple commits that touch disjoint files—prepare the changes and propose the commit(s) instead of committing.
- When proposing commit(s), stage the changes for the first proposed commit so it is ready to publish; leave subsequent proposals unstaged unless you are asked otherwise.
- Never attempt to resolve merge conflicts without explicit user direction.
- Keep secrets out of the repository and documentation entirely; if something looks sensitive, stop and confirm with the user before continuing.

**Release Awareness**
- When the work naturally reaches a milestone (feature completion, bugfix, etc.), proactively suggest creating a git tag and corresponding release, explain why you think the milestone is release-worthy, and ensure suggested tags follow semantic versioning.
