from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .errors import AgentDocsError


ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def config_path(project_root: Path) -> Path:
    return project_root / ".agent-docs.yml"


def gitignore_path(project_root: Path) -> Path:
    return project_root / ".gitignore"


def docs_dir(project_root: Path) -> Path:
    return project_root / ".agent-docs"


def state_path(project_root: Path) -> Path:
    return docs_dir(project_root) / "state.json"


def global_home() -> Path:
    return Path.home() / ".agent-docs"


def mirror_root() -> Path:
    return global_home() / "mirrors"


def mirror_id(repo_url: str) -> str:
    digest = hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:16]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", repo_url).strip("-._")
    cleaned = cleaned[-48:] if cleaned else "repo"
    return f"{cleaned}-{digest}.git"


def mirror_path(repo_url: str) -> Path:
    return mirror_root() / mirror_id(repo_url)


def validate_alias(alias: str) -> None:
    if not ALIAS_RE.match(alias) or alias in {".", ".."}:
        raise AgentDocsError(
            "Invalid alias. Use 1-64 letters, digits, dots, underscores, or hyphens; "
            "do not use path separators."
        )


def validate_repo_url(repo_url: str) -> None:
    if not repo_url:
        raise AgentDocsError("Invalid repo URL: it must be non-empty.")
    if repo_url.startswith("-"):
        raise AgentDocsError("Invalid repo URL: it must not start with '-'.")
    if repo_url.startswith(("/", ".", "~")):
        return
    if any(char.isspace() for char in repo_url):
        raise AgentDocsError("Invalid repo URL: remote URLs must contain no whitespace.")
    allowed_prefixes = (
        "git@",
        "ssh://",
        "https://",
        "file://",
    )
    if not repo_url.startswith(allowed_prefixes):
        raise AgentDocsError(
            "Invalid repo URL. Use git@, ssh://, https://, file://, or a local path."
        )


def validate_branch_name(branch: str) -> None:
    if not branch or branch.startswith("-"):
        raise AgentDocsError("Invalid branch name.")
    forbidden = ["..", "@{", "\\", "//", " "]
    if any(token in branch for token in forbidden):
        raise AgentDocsError("Invalid branch name: contains forbidden git ref characters.")
    if branch.startswith("/") or branch.endswith("/") or branch.endswith("."):
        raise AgentDocsError("Invalid branch name.")
    if branch.endswith(".lock"):
        raise AgentDocsError("Invalid branch name: must not end with .lock.")


def validate_doc_path(project_root: Path, raw_path: str, alias: str) -> Path:
    if not raw_path:
        raw_path = f".agent-docs/{alias}"
    candidate = (project_root / raw_path).resolve()
    allowed = docs_dir(project_root).resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise AgentDocsError("Doc path must stay inside .agent-docs/.") from exc
    if candidate == allowed:
        raise AgentDocsError("Doc path must point to a child of .agent-docs/.")
    return candidate
