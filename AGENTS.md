# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Run `scripts/sync-agent-skills.py` with a released tag from a local `stackhawk/agent-skills` checkout to regenerate catalogs, plugin snapshots, and `skills/`; see [README.md](README.md#updating-the-pinned-version). Do not edit generated outputs by hand.
- Validate the Claude catalog with `claude plugin validate --strict .` and each `plugins/<name>` folder with the same command. The Codex and Copilot catalogs use their own schemas.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
