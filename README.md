# Disgust Docs CLI

## Overview

`disgust-docs` makes shared Markdown documentation available to coding agents as ordinary project-local files without mixing the documentation into the project's Git repository.

The CLI keeps one regular cache clone per documentation repository under `~/.disgust-docs/repos/`. `update` exports a tracked Git commit into an ignored project directory such as `docs/`; the exported snapshot contains no `.git` metadata. Agents can read and edit that snapshot normally. `publish` transfers the resulting file changes into a temporary Git checkout, pushes a branch, and opens a GitHub pull request.

## Install

Install it as a regular CLI tool:

```bash
uv tool install disgust-docs
```

or:

```bash
pipx install disgust-docs
```

For pre-release installs directly from GitHub:

```bash
pipx install git+https://github.com/LebedAlIv2601/shareable-ai-md-docs.git
uv tool install git+https://github.com/LebedAlIv2601/shareable-ai-md-docs.git
```

## Quick Start

```bash
disgust-docs setup
disgust-docs add product git@github.com:org/product-docs.git --branch main --mode pr --path docs
```

The project commits `.disgust-docs.yml`. The generated `docs/` snapshot and `.disgust-docs/` local state are added to `.gitignore`.

Refresh the local snapshot:

```bash
disgust-docs update product
```

Edit files directly under `docs/`, then inspect and publish them:

```bash
disgust-docs status product
disgust-docs diff product
disgust-docs publish product \
  --branch docs/update-checkout-rules \
  --message "Update checkout docs" \
  --title "Update checkout docs"
```

The local `docs/` files remain unchanged after publishing. Additional edits can be published to the same branch and pull request. A later `update` replaces the published snapshot with the configured base branch.

## Configuration

```yaml
version: 1
docs:
  product:
    repo: "git@github.com:org/product-docs.git"
    branch: "main"
    provider: "github"
    mode: "pr"
    path: "docs"
```

- `repo` is the documentation Git repository.
- `branch` is the base branch exported by `update` and targeted by pull requests.
- `mode: readOnly` allows snapshots but refuses publication.
- `mode: pr` allows publication through GitHub pull requests.
- `path` must be a non-overlapping relative directory inside the project.

## Safety

- Only tracked files from the resolved base commit are exported.
- Project snapshots contain no `.git` directory.
- Managed ignore entries are kept after earlier negation rules so snapshots remain effectively ignored by the project repository.
- `update` refuses to overwrite unpublished local changes unless `--discard-local` is explicit.
- `publish` records commit, push, and PR phases so a failed PR creation can be retried.
- `publish` leaves the project-local snapshot intact.
- A snapshot path already tracked by the project repository is rejected.
- Snapshot paths inside `.git/` or the CLI-owned `.disgust-docs/` directory are rejected.
- Symlinks and other non-file Git entries are intentionally unsupported in v1 snapshots.
- Direct pushes to the configured base branch are unsupported.

`readOnly` is a workflow guard, not a security boundary. Repository permissions and branch protection remain authoritative.

## Commands

- `disgust-docs setup`: create the config template and Git ignore entries.
- `disgust-docs add <alias> <repo>`: register a repository and create its first snapshot.
- `disgust-docs update [alias]`: fetch the cache and replace safe snapshots.
- `disgust-docs status [alias]`: show snapshot, publication branch, and PR state.
- `disgust-docs diff <alias>`: compare local files with the last exported commit.
- `disgust-docs publish <alias> ...`: commit snapshot changes, push a branch, and create or update a PR.
- `disgust-docs remove <alias>`: remove registration and a safe local snapshot.

`init` and `sync` remain deprecated aliases for `setup` and `update`.

Run commands from another working directory by placing the global project option before the subcommand:

```bash
disgust-docs --project /path/to/backend status product
```

## Skill

Install the bundled Codex skill into the current project:

```bash
disgust-docs skill install
```

This overwrites `.agents/skills/disgust-docs`.

Install it globally instead:

```bash
disgust-docs skill install --global
```

Global install overwrites `${CODEX_HOME:-~/.codex}/skills/disgust-docs`.
