from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import DocConfig
from .errors import AgentDocsError
from .paths import mirror_path


def run_git(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=cwd, check=check)


def run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        command = " ".join(args)
        details = completed.stderr.strip() or completed.stdout.strip()
        raise AgentDocsError(f"Command failed: {command}\n{details}")
    return completed


def ensure_mirror(doc: DocConfig) -> Path:
    mirror = mirror_path(doc.repo)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    if mirror.exists():
        fetch_mirror(mirror)
        return mirror
    run_git(["clone", "--mirror", doc.repo, str(mirror)])
    return mirror


def fetch_mirror(mirror: Path) -> None:
    run_git(["--git-dir", str(mirror), "fetch", "--prune", "origin"])


def ensure_clean_worktree(path: Path) -> None:
    if not path.exists():
        return
    completed = run_git(["status", "--porcelain"], cwd=path)
    if completed.stdout.strip():
        raise AgentDocsError(f"Worktree has local changes and will not be overwritten: {path}")


def remove_worktree(path: Path, mirror: Path) -> None:
    if not path.exists():
        return
    completed = run_git(["--git-dir", str(mirror), "worktree", "remove", "--force", str(path)], check=False)
    if completed.returncode != 0:
        shutil.rmtree(path)
        run_git(["--git-dir", str(mirror), "worktree", "prune"], check=False)


def checkout_read_worktree(doc: DocConfig, path: Path) -> None:
    mirror = ensure_mirror(doc)
    ref = resolve_ref(mirror, doc.branch)
    if path.exists():
        ensure_clean_worktree(path)
        remove_worktree(path, mirror)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git(["--git-dir", str(mirror), "worktree", "add", "--detach", str(path), ref])


def checkout_edit_worktree(doc: DocConfig, path: Path, edit_branch: str) -> None:
    mirror = ensure_mirror(doc)
    ref = resolve_ref(mirror, doc.branch)
    if path.exists():
        ensure_clean_worktree(path)
        remove_worktree(path, mirror)
    path.parent.mkdir(parents=True, exist_ok=True)
    if ref_exists(mirror, f"refs/heads/{edit_branch}"):
        run_git(["--git-dir", str(mirror), "worktree", "add", str(path), edit_branch])
    else:
        run_git(["--git-dir", str(mirror), "worktree", "add", "-b", edit_branch, str(path), ref])


def resolve_ref(mirror: Path, branch: str) -> str:
    candidates = [f"refs/heads/{branch}", branch]
    for candidate in candidates:
        completed = run_git(["--git-dir", str(mirror), "rev-parse", "--verify", candidate], check=False)
        if completed.returncode == 0:
            return completed.stdout.strip()
    raise AgentDocsError(f"Branch not found in docs repository: {branch}")


def ref_exists(mirror: Path, ref: str) -> bool:
    completed = run_git(["--git-dir", str(mirror), "rev-parse", "--verify", ref], check=False)
    return completed.returncode == 0


def current_commit(path: Path) -> str:
    if not path.exists():
        return "-"
    completed = run_git(["rev-parse", "--short", "HEAD"], cwd=path, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else "-"


def current_branch(path: Path) -> str:
    if not path.exists():
        return "-"
    completed = run_git(["branch", "--show-current"], cwd=path, check=False)
    branch = completed.stdout.strip()
    return branch or "detached"


def dirty_state(path: Path) -> str:
    if not path.exists():
        return "missing"
    completed = run_git(["status", "--porcelain"], cwd=path, check=False)
    if completed.returncode != 0:
        return "invalid"
    return "dirty" if completed.stdout.strip() else "clean"


def commit_all(path: Path, message: str) -> bool:
    ensure_git_worktree(path)
    status = run_git(["status", "--porcelain"], cwd=path)
    if not status.stdout.strip():
        return False
    run_git(["add", "--all"], cwd=path)
    run_git(["commit", "-m", message], cwd=path)
    return True


def ensure_git_worktree(path: Path) -> None:
    completed = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise AgentDocsError(f"Not a git worktree: {path}")


def push_branch(path: Path, branch: str) -> None:
    run_git(["-c", "remote.origin.mirror=false", "push", "-u", "origin", f"HEAD:{branch}"], cwd=path)


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise AgentDocsError("GitHub CLI 'gh' is required for publish but was not found.")
    auth = run(["gh", "auth", "status"], check=False)
    if auth.returncode != 0:
        details = auth.stderr.strip() or auth.stdout.strip()
        raise AgentDocsError(f"GitHub CLI is not authenticated.\n{details}")


def create_pr(path: Path, title: str, body: str, base_branch: str) -> str:
    args = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base_branch]
    completed = run(args, cwd=path)
    return completed.stdout.strip()


def remove_path_if_safe(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
