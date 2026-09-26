# agent-skills-marketplace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Plugin marketplace catalog for [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

This is an open-source, publicly installable catalog. It holds the catalogs that control which version of `agent-skills` marketplace consumers install — each plugin pinned to a tested GA release (`ref` + `sha`) — plus a vendored copy of the released skills (`skills/`) for tools that install from `SKILL.md` files directly. Bumping the pin here rolls out updates on StackHawk's release cadence, independently of the plugin development cadence.

The catalog publishes six plugins: **`hawkscan`** (DAST scanning), **`stackhawk-api`** (StackHawk platform API), **`hawkscan-ci`** (CI integration), **`stackhawk-data-seed`** (seed data for authenticated scans), **`stackhawk-optimize`** (scan tuning), and **`wingman`** (umbrella: installs the default skill set).

## Install

The marketplace serves the agents whose plugin systems can pin a remote source. Pick yours:

### Claude Code

```
/plugin marketplace add stackhawk/agent-skills-marketplace
/plugin install hawkscan@stackhawk
/plugin install stackhawk-api@stackhawk
```

### Anthropic directory submissions

Submit each plugin bundle from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills), where its `.claude-plugin/plugin.json` and components live. This marketplace repository is an install catalog, not a plugin bundle. In the [developer portal](https://claude.ai/directory/manage), use `stackhawk/agent-skills` as the repository and submit each desired `plugins/<path>` folder separately. The paths are `plugins/hawkscan`, `plugins/api` (plugin name `stackhawk-api`), `plugins/hawkscan-ci`, `plugins/stackhawk-data-seed`, `plugins/optimize` (plugin name `stackhawk-optimize`), and `plugins/wingman`.

Run `claude plugin validate --strict plugins/<path>` in the `agent-skills` repository for each folder, then use the portal's **Validate** action on the commit you intend to submit. The [portal checklist](https://claude.com/docs/plugins/pre-submission-checklist) checks more than the CLI, including a README of at least 40 words in each plugin folder. Choose the intended tracked branch or tag in the portal and validate again after changing its commit. Submission and publication are separate actions.

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

### skills CLI (npx)

The [`skills` CLI](https://github.com/vercel-labs/skills) discovers `SKILL.md` files and ignores `marketplace.json`, so it installs from the vendored `skills/` directory instead of the catalog:

```
npx skills add stackhawk/agent-skills-marketplace --all
```

Add `-g` for a user-level install. This installs five skills: `hawkscan`, `stackhawk-api`, `hawkscan-ci`, `stackhawk-data-seed`, and `stackhawk-optimize`. To move to the next GA release, run `npx skills update` — the CLI re-fetches the default branch and compares folder hashes.

This path installs skills only (`SKILL.md` + `references/`), not plugin hooks. For the full plugin with hooks, use the per-agent plugin commands above; each also has a scriptable CLI form (`claude plugin install wingman@stackhawk`, `codex plugin add hawkscan@stackhawk`, `copilot plugin install wingman@stackhawk`) after the matching `marketplace add`.

> **Cursor** and **Antigravity (`agy`)** don't consume this marketplace — they install directly from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) (Cursor copies the generated `.mdc` rules; `agy plugin install <agent-skills repo URL>`). See the agent-skills README for their steps.

## Structure

```
.claude-plugin/marketplace.json   # Claude Code - git-subdir source
.agents/plugins/marketplace.json  # Codex — git-subdir source
.codex-plugin/marketplace.json    # legacy Codex path (back-compat)
.github/plugin/marketplace.json   # GitHub Copilot CLI - github source + path
skills/<name>/                    # vendored GA skills for the `skills` CLI — generated, do not edit
```

Every plugin entry points at `stackhawk/agent-skills` at a subdirectory (`plugins/<name>`), pinned to a release `ref` + `sha`. Claude Code and Codex use a `git-subdir` source, while GitHub Copilot CLI uses a `github` source. Each tool reads its own catalog.

## Updating the pinned version

**These catalogs are generated, not hand-edited.** When `agent-skills` cuts a release, its `release.yml` runs `scripts/generate-marketplace-catalogs.py` and pushes the regenerated catalogs here automatically — pinning every plugin to the new tag + SHA in each tool's schema. The same release run also regenerates `skills/` (via `scripts/generate-marketplace-skills.py`) from the released skill directories. To roll a new version out to consumers, **release `agent-skills`**; don't edit `marketplace.json` or `skills/` by hand (a release will overwrite them).

## Why a separate repo

- `agent-skills` iterates continuously; this repo only changes when we deliberately roll a GA version to consumers
- SHA pinning alongside `ref` guarantees reproducibility even if a tag is moved
- Public and open source so any supported agent can install StackHawk skills directly

## Contributing

The catalogs are generated from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) — to add or change skills, contribute there. The generator and publisher live in that repo (`scripts/generate-marketplace-catalogs.py` and `.github/workflows/release.yml`).

## License

[MIT](LICENSE) — © 2026 StackHawk, Inc.
