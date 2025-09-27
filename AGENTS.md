# Agent Workflow Notes

- Prefer editor-style patch operations (`apply_patch`) for creating, updating, or deleting files. Avoid shell commands like `mkdir`, `cat`, or `echo` unless there is no alternative.
- Minimize shell usage overall to reduce redundant approval prompts.
