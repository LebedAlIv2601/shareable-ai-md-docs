from __future__ import annotations

import argparse
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import DisgustDocsConfig, DocConfig, add_doc, empty_config, load_config, remove_doc, save_config
from .errors import DisgustDocsError
from .git_ops import (
    build_manifest,
    commit_all,
    create_pr,
    current_commit,
    ensure_cache,
    ensure_not_tracked_by_project,
    export_commit,
    prepare_publish_checkout,
    push_branch,
    remove_path_if_safe,
    replace_checkout_contents,
    replace_snapshot,
    require_gh,
    resolve_remote_commit,
    run_git,
)
from .paths import docs_dir, gitignore_path, validate_alias, validate_branch_name, validate_doc_path
from .skill_installer import install_skill
from .state import SnapshotState, load_state, save_state, update_snapshot, with_snapshot, without_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="disgust-docs")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Project root. Defaults to current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("setup", help="Create config and ignore local docs snapshots.")
    subparsers.add_parser("init", help="Deprecated alias for setup.")

    add_parser = subparsers.add_parser("add", help="Register and update a docs snapshot.")
    add_parser.add_argument("alias")
    add_parser.add_argument("repo")
    add_parser.add_argument("--branch", default="main")
    add_parser.add_argument("--mode", choices=["readOnly", "pr"], default="readOnly")
    add_parser.add_argument("--provider", choices=["github"], default="github")
    add_parser.add_argument("--path")

    update_parser = subparsers.add_parser("update", help="Fetch and export docs snapshots.")
    update_parser.add_argument("alias", nargs="?")
    update_parser.add_argument(
        "--discard-local",
        action="store_true",
        help="Replace unpublished local docs changes.",
    )

    sync_parser = subparsers.add_parser("sync", help="Deprecated alias for update.")
    sync_parser.add_argument("alias", nargs="?")
    sync_parser.add_argument("--discard-local", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show docs snapshot status.")
    status_parser.add_argument("alias", nargs="?")

    diff_parser = subparsers.add_parser("diff", help="Show local docs changes from the last update.")
    diff_parser.add_argument("alias")

    publish_parser = subparsers.add_parser("publish", help="Publish snapshot changes through a GitHub PR.")
    publish_parser.add_argument("alias")
    publish_parser.add_argument("--branch")
    publish_parser.add_argument("--message", required=True)
    publish_parser.add_argument("--title", required=True)
    publish_parser.add_argument("--body", default="")

    remove_parser = subparsers.add_parser("remove", help="Remove registration and local snapshot.")
    remove_parser.add_argument("alias")
    remove_parser.add_argument("--yes", action="store_true", help="Skip confirmation.")

    skill_parser = subparsers.add_parser("skill", help="Manage the bundled agent skill.")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)
    skill_install_parser = skill_subparsers.add_parser("install", help="Install the bundled agent skill.")
    skill_install_parser.add_argument(
        "--global",
        action="store_true",
        dest="global_install",
        help="Install to ${CODEX_HOME:-~/.codex}/skills instead of .agents/skills.",
    )

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
    if args.command in {"setup", "init"}:
        command_setup(project_root)
    elif args.command == "add":
        command_add(args, project_root)
    elif args.command in {"update", "sync"}:
        command_update(project_root, args.alias, args.discard_local)
    elif args.command == "status":
        command_status(project_root, args.alias)
    elif args.command == "diff":
        command_diff(project_root, args.alias)
    elif args.command == "publish":
        command_publish(
            project_root,
            args.alias,
            args.branch,
            args.message,
            args.title,
            args.body,
        )
    elif args.command == "remove":
        command_remove(project_root, args.alias, args.yes)
    elif args.command == "skill" and args.skill_command == "install":
        command_skill_install(project_root, args.global_install)
    else:
        raise DisgustDocsError(f"Unknown command: {args.command}")


