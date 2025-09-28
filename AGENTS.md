# Agent Workflow Notes

- Prefer editor-style patch operations (`apply_patch`) for creating, updating, or deleting files. Avoid shell commands like `mkdir`, `cat`, or `echo` unless there is no alternative.
- Minimize shell usage overall to reduce redundant approval prompts.
- For any non-trivial edit (multi-line changes, new files, refactors), run `.venv/bin/ruff check`, `.venv/bin/pyright`, and `.venv/bin/pytest` before wrapping up.
- Fix or explain any failures those tools surface; do not leave known lint/test issues unresolved.
- If a tool is unavailable or blocked, call it out explicitly and ask the user how to proceed instead of skipping it silently.
- When adding a Python module, place `from __future__ import annotations` at the top to satisfy Ruff's required import rule.
- Create commits proactively; keep them atomic and scoped (tooling, docs, feature, refactor, bugfix, etc.) instead of bundling unrelated changes.
- Only commit after `.venv/bin/ruff check`, `.venv/bin/pyright`, and `.venv/bin/pytest` all succeed so the history stays green.
- If you cannot resolve a failure before committing, stop and ask for guidance instead of committing a broken state.
- After completing work, summarize the commit list (`git log --oneline -n <count>`) with brief descriptions so the user sees exactly what changed.
