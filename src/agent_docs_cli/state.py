from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import state_path


@dataclass(frozen=True)
class EditSession:
    alias: str
    branch: str
    base_branch: str
    path: str


@dataclass(frozen=True)
class LocalState:
    edits: dict[str, EditSession]


def load_state(project_root: Path) -> LocalState:
    path = state_path(project_root)
    if not path.exists():
        return LocalState(edits={})
    data = json.loads(path.read_text(encoding="utf-8"))
    edits: dict[str, EditSession] = {}
    for alias, raw in data.get("edits", {}).items():
        edits[alias] = EditSession(
            alias=alias,
            branch=raw["branch"],
            base_branch=raw["base_branch"],
            path=raw["path"],
        )
    return LocalState(edits=edits)


def save_state(project_root: Path, state: LocalState) -> None:
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "edits": {
            alias: {
                "branch": edit.branch,
                "base_branch": edit.base_branch,
                "path": edit.path,
            }
            for alias, edit in sorted(state.edits.items())
        }
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def with_edit(state: LocalState, edit: EditSession) -> LocalState:
    edits = dict(state.edits)
    edits[edit.alias] = edit
    return LocalState(edits=edits)


def without_edit(state: LocalState, alias: str) -> LocalState:
    edits = dict(state.edits)
    edits.pop(alias, None)
    return LocalState(edits=edits)
