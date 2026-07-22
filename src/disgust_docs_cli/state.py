from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import DisgustDocsError
from .paths import state_path


Manifest = dict[str, str]


@dataclass(frozen=True)
class SnapshotState:
    alias: str
    repo: str
    branch: str
    path: str
    base_commit: str
    base_manifest: Manifest
    phase: str = "synced"
    publish_branch: str | None = None
    published_commit: str | None = None
    published_manifest: Manifest | None = None
    pr_url: str | None = None


@dataclass(frozen=True)
class LocalState:
    snapshots: dict[str, SnapshotState]


def load_state(project_root: Path) -> LocalState:
    path = state_path(project_root)
    if not path.exists():
        return LocalState(snapshots={})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DisgustDocsError(f"Invalid disgust-docs local state: {path}") from exc
    if data.get("edits"):
        raise DisgustDocsError(
            "Legacy worktree edit state detected. Finish or abort it with disgust-docs 0.1.x before upgrading."
        )
    raw_snapshots = data.get("snapshots", {})
    if not isinstance(raw_snapshots, dict):
        raise DisgustDocsError("Invalid disgust-docs local state: snapshots must be an object.")
    snapshots: dict[str, SnapshotState] = {}
    try:
        for alias, raw in raw_snapshots.items():
            snapshots[alias] = SnapshotState(
                alias=alias,
                repo=raw["repo"],
                branch=raw["branch"],
                path=raw["path"],
                base_commit=raw["base_commit"],
                base_manifest=_manifest(raw.get("base_manifest", {})),
                phase=raw.get("phase", "synced"),
                publish_branch=raw.get("publish_branch"),
                published_commit=raw.get("published_commit"),
                published_manifest=(
                    _manifest(raw["published_manifest"])
                    if raw.get("published_manifest") is not None
                    else None
                ),
                pr_url=raw.get("pr_url"),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise DisgustDocsError("Invalid disgust-docs local state fields.") from exc
    return LocalState(snapshots=snapshots)


def save_state(project_root: Path, state: LocalState) -> None:
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "version": 2,
        "snapshots": {
            alias: {
                "repo": snapshot.repo,
                "branch": snapshot.branch,
                "path": snapshot.path,
                "base_commit": snapshot.base_commit,
                "base_manifest": snapshot.base_manifest,
                "phase": snapshot.phase,
                "publish_branch": snapshot.publish_branch,
                "published_commit": snapshot.published_commit,
                "published_manifest": snapshot.published_manifest,
                "pr_url": snapshot.pr_url,
            }
            for alias, snapshot in sorted(state.snapshots.items())
        },
    }
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix="state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def with_snapshot(state: LocalState, snapshot: SnapshotState) -> LocalState:
    snapshots = dict(state.snapshots)
    snapshots[snapshot.alias] = snapshot
    return LocalState(snapshots=snapshots)


def update_snapshot(state: LocalState, alias: str, **changes: object) -> LocalState:
    snapshot = state.snapshots[alias]
    return with_snapshot(state, replace(snapshot, **changes))


def without_snapshot(state: LocalState, alias: str) -> LocalState:
    snapshots = dict(state.snapshots)
    snapshots.pop(alias, None)
    return LocalState(snapshots=snapshots)


def _manifest(value: Any) -> Manifest:
    if not isinstance(value, dict):
        raise TypeError("manifest must be an object")
    result: Manifest = {}
    for path, digest in value.items():
        if not isinstance(path, str) or not isinstance(digest, str):
            raise TypeError("manifest entries must be strings")
        result[path] = digest
    return result
