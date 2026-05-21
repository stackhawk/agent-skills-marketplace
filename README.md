# agent-skills-marketplace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Claude Code plugin marketplace catalog for [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

This is an open-source, publicly installable catalog. It holds only the catalog (`marketplace.json`) that controls which version of `agent-skills` marketplace consumers install. Bumping the pinned version here rolls out updates independently of the plugin development cadence.

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
- Public and open source so any Claude Code user can install StackHawk skills directly

## Contributing

This repo is intentionally minimal — the catalog pin and the README. If you want to contribute new skills or improvements, head to [stackhawk/agent-skills](https://github.com/stackhawk/agent-skills).

## License

[MIT](LICENSE) — © 2026 StackHawk, Inc.
