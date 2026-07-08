---
name: disgust-docs
description: "Work with shared Markdown documentation through the disgust-docs CLI. Use when an agent needs to connect, sync, inspect, or safely update docs repositories from a local project using .disgust-docs.yml, .disgust-docs worktrees, and the PR flow."
---

# Disgust Docs

Use this skill for documentation connected through `disgust-docs`.

## Initial Setup

Use this flow when a project is not connected to shared docs yet.

1. Check whether `disgust-docs` is available by running `disgust-docs --help`.
2. If `.disgust-docs.yml` is missing, run `disgust-docs init` from the project root.
3. Before adding a docs repo, identify the intended alias, repository URL, base branch, and mode with the user or existing project instructions.
4. Add the docs repo with `disgust-docs add <alias> <repo-url> --branch <base-branch> --mode readOnly|pr`.
5. Use `mode: readOnly` unless the user or project rules explicitly allow docs edits through pull requests.
6. After setup, run `disgust-docs status <alias>` and confirm the configured path.
7. Commit `.disgust-docs.yml` and `.gitignore` changes in the consumer project when the user asks to persist the connection.

Use `templates/disgust-docs.yml` only as a starting point for the expected config shape. Do not copy placeholder aliases, URLs, or branches into a real project.

## Basic Flow

1. Find the project root and inspect `.disgust-docs.yml`.
2. Run `disgust-docs status` to understand alias, mode, state, branch, commit, dirty state, and path.
3. If no edit session is active, run `disgust-docs sync [alias]` before relying on current docs.
4. Treat the configured docs path as the boundary for that alias. Use whichever local tools are appropriate in the user's environment.

## Safe Editing

- Edit docs only when the entry has `mode: pr`.
- Start changes with `disgust-docs edit <alias> --branch <branch>`.
- Write only inside the configured docs path for that alias.
- Do not change `.disgust-docs.yml` just to update docs content.
- Do not commit or push the base branch directly.
- Do not bypass `readOnly`; if the entry is `readOnly`, propose a separate project change to switch it to `mode: pr`.
- Before publishing, check `disgust-docs status <alias>` and review the actual docs diff.
- Publish with `disgust-docs publish <alias> --message ... --title ... --body ...`.
- To close a clean edit session without publishing, use `disgust-docs abort <alias>`.

## Errors And Limits

- If `sync` reports an active edit session, finish it with `publish` or `abort` first.
- If `publish` reports no changes, do not create an empty PR.
- If `gh` is missing or unauthenticated, explain that publish requires GitHub CLI auth.
- If the worktree is dirty before `abort` or `remove`, do not delete changes without an explicit user request.
- Direct pushes to the base branch, writes outside `.disgust-docs/`, and automatic `AGENTS.md` patches are outside v1.

## Templates

For commit and PR text templates, see `templates/publish.md`.
For a standalone `.disgust-docs.yml` template, see `templates/disgust-docs.yml`.
