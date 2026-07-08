# Disgust Docs CLI

## Overview

`disgust-docs` connects product Markdown documentation repositories to local code projects so coding agents can read and update shared docs as normal files.

It keeps shared docs in project-local worktrees under `.disgust-docs/`, while git objects are cached globally under `~/.disgust-docs/mirrors/`.

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
disgust-docs init
disgust-docs add pizza git@github.com:org/pizza-docs.git --branch main --mode pr
disgust-docs sync pizza
disgust-docs edit pizza --branch docs/update-checkout-rules
disgust-docs publish pizza --message "Update checkout docs" --title "Update checkout docs"
```

The project commits `.disgust-docs.yml` and ignores `.disgust-docs/`.

## Features

- Each product has its own docs repository.
- `readOnly` docs can be synced and inspected.
- `pr` docs can be edited through an explicit edit session and published through a GitHub PR using `gh`.
- Local worktrees give agents normal files to inspect and edit.
- The portable project contract lives in `.disgust-docs.yml`.
- Direct pushes to `main` are intentionally unsupported.

Generated indexes, automatic `AGENTS.md` patches, and non-GitHub providers are future extensions.

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
