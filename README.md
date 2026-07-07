# Disgust Docs CLI

`disgust-docs` connects product Markdown documentation repositories to local code projects so coding agents can read and update shared docs as normal files.

## Install

After the package is published, install it as a regular CLI tool:

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

## Release

PyPI publishing is handled by `.github/workflows/publish.yml`.

Before the first release, configure PyPI Trusted Publishing for:

- project name: `disgust-docs`
- repository: `LebedAlIv2601/shareable-ai-md-docs`
- workflow: `publish.yml`
- environment: `pypi`

Then create a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
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

## V1 Model

- Each product has its own docs repository.
- The global git object cache lives under `~/.disgust-docs/mirrors/`.
- Each project gets a local docs worktree under `.disgust-docs/<alias>`.
- `readOnly` docs can be synced and inspected.
- `pr` docs can be edited through an explicit edit session and published through a GitHub PR using `gh`.
- Direct pushes to `main` are intentionally unsupported.

Generated indexes, automatic `AGENTS.md` patches, non-GitHub providers, and a dedicated agent skill are future extensions.