def command_setup(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    config_file = project_root / ".disgust-docs.yml"
    if not config_file.exists():
        save_config(project_root, empty_config())
        print("Created .disgust-docs.yml")
        config = empty_config()
    else:
        config = load_config(project_root)
        print(".disgust-docs.yml already exists")
    docs_dir(project_root).mkdir(parents=True, exist_ok=True)
    snapshot_paths = [doc.path for doc in config.docs.values()] or ["docs"]
    ensure_gitignore_entries(project_root, [".disgust-docs", *snapshot_paths])


def command_add(args: argparse.Namespace, project_root: Path) -> None:
    config = load_config(project_root, required=False)
    raw_path = args.path or ("docs" if not config.docs else f"docs/{args.alias}")
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
    docs_dir(project_root).mkdir(parents=True, exist_ok=True)
    ensure_gitignore_entries(project_root, [".disgust-docs", raw_path])
    print(f"Registered docs '{args.alias}'")
    command_update(project_root, args.alias, discard_local=False)


def command_update(project_root: Path, alias: str | None, discard_local: bool) -> None:
    config = load_config(project_root)
    state = load_state(project_root)
    docs_dir(project_root).mkdir(parents=True, exist_ok=True)
    for doc in selected_docs(config, alias):
        path = validate_doc_path(project_root, doc.path, doc.alias)
        ensure_gitignore_entries(project_root, [".disgust-docs", doc.path])
        ensure_not_tracked_by_project(project_root, doc.path)
        previous = state.snapshots.get(doc.alias)
        _ensure_update_is_safe(path, previous, doc, discard_local)

        cache = ensure_cache(doc)
        commit = resolve_remote_commit(cache, doc.branch)
        with tempfile.TemporaryDirectory(prefix=f"update-{doc.alias}-", dir=docs_dir(project_root)) as temporary:
            staging = Path(temporary) / "snapshot"
            export_commit(cache, commit, staging)
            manifest = build_manifest(staging)
            replace_snapshot(staging, path)

        snapshot = SnapshotState(
            alias=doc.alias,
            repo=doc.repo,
            branch=doc.branch,
            path=doc.path,
            base_commit=commit,
            base_manifest=manifest,
        )
        state = with_snapshot(state, snapshot)
        save_state(project_root, state)
        print(f"Updated {doc.alias} -> {doc.path} @ {commit[:12]}")


def command_status(project_root: Path, alias: str | None) -> None:
    config = load_config(project_root)
    state = load_state(project_root)
    docs = selected_docs(config, alias)
    if not docs:
        print("No docs configured.")
        return
    for doc in docs:
        path = validate_doc_path(project_root, doc.path, doc.alias)
        snapshot = state.snapshots.get(doc.alias)
        status = _snapshot_status(path, snapshot)
        commit = snapshot.base_commit[:12] if snapshot else "-"
        publish_branch = snapshot.publish_branch if snapshot and snapshot.publish_branch else "-"
        pr_url = snapshot.pr_url if snapshot and snapshot.pr_url else "-"
        print(
            f"{doc.alias}\tmode={doc.mode}\tstate={status}\tbranch={doc.branch}"
            f"\tcommit={commit}\tpublish_branch={publish_branch}\tpr={pr_url}\tpath={doc.path}"
        )


def command_diff(project_root: Path, alias: str) -> None:
    validate_alias(alias)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    state = load_state(project_root)
    snapshot = state.snapshots.get(alias)
    if snapshot is None:
        raise DisgustDocsError(f"Docs '{alias}' has no local snapshot. Run update first.")
    _ensure_snapshot_matches_config(snapshot, doc)
    path = validate_doc_path(project_root, doc.path, doc.alias)
    if not path.exists():
        raise DisgustDocsError(f"Docs snapshot is missing: {path}")
    cache = ensure_cache(doc)
    with tempfile.TemporaryDirectory(prefix=f"diff-{alias}-", dir=docs_dir(project_root)) as temporary:
        base = Path(temporary) / "base"
        export_commit(cache, snapshot.base_commit, base)
        completed = run_git(
            ["diff", "--no-index", "--no-prefix", "--", str(base), str(path)],
            cwd=project_root,
            check=False,
        )
    if completed.returncode not in {0, 1}:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise DisgustDocsError(f"Could not compare docs snapshot.\n{details}")
    if completed.stdout:
        print(completed.stdout, end="")
    else:
        print(f"No local documentation changes for {alias}.")


def command_publish(
    project_root: Path,
    alias: str,
    requested_branch: str | None,
    message: str,
    title: str,
    body: str,
) -> None:
    validate_alias(alias)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    if doc.mode != "pr":
        raise DisgustDocsError(f"Docs '{alias}' is {doc.mode}; publish requires mode: pr.")
    state = load_state(project_root)
    snapshot = state.snapshots.get(alias)
    if snapshot is None:
        raise DisgustDocsError(f"Docs '{alias}' has no local snapshot. Run 'disgust-docs update {alias}' first.")
    _ensure_snapshot_matches_config(snapshot, doc)
    path = validate_doc_path(project_root, doc.path, doc.alias)
    manifest = build_manifest(path)

    if snapshot.pr_url and snapshot.published_manifest == manifest:
        print(snapshot.pr_url)
        print(f"No new local changes for {alias}; existing pull request is unchanged.")
        return
    if not snapshot.publish_branch and manifest == snapshot.base_manifest:
        raise DisgustDocsError("No documentation changes to publish.")

    branch = snapshot.publish_branch or requested_branch or _default_publish_branch(project_root, alias)
    validate_branch_name(branch)
    if branch == doc.branch:
        raise DisgustDocsError("Publish branch must differ from the base branch.")
    if snapshot.publish_branch and requested_branch and requested_branch != snapshot.publish_branch:
        raise DisgustDocsError(
            f"Snapshot already publishes through branch '{snapshot.publish_branch}'."
        )

    require_gh()
    cache = ensure_cache(doc)
    with tempfile.TemporaryDirectory(prefix=f"publish-{alias}-", dir=docs_dir(project_root)) as temporary:
        checkout = Path(temporary) / "checkout"
        prepare_publish_checkout(
            doc,
            cache,
            checkout,
            snapshot.base_commit,
            branch,
            existing_branch=snapshot.publish_branch is not None,
        )
        replace_checkout_contents(path, checkout)
        committed = commit_all(checkout, message)
        if committed:
            published_commit = current_commit(checkout)
            state = update_snapshot(
                state,
                alias,
                phase="prepared",
                publish_branch=branch,
            )
            save_state(project_root, state)
            push_branch(checkout, branch)
            state = update_snapshot(
                state,
                alias,
                phase="pushed",
                published_commit=published_commit,
                published_manifest=manifest,
            )
            save_state(project_root, state)
        elif snapshot.publish_branch is None:
            raise DisgustDocsError("No documentation changes to publish.")
        elif state.snapshots[alias].published_manifest != manifest:
            state = update_snapshot(
                state,
                alias,
                phase="pushed",
                published_commit=current_commit(checkout),
                published_manifest=manifest,
            )
            save_state(project_root, state)

        current = state.snapshots[alias]
        if current.pr_url:
            pr_url = current.pr_url
        else:
            pr_url = create_pr(checkout, title, body, doc.branch, branch)
            state = update_snapshot(
                state,
                alias,
                phase="published",
                publish_branch=branch,
                published_manifest=manifest,
                pr_url=pr_url,
            )
            save_state(project_root, state)

    print(pr_url or "Created pull request.")
    print(f"Kept local docs snapshot unchanged at {doc.path}")


def command_remove(project_root: Path, alias: str, yes: bool) -> None:
    validate_alias(alias)
    config = load_config(project_root)
    doc = require_doc(config, alias)
    state = load_state(project_root)
    snapshot = state.snapshots.get(alias)
    path = validate_doc_path(project_root, doc.path, doc.alias)
    if snapshot is None and path.exists():
        raise DisgustDocsError(f"Refusing to remove unmanaged docs path: {path}")
    if snapshot is not None:
        current = build_manifest(path)
        safely_published = snapshot.pr_url and snapshot.published_manifest == current
        if current != snapshot.base_manifest and not safely_published:
            raise DisgustDocsError(
                f"Docs snapshot has unpublished local changes and will not be removed: {path}"
            )
    if not yes and not confirm(f"Remove docs registration '{alias}' and local snapshot?"):
        raise DisgustDocsError("Remove cancelled.")
    remove_path_if_safe(path)
    save_config(project_root, remove_doc(config, alias))
    save_state(project_root, without_snapshot(state, alias))
    print(f"Removed docs '{alias}'")


def command_skill_install(project_root: Path, global_install: bool) -> None:
    path = install_skill(project_root, global_install=global_install)
    print(f"Installed disgust-docs skill -> {path}")


def ensure_gitignore_entries(project_root: Path, paths: list[str]) -> None:
    gitignore = gitignore_path(project_root)
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = existing.splitlines()
    entries: list[str] = []
    for raw_path in paths:
        normalized = Path(raw_path).as_posix().strip("/")
        entry = f"/{normalized}/"
        if entry not in entries:
            entries.append(entry)
    if not entries:
        return
    # Keep managed exclusions after user-authored negation rules so snapshots
    # remain effectively ignored, not merely mentioned somewhere in the file.
    retained = [line for line in lines if line not in entries]
    payload = "\n".join([*retained, *entries]) + "\n"
    if payload != existing:
        gitignore.write_text(payload, encoding="utf-8")


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


def _ensure_update_is_safe(
    path: Path,
    snapshot: SnapshotState | None,
    doc: DocConfig,
    discard_local: bool,
) -> None:
    if not path.exists():
        return
    current = build_manifest(path)
    if snapshot is None:
        if not discard_local:
            raise DisgustDocsError(
                f"Docs path already exists but is not managed: {path}. Use --discard-local to replace it."
            )
        return
    if (snapshot.repo, snapshot.branch, snapshot.path) != (doc.repo, doc.branch, doc.path):
        if discard_local:
            return
        _ensure_snapshot_matches_config(snapshot, doc)
    if current == snapshot.base_manifest:
        return
    if snapshot.pr_url and snapshot.published_manifest == current:
        return
    if not discard_local:
        raise DisgustDocsError(
            f"Local documentation changes would be overwritten: {path}. "
            "Publish them or use --discard-local."
        )


def _ensure_snapshot_matches_config(snapshot: SnapshotState, doc: DocConfig) -> None:
    if (snapshot.repo, snapshot.branch, snapshot.path) != (doc.repo, doc.branch, doc.path):
        raise DisgustDocsError(
            f"Config for '{doc.alias}' changed after the last update. Run update with --discard-local."
        )


def _snapshot_status(path: Path, snapshot: SnapshotState | None) -> str:
    if not path.exists():
        return "missing"
    if snapshot is None:
        return "unmanaged"
    manifest = build_manifest(path)
    if manifest == snapshot.base_manifest:
        return "synced"
    if snapshot.pr_url and manifest == snapshot.published_manifest:
        return "published"
    if snapshot.publish_branch and manifest == snapshot.published_manifest:
        return snapshot.phase
    return "modified"


def _default_publish_branch(project_root: Path, alias: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project_root.name).strip("-._") or "project"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"disgust-docs/{slug}-{alias}-{timestamp}"
