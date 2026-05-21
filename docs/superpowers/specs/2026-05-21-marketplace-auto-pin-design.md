# Design: Auto-update marketplace version pin on agent-skills release

**Date:** 2026-05-21  
**Status:** Approved

## Problem

When `agent-skills` cuts a release, the version pin in `agent-skills-marketplace/.claude-plugin/marketplace.json` must be manually updated to point at the new tag and SHA. This is error-prone and easy to forget.

## Goal

Automatically update the marketplace pin whenever `agent-skills/release.yml` completes a successful (non-dry-run) release.

---

## Architecture

A new `update-marketplace` job is added to the existing `agent-skills/release.yml` workflow. It runs after the `release` job succeeds and only when `inputs.dry_run != true`.

**Repos involved:**
- `stackhawk/agent-skills` — source of truth for version; workflow lives here
- `stackhawk/agent-skills-marketplace` — receives the automated commit

---

## Data Flow

1. The `update-marketplace` job inherits `steps.version.outputs.tag` and `steps.version.outputs.version` from the earlier `release` job via `needs`.
2. The job checks out `agent-skills` at the released tag (already the case from the release job's checkout context) and resolves the commit SHA with `git rev-parse HEAD`.
3. A GitHub App token is generated via `tibdex/github-app-token@v1` using `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` secrets — the same App the org uses for cross-repo automation in `hawkop`.
4. The job clones `stackhawk/agent-skills-marketplace` using the App token as the credential.
5. A Python one-liner updates `.claude-plugin/marketplace.json` — for every plugin entry, sets `source.ref` to the new tag (e.g. `v1.6.3`) and `source.sha` to the resolved commit SHA. Also sets a top-level `version` field consistent with the internal marketplace format.
6. The updated file is committed as `chore: pin agent-skills to v<version>` and pushed directly to `main`.

---

## Authentication

Uses the org's existing GitHub App via `tibdex/github-app-token@v1`. Requires two secrets to be present in `stackhawk/agent-skills`:

| Secret | Description |
|--------|-------------|
| `GITHUB_APP_ID` | The GitHub App's numeric ID |
| `GITHUB_APP_PRIVATE_KEY` | The App's private key (PEM format) |

The App must have **Contents: Read & Write** permission on `stackhawk/agent-skills-marketplace`.

---

## marketplace.json update

**Before (current state):**
```json
{
  "name": "hawkscan",
  "source": {
    "source": "github",
    "repo": "stackhawk/agent-skills",
    "ref": "main",
    "sha": "9ec78a4a7f60341c08a27c6110c4c49ffcd6596e"
  }
}
```

**After a v1.6.3 release:**
```json
{
  "name": "hawkscan",
  "version": "1.6.3",
  "source": {
    "source": "github",
    "repo": "stackhawk/agent-skills",
    "ref": "v1.6.3",
    "sha": "<sha-of-v1.6.3-tag>"
  }
}
```

All plugin entries are updated in a single commit.

---

## Error Handling

- Job is gated on `needs.release.result == 'success'` and `inputs.dry_run != true` — the marketplace update never runs on a dry run or a failed release.
- If the App token generation or the push fails, the job fails loudly in GitHub Actions. The GitHub Release already created is unaffected.
- The Python update script validates JSON before writing; a malformed result cannot corrupt the file.
- Re-running the workflow from the same tag is safe — the script is idempotent (same tag → same output).

---

## Out of Scope

- No PR flow — direct push to `main` (mechanical version bump, mirrors the `hawkop` bump-version pattern).
- No rollback automation — re-run from the same tag to retry.
- No changes to `agent-skills-marketplace`'s own CI workflows.
- No changes to how the release itself (GitHub Release creation) works.

---

## Files Changed

| Repo | File | Change |
|------|------|--------|
| `stackhawk/agent-skills` | `.github/workflows/release.yml` | Add `update-marketplace` job |

The `agent-skills-marketplace` repo has no workflow changes — it is only a target of the automated commit.

---

## Secret Setup (one-time, out of band)

Before the workflow will work, a StackHawk admin must:
1. Confirm the GitHub App has **Contents: Read & Write** on `stackhawk/agent-skills-marketplace`
2. Add `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` as secrets on `stackhawk/agent-skills` (or as org-level secrets if not already present)
