from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DisgustDocsConfig, DocConfig, add_doc, empty_config, load_config, remove_doc, save_config
from .errors import DisgustDocsError
from .git_ops import (
    checkout_edit_worktree,
    checkout_read_worktree,
    commit_all,
    create_pr,
    current_branch,
    current_commit,
    dirty_state,
    ensure_clean_worktree,
    push_branch,
    remove_path_if_safe,
    remove_worktree,
    require_gh,
)
from .paths import (
    docs_dir,
    gitignore_path,
    mirror_path,
    validate_alias,
    validate_branch_name,
    validate_doc_path,
)
from .state import EditSession, load_state, save_state, with_edit, without_edit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="disgust-docs")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Project root. Defaults to current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create .disgust-docs.yml and ignore .disgust-docs/.")

    add_parser = subparsers.add_parser("add", help="Register a docs repository.")
    add_parser.add_argument("alias")
    add_parser.add_argument("repo")
    add_parser.add_argument("--branch", default="main")
    add_parser.add_argument("--mode", choices=["readOnly", "pr"], default="readOnly")
    add_parser.add_argument("--provider", choices=["github"], default="github")
    add_parser.add_argument("--path")

    sync_parser = subparsers.add_parser("sync", help="Fetch and refresh docs worktrees.")
    sync_parser.add_argument("alias", nargs="?")

    status_parser = subparsers.add_parser("status", help="Show docs status.")
    status_parser.add_argument("alias", nargs="?")

    edit_parser = subparsers.add_parser("edit", help="Start an explicit docs edit session.")
    edit_parser.add_argument("alias")
    edit_parser.add_argument("--branch", required=True)

    publish_parser = subparsers.add_parser("publish", help="Commit, push, and open a GitHub PR.")
    publish_parser.add_argument("alias")
    publish_parser.add_argument("--message", required=True)
    publish_parser.add_argument("--title", required=True)
    publish_parser.add_argument("--body", default="")

    abort_parser = subparsers.add_parser("abort", help="Abort an edit session.")
    abort_parser.add_argument("alias")
    abort_parser.add_argument("--yes", action="store_true", help="Skip confirmation.")

    remove_parser = subparsers.add_parser("remove", help="Remove docs registration and local worktree.")
    remove_parser.add_argument("alias")
    remove_parser.add_argument("--yes", action="store_true", help="Skip confirmation.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = args.project.resolve()
    try:
        dispatch(args, project_root)
    except DisgustDocsError as exc:
        print(f"disgust-docs: {exc}", file=sys.stderr)
        return 1
    return 0


def dispatch(args: argparse.Namespace, project_root: Path) -> None:
    if args.command == "init":
        command_init(project_root)
    elif args.command == "add":
        command_add(args, project_root)
    elif args.command == "sync":
        command_sync(project_root, args.alias)
    elif args.command == "status":
        command_status(project_root, args.alias)
    elif args.command == "edit":
        command_edit(project_root, args.alias, args.branch)
    elif args.command == "publish":
        command_publish(project_root, args.alias, args.message, args.title, args.body)
    elif args.command == "abort":
        command_abort(project_root, args.alias, args.yes)
    elif args.command == "remove":
        command_remove(project_root, args.alias, args.yes)
    else:
        raise DisgustDocsError(f"Unknown command: {args.command}")


def command_init(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    config_file = project_root / ".disgust-docs.yml"
    if not config_file.exists():
        save_config(project_root, empty_config())
        print("Created .disgust-docs.yml")
    else:
        load_config(project_root)
        print(".disgust-docs.yml already exists")
    ensure_gitignore(project_root)
    docs_dir(project_root).mkdir(parents=True, exist_ok=True)


def command_add(args: argparse.Namespace, project_root: Path) -> None:
    config = load_config(project_root, required=False)
    raw_path = args.path or f".disgust-docs/{args.alias}"
    doc = DocConfig(
        alias=args.alias,
        repo=args.repo,
        branch=args.branch,
        provider=args.provider,
        mode=args.mode,
        path=raw_path,
    )
    config = add_doc(config, doc, project_root)
    save_config(project_root, config)
    ensure_gitignore(project_root)
    print(f"Registered docs '{args.alias}'")
    command_sync(project_root, args.alias)


def command_sync(project_root: Path, alias: str | None) -> None:
    config = load_config(project_root)
    state = load_state(project_root)
    docs = selected_docs(config, alias)
    for doc in docs:
        if doc.alias in state.edits:
            raise DisgustDocsError(f"Cannot sync '{doc.alias}' while an edit session is active.")
        path = validate_doc_path(project_root, doc.path, doc.alias)
        checkout_read_worktree(doc, path)
        print(f"Synced {doc.alias} -> {doc.path} @ {current_commit(path)}")


def command_status(project_root: Path, alias: str | None) -> None:
    config = load_config(project_root)
    state = load_state(project_root)
    docs = selected_docs(config, alias)
    if not docs:
        print("No docs configured.")
        return
    for doc in docs:
        path = validate_doc_path(project_root, doc.path, doc.alias)
        session = state.edits.get(doc.alias)
        active = f"edit:{session.branch}" if session else "read"
        print(
            f"{doc.alias}\tmode={doc.mode}\tstate={active}\tbranch={current_branch(path)}"
            f"\tcommit={current_commit(path)}\tdirty={dirty_state(path)}\tpath={doc.path}"
        )


def command_edit(project_root: Path, alias: str, branch: str) -> None:
    validate_alias(alias)
    validate_branch_name(branch)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    if doc.mode != "pr":
        raise DisgustDocsError(f"Docs '{alias}' is {doc.mode}; set mode: pr to edit.")
    state = load_state(project_root)
    if alias in state.edits:
        raise DisgustDocsError(f"Edit session already active for '{alias}'.")
    if branch == doc.branch:
        raise DisgustDocsError("Edit branch must differ from the base branch.")
    path = validate_doc_path(project_root, doc.path, doc.alias)
    checkout_edit_worktree(doc, path, branch)
    state = with_edit(
        state,
        EditSession(alias=alias, branch=branch, base_branch=doc.branch, path=doc.path),
    )
    save_state(project_root, state)
    print(f"Started edit session for {alias} on {branch}")


def command_publish(project_root: Path, alias: str, message: str, title: str, body: str) -> None:
    validate_alias(alias)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    if doc.mode != "pr":
        raise DisgustDocsError(f"Docs '{alias}' is {doc.mode}; publish requires mode: pr.")
    state = load_state(project_root)
    session = state.edits.get(alias)
    if not session:
        raise DisgustDocsError(f"No edit session active for '{alias}'. Run 'disgust-docs edit' first.")
    path = validate_doc_path(project_root, doc.path, doc.alias)
    require_gh()
    committed = commit_all(path, message)
    if not committed:
        raise DisgustDocsError("No documentation changes to publish.")
    push_branch(path, session.branch)
    pr_url = create_pr(path, title, body, session.base_branch)
    print(pr_url or "Created pull request.")
    state = without_edit(state, alias)
    save_state(project_root, state)
    remove_worktree(path, mirror_path(doc.repo))
    checkout_read_worktree(doc, path)
    print(f"Returned {alias} to read worktree on {doc.branch}")


def command_abort(project_root: Path, alias: str, yes: bool) -> None:
    validate_alias(alias)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    state = load_state(project_root)
    if alias not in state.edits:
        raise DisgustDocsError(f"No edit session active for '{alias}'.")
    path = validate_doc_path(project_root, doc.path, doc.alias)
    ensure_clean_worktree(path)
    if not yes and not confirm(f"Abort edit session for '{alias}' and discard its worktree?"):
        raise DisgustDocsError("Abort cancelled.")
    remove_worktree(path, mirror_path(doc.repo))
    state = without_edit(state, alias)
    save_state(project_root, state)
    checkout_read_worktree(doc, path)
    print(f"Aborted edit session for {alias}")


def command_remove(project_root: Path, alias: str, yes: bool) -> None:
    validate_alias(alias)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    path = validate_doc_path(project_root, doc.path, doc.alias)
    if dirty_state(path) == "dirty":
        raise DisgustDocsError(f"Docs worktree has local changes and will not be removed: {path}")
    if not yes and not confirm(f"Remove docs registration '{alias}' and local worktree?"):
        raise DisgustDocsError("Remove cancelled.")
    remove_worktree(path, mirror_path(doc.repo))
    remove_path_if_safe(path)
    save_config(project_root, remove_doc(config, alias))
    state = without_edit(load_state(project_root), alias)
    save_state(project_root, state)
    print(f"Removed docs '{alias}'")


def ensure_gitignore(project_root: Path) -> None:
    path = gitignore_path(project_root)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    if ".disgust-docs/" not in lines:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        existing += ".disgust-docs/\n"
        path.write_text(existing, encoding="utf-8")


def selected_docs(config: DisgustDocsConfig, alias: str | None) -> list[DocConfig]:
    if alias:
        return [require_doc(config, alias)]
    return [config.docs[key] for key in sorted(config.docs)]


def require_doc(config: DisgustDocsConfig, alias: str) -> DocConfig:
    validate_alias(alias)
    try:
        return config.docs[alias]
    except KeyError as exc:
        raise DisgustDocsError(f"Unknown docs alias: {alias}.") from exc


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}
