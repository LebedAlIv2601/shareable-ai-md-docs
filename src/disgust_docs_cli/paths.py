from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .errors import DisgustDocsError


ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def config_path(project_root: Path) -> Path:
    return project_root / ".disgust-docs.yml"


def gitignore_path(project_root: Path) -> Path:
    return project_root / ".gitignore"


def docs_dir(project_root: Path) -> Path:
    return project_root / ".disgust-docs"


def state_path(project_root: Path) -> Path:
    return docs_dir(project_root) / "state.json"


def global_home() -> Path:
    return Path.home() / ".disgust-docs"


def repo_cache_id(repo_url: str) -> str:
    digest = hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:16]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", repo_url).strip("-._")
    cleaned = cleaned[-48:] if cleaned else "repo"
    return f"{cleaned}-{digest}"


def repo_cache_root() -> Path:
    return global_home() / "repos"


def repo_cache_path(repo_url: str) -> Path:
    return repo_cache_root() / repo_cache_id(repo_url)


def validate_alias(alias: str) -> None:
    if not ALIAS_RE.match(alias) or alias in {".", ".."}:
        raise DisgustDocsError(
            "Invalid alias. Use 1-64 letters, digits, dots, underscores, or hyphens; "
            "do not use path separators."
        )


def validate_repo_url(repo_url: str) -> None:
    if not repo_url:
        raise DisgustDocsError("Invalid repo URL: it must be non-empty.")
    if repo_url.startswith("-"):
        raise DisgustDocsError("Invalid repo URL: it must not start with '-'.")
    if repo_url.startswith(("/", ".", "~")):
        return
    if any(char.isspace() for char in repo_url):
        raise DisgustDocsError("Invalid repo URL: remote URLs must contain no whitespace.")
    allowed_prefixes = (
        "git@",
        "ssh://",
        "https://",
        "file://",
    )
    if not repo_url.startswith(allowed_prefixes):
        raise DisgustDocsError(
            "Invalid repo URL. Use git@, ssh://, https://, file://, or a local path."
        )


def validate_branch_name(branch: str) -> None:
    if not branch or branch.startswith("-"):
        raise DisgustDocsError("Invalid branch name.")
    forbidden = ["..", "@{", "\\", "//", " "]
    if any(token in branch for token in forbidden):
        raise DisgustDocsError("Invalid branch name: contains forbidden git ref characters.")
    if branch.startswith("/") or branch.endswith("/") or branch.endswith("."):
        raise DisgustDocsError("Invalid branch name.")
    if branch.endswith(".lock"):
        raise DisgustDocsError("Invalid branch name: must not end with .lock.")


def validate_doc_path(project_root: Path, raw_path: str, alias: str) -> Path:
    if not raw_path:
        raw_path = "docs" if alias == "product" else f"docs/{alias}"
    raw = Path(raw_path)
    if raw.is_absolute():
        raise DisgustDocsError("Doc path must be relative to the project root.")
    if ".." in raw.parts:
        raise DisgustDocsError("Doc path must not contain '..'.")
    candidate = (project_root / raw_path).resolve()
    allowed = project_root.resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise DisgustDocsError("Doc path must stay inside the project root.") from exc
    if candidate == allowed:
        raise DisgustDocsError("Doc path must point to a child of the project root.")
    relative = candidate.relative_to(allowed)
    if relative.parts[0] == ".git":
        raise DisgustDocsError("Doc path must not point inside .git/.")
    internal = docs_dir(project_root).resolve()
    try:
        candidate.relative_to(internal)
    except ValueError:
        pass
    else:
        raise DisgustDocsError("Doc path must not point inside disgust-docs internal state directory.")
    return candidate
