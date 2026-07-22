from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from contextlib import contextmanager
from typing import BinaryIO, Iterator
from pathlib import Path, PurePosixPath

from .config import DocConfig
from .errors import DisgustDocsError
from .paths import repo_cache_path


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
        raise DisgustDocsError(f"Command failed: {command}\n{details}")
    return completed


def ensure_cache(doc: DocConfig) -> Path:
    cache = repo_cache_path(doc.repo)
    with _cache_lock(cache):
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            valid = run_git(["rev-parse", "--is-inside-work-tree"], cwd=cache, check=False)
            if valid.returncode != 0 or valid.stdout.strip() != "true":
                raise DisgustDocsError(f"Docs cache is not a git repository: {cache}")
        else:
            run_git(["clone", _repo_argument(doc.repo), str(cache)])
        run_git(["fetch", "--prune", "origin"], cwd=cache)
    return cache


def resolve_remote_commit(cache: Path, branch: str) -> str:
    ref = f"refs/remotes/origin/{branch}"
    completed = run_git(["rev-parse", "--verify", ref], cwd=cache, check=False)
    if completed.returncode != 0:
        raise DisgustDocsError(f"Branch not found in docs repository: {branch}")
    return completed.stdout.strip()


def export_commit(cache: Path, commit: str, destination: Path) -> None:
    if destination.exists():
        raise DisgustDocsError(f"Snapshot staging path already exists: {destination}")
    destination.mkdir(parents=True)
    with tempfile.NamedTemporaryFile(prefix="disgust-docs-", suffix=".tar", delete=False) as handle:
        archive_path = Path(handle.name)
    try:
        run_git(["archive", "--format=tar", "--output", str(archive_path), commit], cwd=cache)
        with tarfile.open(archive_path, "r") as archive:
            members = archive.getmembers()
            for member in members:
                _validate_archive_member(member)
            archive.extractall(destination, members=members)
    finally:
        archive_path.unlink(missing_ok=True)


def build_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_dir():
        raise DisgustDocsError(f"Docs snapshot must be a real directory: {path}")
    manifest: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise DisgustDocsError(f"Symlinks are not supported in docs snapshots: {item}")
        if item.is_file():
            relative = item.relative_to(path).as_posix()
            manifest[relative] = _sha256(item)
    return manifest


def ensure_not_tracked_by_project(project_root: Path, raw_path: str) -> None:
    inside = run_git(["rev-parse", "--is-inside-work-tree"], cwd=project_root, check=False)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return
    tracked = run_git(["ls-files", "--", raw_path], cwd=project_root)
    if tracked.stdout.strip():
        raise DisgustDocsError(
            f"Docs path is already tracked by the project repository: {raw_path}. "
            "Remove it from the project index before running update."
        )


def replace_snapshot(staging: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise DisgustDocsError(f"Refusing to replace non-directory docs path: {target}")
    backup = target.parent / f".{target.name}.disgust-backup-{uuid.uuid4().hex[:8]}"
    had_target = target.exists()
    if had_target:
        target.rename(backup)
    try:
        staging.rename(target)
    except Exception:
        if had_target and backup.exists() and not target.exists():
            backup.rename(target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def prepare_publish_checkout(
    doc: DocConfig,
    cache: Path,
    destination: Path,
    base_commit: str,
    branch: str,
    *,
    existing_branch: bool,
) -> None:
    run_git(
        [
            "clone",
            "--no-checkout",
            "--reference-if-able",
            str(cache),
            _repo_argument(doc.repo),
            str(destination),
        ]
    )
    remote_ref = f"refs/remotes/origin/{branch}"
    remote_exists = ref_exists(destination, remote_ref)
    if existing_branch:
        if remote_exists:
            run_git(["checkout", "-B", branch, remote_ref], cwd=destination)
        else:
            run_git(["checkout", "-b", branch, base_commit], cwd=destination)
    else:
        if remote_exists:
            raise DisgustDocsError(
                f"Remote branch already exists and is not managed by this snapshot: {branch}"
            )
        run_git(["checkout", "-b", branch, base_commit], cwd=destination)


def replace_checkout_contents(source: Path, checkout: Path) -> None:
    build_manifest(source)
    for child in checkout.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in source.iterdir():
        if child.name == ".git":
            raise DisgustDocsError("Docs snapshot must not contain .git.")
        destination = checkout / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def commit_all(path: Path, message: str) -> bool:
    status = run_git(["status", "--porcelain"], cwd=path)
    if not status.stdout.strip():
        return False
    run_git(["add", "--all"], cwd=path)
    run_git(["commit", "-m", message], cwd=path)
    return True


def current_commit(path: Path) -> str:
    completed = run_git(["rev-parse", "HEAD"], cwd=path)
    return completed.stdout.strip()


def push_branch(path: Path, branch: str) -> None:
    run_git(["push", "-u", "origin", f"HEAD:{branch}"], cwd=path)


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise DisgustDocsError("GitHub CLI 'gh' is required for publish but was not found.")
    auth = run(["gh", "auth", "status"], check=False)
    if auth.returncode != 0:
        details = auth.stderr.strip() or auth.stdout.strip()
        raise DisgustDocsError(f"GitHub CLI is not authenticated.\n{details}")


def create_pr(path: Path, title: str, body: str, base_branch: str, head_branch: str) -> str:
    args = [
        "gh",
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        base_branch,
        "--head",
        head_branch,
    ]
    completed = run(args, cwd=path)
    return completed.stdout.strip()


def ref_exists(repo: Path, ref: str) -> bool:
    completed = run_git(["rev-parse", "--verify", ref], cwd=repo, check=False)
    return completed.returncode == 0


def remove_path_if_safe(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _validate_archive_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise DisgustDocsError(f"Unsafe path in docs archive: {member.name}")
    if not (member.isdir() or member.isfile()):
        raise DisgustDocsError(
            f"Unsupported non-file entry in docs repository: {member.name}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_argument(repo: str) -> str:
    return str(Path(repo).expanduser()) if repo.startswith("~") else repo


@contextmanager
def _cache_lock(cache: Path) -> Iterator[None]:
    lock_root = cache.parent.parent / "locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{cache.name}.lock"
    with lock_path.open("a+b") as handle:
        _lock(handle)
        try:
            yield
        finally:
            _unlock(handle)


def _lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        if not handle.read(1):
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
