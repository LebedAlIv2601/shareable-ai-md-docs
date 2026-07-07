# Agent Docs CLI

`agent-docs` connects product Markdown documentation repositories to local code projects so coding agents can read and update shared docs as normal files.

## Install

```bash
uvx agent-docs --help
pipx install .
```

## Quick Start

```bash
agent-docs init
agent-docs add pizza git@github.com:org/pizza-docs.git --branch main --mode pr
agent-docs sync pizza
agent-docs edit pizza --branch docs/update-checkout-rules
agent-docs publish pizza --message "Update checkout docs" --title "Update checkout docs"
```

The project commits `.agent-docs.yml` and ignores `.agent-docs/`.

## V1 Model

- Each product has its own docs repository.
- The global git object cache lives under `~/.agent-docs/mirrors/`.
- Each project gets a local docs worktree under `.agent-docs/<alias>`.
- `readOnly` docs can be synced and inspected.
- `pr` docs can be edited through an explicit edit session and published through a GitHub PR using `gh`.
- Direct pushes to `main` are intentionally unsupported.

Generated indexes, automatic `AGENTS.md` patches, non-GitHub providers, and a dedicated agent skill are future extensions.
