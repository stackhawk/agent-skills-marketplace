# agent-skills-marketplace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Plugin marketplace catalog for [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

This is a public catalog pinned to a tested `agent-skills` release. Every catalog installs from this repository through relative sources, so the marketplace commit that you add is the one pin for all agents. Claude, Codex, and GitHub Copilot CLI install the plugin snapshots in `plugins/`. Codex and Copilot install Wingman from `bundles/wingman/`, because they cannot install plugin dependencies, and so does Cursor from the first release with the Cursor catalog. The standalone `skills/` copies serve tools that install directly from `SKILL.md`. Updating this repo rolls out a GA release independently of development in `agent-skills`.

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

Wingman is an umbrella plugin. It has no direct skill; its `dependencies` field installs `hawkscan`, `stackhawk-api`, `stackhawk-data-seed`, and `stackhawk-optimize` from this marketplace in Claude Code. Codex, Copilot, and Cursor ignore that field, so their Wingman bundle in `bundles/wingman/` contains copies of those four skills. The directory may describe Wingman as having no components, so review its listing text before publishing.

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

### Cursor

The Cursor catalog (`.cursor-plugin/marketplace.json`) and the installers in `install/` arrive with the first `agent-skills` release that the sync publishes with `--export` (see [Updating the pinned version](#updating-the-pinned-version)). Until this repository has them, install Cursor from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) as its README describes.

**Project install** (recommended; Cursor Cloud Agents and the headless CLI read only the project's `.cursor/`). Run the released installer from a clone of this repository:

```
bash agent-skills-marketplace/install/install.sh --platform cursor --target .
```

On Windows, run `.\agent-skills-marketplace\install\install.ps1 -Platform cursor -Target .`. The installer copies the five released skills into `.cursor/skills/`, the router rule `stackhawk.mdc` and the `stackhawk.yml` rule `stackhawk-config.mdc` into `.cursor/rules/`, and the stop hook into `.cursor/hooks/` with one entry in `.cursor/hooks.json`. It removes the rules that older StackHawk installers wrote. With your home directory as the target, it makes a user-level install of the skills and the stop hook only, because Cursor has no file-based user rules.

**Team marketplace:** a Cursor team admin can import this repository as a team marketplace. Its Cursor catalog lists the same six plugins. Cursor installs Wingman from `bundles/wingman/`, which bundles its four skills. Enable `wingman` or the separate plugins, not both: `hawkscan` and `wingman` each carry the router rule and the stop hook. By default the Cursor app can also import the plugins that you install in Claude Code (according to its code; not verified in a live session). If it does, StackHawk plugins installed both in Claude Code and from this Cursor catalog load the router rule and the stop hook twice, so install them in one place. In a headless run, the Cursor CLI loads the skills of a plugin but does not give its rules to the agent, and it runs stop hooks only in interactive sessions. For the router rule in headless runs, use the project install.

The stop hook is a bash script. On Windows, Cursor needs bash (for example Git for Windows) to run it.

> **Antigravity (`agy`)** doesn't consume this marketplace. It installs directly from [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills) (`agy plugin install <agent-skills repo URL>`). See the agent-skills README for its steps.

## Structure

```
.claude-plugin/marketplace.json   # Claude Code - local plugin paths
.agents/plugins/marketplace.json  # Codex - local plugin paths
.codex-plugin/marketplace.json    # legacy Codex path
.github/plugin/marketplace.json   # GitHub Copilot CLI - local plugin paths
.cursor-plugin/marketplace.json   # Cursor - local plugin paths
plugins/<name>/                  # released plugin snapshots
bundles/wingman/                 # Wingman with bundled skills for Codex, Copilot, and Cursor
install/                         # released Cursor and Copilot installers
skills/<name>/                   # standalone skills for the skills CLI
sources.json                     # source tag, SHA, and plugin path mapping
scripts/sync-agent-skills.py     # repeatable release sync
overrides/<name>/README.md       # README fallbacks for older source tags
overrides/wingman-bundle/README.md # README for the Wingman bundle
```

The Claude catalog uses local paths so the directory can inspect each plugin. The Codex, Copilot, and Cursor catalogs use the same local paths in their own source schemas, except for Wingman, which they install from `bundles/wingman/`. The Claude `plugins/wingman/` carries no Cursor files: by default the Cursor app imports Claude Code plugins (according to its code; not verified in a live session), and the `hawkscan` dependency already brings the router rule and the stop hook. `sources.json` records the exact upstream commit for all copied files.

## Updating the pinned version

**The catalogs, plugin snapshots, standalone skills, and installers are generated.** Do not edit the generated output by hand.

The `agent-skills` release workflow does the sync. It does not write the external-source Claude catalog. For each release tag, it runs `scripts/sync-agent-skills.py` from this repository and runs the tests. Then it commits only the sync outputs to `main` here. From the `agent-skills` release that adds `scripts/export-marketplace.py`, the workflow exports the release payload with that script, runs the sync with `--export`, and also runs its `scripts/check-marketplace-layout.py` and `scripts/ci/stage-marketplace-sync.sh`. Its validate job runs the same steps on a clone of `main` here before it claims a release number.

Merge `--export` support here before `agent-skills` merges `scripts/export-marketplace.py`. From that merge on, the validate job of every release runs this sync with `--export`, and it fails until `main` here accepts that option.

To sync by hand, use a local `agent-skills` checkout that contains the release tag:

```bash
python3 /path/to/agent-skills/scripts/export-marketplace.py --source-repo /path/to/agent-skills \
  --ref vX.Y.Z --version X.Y.Z --dest /tmp/agent-skills-export
python3 scripts/sync-agent-skills.py --source-repo /path/to/agent-skills --tag vX.Y.Z \
  --export /tmp/agent-skills-export
python3 -m unittest discover -s tests
python3 /path/to/agent-skills/scripts/check-marketplace-layout.py --run-installers --version X.Y.Z .
bash /path/to/agent-skills/scripts/ci/stage-marketplace-sync.sh .
```

The export holds the Claude-oriented plugin snapshots, the complete Wingman bundle, the Cursor catalog, and the installers, as `agent-skills` builds them, and a manifest of every file. The last command stages the sync outputs, and it fails when the sync changed any other path. For a tag older than the export, run only the sync without `--export`, and the tests. That sync copies the plugin folders of the tag. It refuses a tag that carries the Cursor adapter, and it removes the Cursor catalog and installers of an earlier sync.

To preview the directory checks locally, run the Claude validator on the catalog and on each plugin:

```bash
claude plugin validate --strict .
for plugin in plugins/*; do claude plugin validate --strict "$plugin"; done
```

The release version comes from `--tag`, not from the tagged tree: the script stamps it into every plugin manifest, each `SKILL.md` `version:` line, and Wingman's bundled skill copies, so placeholder in-tree versions are fine. It records the tag's SHA in `sources.json` and refuses a moved tag. It copies the six plugin folders, adds verified StackHawk listing URLs, and supplies missing README files from `overrides/`. It keeps Wingman's bundled skills, Copilot manifest, and Cursor files in `bundles/wingman/` only, and writes the bundle README from `overrides/wingman-bundle/`. It regenerates all catalogs and standalone skills, and keeps Wingman's dependencies within this catalog. Review and commit the generated diff before publishing.

With `--export`, the script copies the export into its stage, checks that copy, and builds from it. The export must be of the tag's commit and version, and map each plugin to its folder in `sources.json`. Each file that its manifest lists must have the listed sha256, size, and mode. The export must hold no other file, no path outside its layout, and no symlink or special file, and it must hold every file that the published layout needs. The script then refuses a Claude `plugins/wingman/` with Cursor or bundle files, and a Cursor install that loads more than one router rule or stop hook. A Cursor install that carries the `hawkscan` skill must load exactly one of each. A plugin of the export that `sources.json` does not list is not published.

## Why a separate repo

- `agent-skills` iterates continuously; this repo only changes when we deliberately roll a GA version to consumers
- The recorded SHA and tag movement check make each synced release traceable
- Public and open source so any supported agent can install StackHawk skills directly

## Contributing

The source skills and plugin behavior live in [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills). To add or change them, contribute there, then run the sync script here for a released tag. Marketplace-only README fallbacks live in `overrides/`.

## License

[MIT](LICENSE) - © 2026 StackHawk, Inc.
