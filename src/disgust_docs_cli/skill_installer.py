from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path

from .errors import DisgustDocsError


SKILL_NAME = "disgust-docs"
SKILL_RESOURCE = ("resources", "skills", SKILL_NAME)


def install_skill(project_root: Path, *, global_install: bool) -> Path:
    target = global_skill_path() if global_install else project_skill_path(project_root)
    source = resources.files("disgust_docs_cli").joinpath(*SKILL_RESOURCE)
    if not source.is_dir():
        raise DisgustDocsError("Bundled disgust-docs skill is missing from the installed package.")
    replace_tree(source, target)
    return target


def project_skill_path(project_root: Path) -> Path:
    return project_root / ".agents" / "skills" / SKILL_NAME


def global_skill_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "skills" / SKILL_NAME


def replace_tree(source: resources.abc.Traversable, target: Path) -> None:
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_traversable_tree(source, target)


def copy_traversable_tree(source: resources.abc.Traversable, target: Path) -> None:
    target.mkdir()
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            copy_traversable_tree(child, destination)
        else:
            destination.write_bytes(child.read_bytes())
