# agent-skills-marketplace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Plugin marketplace catalog for [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

This is an open-source, publicly installable catalog. It holds only the catalogs that control which version of `agent-skills` marketplace consumers install — each plugin pinned to a tested GA release (`ref` + `sha`). Bumping the pin here rolls out updates on StackHawk's release cadence, independently of the plugin development cadence.

The catalog publishes two plugins: **`hawkscan`** (DAST scanning) and **`stackhawk-api`** (StackHawk platform API).

## Install

The marketplace serves the agents whose plugin systems can pin a remote source. Pick yours:

### Claude Code

```
/plugin marketplace add stackhawk/agent-skills-marketplace
/plugin install hawkscan@stackhawk
/plugin install stackhawk-api@stackhawk
```

### Codex

```
codex plugin marketplace add stackhawk/agent-skills-marketplace
codex plugin add hawkscan@stackhawk
codex plugin add stackhawk-api@stackhawk
```

### GitHub Copilot CLI

```
copilot plugin marketplace add stackhawk/agent-skills-marketplace
copilot plugin install hawkscan@stackhawk
copilot plugin install stackhawk-api@stackhawk
```

> **Cursor** and **Antigravity (`agy`)** don't consume this marketplace — they install directly from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) (Cursor copies the generated `.mdc` rules; `agy plugin install <agent-skills repo URL>`). See the agent-skills README for their steps.

## Structure

```
.claude-plugin/marketplace.json   # Claude Code + GitHub Copilot CLI — github source + path
.agents/plugins/marketplace.json  # Codex — git-subdir source
.codex-plugin/marketplace.json    # legacy Codex path (back-compat)
```

Every plugin entry points at `stackhawk/agent-skills` at a subdirectory (`plugins/<name>`), pinned to a release `ref` + `sha`. The per-tool source schema differs (Claude/Copilot use a `github` source; Codex uses `git-subdir`), which is why there is more than one catalog.

## Updating the pinned version

**These catalogs are generated, not hand-edited.** When `agent-skills` cuts a release, its `release.yml` runs `scripts/generate-marketplace-catalogs.py` and pushes the regenerated catalogs here automatically — pinning every plugin to the new tag + SHA in each tool's schema. To roll a new version out to consumers, **release `agent-skills`**; don't edit `marketplace.json` by hand (a release will overwrite it).

## Why a separate repo

- `agent-skills` iterates continuously; this repo only changes when we deliberately roll a GA version to consumers
- SHA pinning alongside `ref` guarantees reproducibility even if a tag is moved
- Public and open source so any supported agent can install StackHawk skills directly

## Contributing

The catalogs are generated from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) — to add or change skills, contribute there. The generator and publisher live in that repo (`scripts/generate-marketplace-catalogs.py` and `.github/workflows/release.yml`).

## License

[MIT](LICENSE) — © 2026 StackHawk, Inc.
