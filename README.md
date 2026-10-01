# agent-skills-marketplace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Plugin marketplace catalog for [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

This is a public catalog pinned to a tested `agent-skills` release. Every catalog installs from this repository through relative sources, so the marketplace commit that you add is the one pin for all agents. Claude, Codex, and GitHub Copilot CLI install the plugin snapshots in `plugins/`. Codex and Copilot install Wingman from `bundles/wingman/`, because they cannot install plugin dependencies. The standalone `skills/` copies serve tools that install directly from `SKILL.md`. Updating this repo rolls out a GA release independently of development in `agent-skills`.

The catalog publishes six plugins: **`hawkscan`** (DAST scanning), **`stackhawk-api`** (StackHawk platform API), **`hawkscan-ci`** (CI integration), **`stackhawk-data-seed`** (seed data for authenticated scans), **`stackhawk-optimize`** (scan tuning), and **`wingman`** (umbrella: installs the default skill set).

## Install

The marketplace serves several agents. Pick yours:

### Claude Code

```
/plugin marketplace add stackhawk/agent-skills-marketplace
/plugin install hawkscan@stackhawk
/plugin install stackhawk-api@stackhawk
```

### Anthropic directory submissions

Use this repository as the source when submitting the marketplace directory in the [developer portal](https://claude.ai/directory/manage). Its [Claude catalog](.claude-plugin/marketplace.json) points at six plugin folders inside the same repository, as the directory requires. It does not list `bundles/`. Run `claude plugin validate --strict .` and validate every `plugins/<name>` folder locally, then use the portal's **Validate** action on the commit you intend to submit. The [portal checklist](https://claude.com/docs/plugins/pre-submission-checklist) checks more than the CLI, including each plugin's README. Validate again after changing the tracked commit. Submission and publication are separate actions.

Wingman is an umbrella plugin. It has no direct skill; its `dependencies` field installs `hawkscan`, `stackhawk-api`, `stackhawk-data-seed`, and `stackhawk-optimize` from this marketplace in Claude Code. Codex and Copilot ignore that field, so their Wingman bundle in `bundles/wingman/` contains copies of those four skills. The directory may describe Wingman as having no components, so review its listing text before publishing.

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

Add `-g` for a user-level install. This installs five skills: `hawkscan`, `stackhawk-api`, `hawkscan-ci`, `stackhawk-data-seed`, and `stackhawk-optimize`. To move to the next GA release, run `npx skills update`. The CLI re-fetches the default branch and compares folder hashes.

This path installs skills only (`SKILL.md` + `references/`), not plugin hooks. For the full plugin with hooks, use the per-agent plugin commands above; each also has a scriptable CLI form (`claude plugin install wingman@stackhawk`, `codex plugin add hawkscan@stackhawk`, `copilot plugin install wingman@stackhawk`) after the matching `marketplace add`.

> **Cursor** and **Antigravity (`agy`)** don't consume this marketplace. They install directly from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) (Cursor copies the generated `.mdc` rules; `agy plugin install <agent-skills repo URL>`). See the agent-skills README for their steps.

## Structure

```
.claude-plugin/marketplace.json   # Claude Code - local plugin paths
.agents/plugins/marketplace.json  # Codex - local plugin paths
.codex-plugin/marketplace.json    # legacy Codex path
.github/plugin/marketplace.json   # GitHub Copilot CLI - local plugin paths
plugins/<name>/                  # released plugin snapshots
bundles/wingman/                 # Wingman with bundled skills for Codex and Copilot
skills/<name>/                   # standalone skills for the skills CLI
sources.json                     # source tag, SHA, and plugin path mapping
scripts/sync-agent-skills.py     # repeatable release sync
overrides/<name>/README.md       # README fallbacks for older source tags
```

The Claude catalog uses local paths so the directory can inspect each plugin. The Codex and Copilot catalogs use the same local paths in their own source schemas, except for Wingman. `sources.json` records the exact upstream commit for all copied files.

## Updating the pinned version

**The catalogs, plugin snapshots, and standalone skills are generated.** Do not edit the generated output by hand.

The `agent-skills` release workflow does the sync. It does not write the external-source Claude catalog. For each release tag, it runs `scripts/sync-agent-skills.py` from this repository and runs the tests. Then it opens a sync pull request here for review. Merge that pull request to publish the release.

Merge this repository's local-path layout before the next `agent-skills` release is dispatched. The release workflow needs `scripts/sync-agent-skills.py` in this repository.

To sync by hand, use a local `agent-skills` checkout that contains the release tag:

```bash
python3 scripts/sync-agent-skills.py --source-repo /path/to/agent-skills --tag vX.Y.Z
python3 -m unittest discover -s tests
```

To preview the directory checks locally, run the Claude validator on the catalog and on each plugin:

```bash
claude plugin validate --strict .
for plugin in plugins/*; do claude plugin validate --strict "$plugin"; done
```

The script verifies the tag against `VERSION`, records its SHA in `sources.json`, and refuses a moved tag. It copies the six plugin folders, adds verified StackHawk listing URLs, and supplies missing README files from `overrides/`. It moves Wingman's bundled skills from `plugins/wingman/` to `bundles/wingman/`. It regenerates all catalogs and standalone skills, and keeps Wingman's dependencies within this catalog. Review and commit the generated diff before publishing.

## Why a separate repo

- `agent-skills` iterates continuously; this repo only changes when we deliberately roll a GA version to consumers
- The recorded SHA and tag movement check make each synced release traceable
- Public and open source so any supported agent can install StackHawk skills directly

## Contributing

The source skills and plugin behavior live in [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills). To add or change them, contribute there, then run the sync script here for a released tag. Marketplace-only README fallbacks live in `overrides/`.

## License

[MIT](LICENSE) - © 2026 StackHawk, Inc.
