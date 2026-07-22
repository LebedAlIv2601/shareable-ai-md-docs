---
name: disgust-docs
description: "Work with shared Markdown documentation through project-local Gitless snapshots managed by the disgust-docs CLI. Use when an agent needs to connect, update, inspect, edit, publish, or disconnect shared docs declared in .disgust-docs.yml without mixing those files into the project's Git repository, including when commands must target a project outside the current directory."
---

# Disgust Docs

Use this skill for documentation snapshots managed through `disgust-docs`.

## Project Location

Run commands from the project root by default. When working from another directory, put the global `--project` option before the subcommand:

```bash
disgust-docs --project <project-root> status [alias]
```

Resolve `<project-root>` explicitly and use the same value for the entire operation.

## Initial Setup

Use this flow when a project is not connected to shared docs yet.

1. Check that `disgust-docs` is available with `disgust-docs --help`.
2. If `.disgust-docs.yml` is missing, run `disgust-docs setup` from the project root.
3. Identify the alias, repository URL, base branch, mode, and project-local snapshot path from the user or project instructions.
4. Register and export the docs with `disgust-docs add <alias> <repo-url> --branch <base-branch> --mode readOnly|pr --path <path>`.
5. Default to `readOnly` unless the user or project rules explicitly allow pull-request publication.
6. Run `disgust-docs status <alias>` and confirm that the snapshot is `synced`.
7. Commit `.disgust-docs.yml` and `.gitignore` only when the user asks to persist the connection. Never commit the generated snapshot or `.disgust-docs/` state.

Use `templates/disgust-docs.yml` only as a shape reference. Never copy placeholder URLs or branches into a real project.

## Reading Documentation

1. Inspect `.disgust-docs.yml` to find the relevant alias and snapshot path.
2. Run `disgust-docs status [alias]`.
3. When the snapshot is missing, run `disgust-docs update [alias]`.
4. When the snapshot is `modified`, do not update until the changes are published or the user explicitly authorizes `--discard-local`.
5. Read the configured snapshot as ordinary local files. Start with its root README or documented entry point and search only the relevant area.

The snapshot intentionally contains no `.git`. Use `disgust-docs status` and `disgust-docs diff`, not the main project's Git status, to inspect documentation changes.

## Editing And Publishing

- Edit only the configured snapshot path for the selected alias.
- Publication is allowed only when the config entry has `mode: pr`.
- Before publishing, run `disgust-docs status <alias>` and `disgust-docs diff <alias>`.
- Review added, changed, and deleted files for secrets or unrelated generated output.
- Publish with:

```bash
disgust-docs publish <alias> \
  --branch <branch> \
  --message <commit-message> \
  --title <pr-title> \
  --body <pr-body>
```

- The first publish creates a branch and pull request. Later publishes reuse the recorded branch and PR; do not choose a different branch while that publication session is active.
- `publish` leaves the local snapshot unchanged. A later `update` replaces a fully published snapshot with the configured base branch.
- Never use `--discard-local` unless the user explicitly authorizes losing unpublished snapshot changes.
- Do not push the configured base branch directly.

## Errors And Recovery

- If `update` reports local changes, publish them or request explicit permission for `--discard-local`.
- If `publish` fails after pushing but before creating the PR, rerun the same publish command. The saved phase allows it to continue without a new documentation edit.
- If `publish` reports no changes, do not create an empty commit or PR.
- If `gh` is missing or unauthenticated, explain that GitHub CLI authentication is required.
- If the project already tracks the configured snapshot path, stop. The path must be removed from the project Git index before `update` can manage it.
- `readOnly` is a workflow guard. Actual write protection comes from GitHub permissions and branch protection.
- Symlinks, Git LFS materialization, automatic `AGENTS.md` patches, and direct base-branch pushes are outside the snapshot v1 contract.

## Disconnecting Documentation

1. Run `disgust-docs status <alias>` and inspect `disgust-docs diff <alias>` before removal.
2. If the snapshot is `modified`, publish the changes or stop and ask the user how to preserve them. Do not delete unpublished work.
3. After the user explicitly requests disconnection, run `disgust-docs remove <alias>`. Use `--yes` only when non-interactive removal was explicitly authorized.
4. Treat cleanup of the now-unused `.gitignore` entry as a separate project change; do not remove it automatically when another project rule may still rely on it.

## Templates

For commit and PR text, see `templates/publish.md`.
For a standalone config example, see `templates/disgust-docs.yml`.
