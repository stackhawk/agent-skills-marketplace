# agent-skills-marketplace

Claude Code plugin marketplace catalog for [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

This repo holds only the catalog (`marketplace.json`) that controls which version of `agent-skills` marketplace consumers install. Bumping the pinned version here rolls out updates independently of the plugin development cadence.

## Install

In Claude Code:

```
/plugin marketplace add stackhawk/agent-skills-marketplace
/plugin install hawkscan@stackhawk
/plugin install api@stackhawk
```

## Structure

```
.claude-plugin/
└── marketplace.json   # Catalog pointing at stackhawk/agent-skills at a pinned ref + SHA
```

## Updating the pinned version

When a new `agent-skills` release is tagged:

1. Get the SHA for the new tag:
   ```bash
   gh api repos/stackhawk/agent-skills/git/refs/tags/vX.Y.Z --jq '.object.sha'
   ```

2. Update `.claude-plugin/marketplace.json` — set `ref` to `vX.Y.Z` and `sha` to the new SHA for each plugin entry.

3. Open a PR, get it reviewed, merge.

## Why a separate repo

- `agent-skills` iterates continuously; this repo only changes when we deliberately roll a version to consumers
- SHA pinning alongside `ref` guarantees reproducibility even if a tag is accidentally moved
- Starting private lets us validate the install flow before any consumer impact; flip public once confirmed working
