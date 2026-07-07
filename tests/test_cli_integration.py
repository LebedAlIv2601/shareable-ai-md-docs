from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["PYTHONPATH"] = str(ROOT / "src")
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "disgust_docs_cli", *args],
        cwd=cwd,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def make_docs_repo(root: Path) -> Path:
    docs = root / "pizza-docs"
    docs.mkdir()
    git(["init", "-b", "main"], cwd=docs)
    git(["config", "user.email", "tests@example.com"], cwd=docs)
    git(["config", "user.name", "Tests"], cwd=docs)
    (docs / "README.md").write_text("# Pizza Docs\n", encoding="utf-8")
    git(["add", "README.md"], cwd=docs)
    git(["commit", "-m", "Initial docs"], cwd=docs)
    return docs


class CliIntegrationTests(unittest.TestCase):
    def test_init_add_sync_creates_project_local_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()

            init = run(["init"], cwd=project, env={"HOME": str(home)})
            self.assertEqual(init.returncode, 0, init.stderr)

            add = run(
                ["add", "pizza", str(docs), "--branch", "main", "--mode", "pr"],
                cwd=project,
                env={"HOME": str(home)},
            )
            self.assertEqual(add.returncode, 0, add.stderr)

            self.assertTrue((project / ".disgust-docs.yml").exists())
            self.assertIn(".disgust-docs/", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertEqual(
                (project / ".disgust-docs" / "pizza" / "README.md").read_text(encoding="utf-8"),
                "# Pizza Docs\n",
            )
            status = run(["status"], cwd=project, env={"HOME": str(home)})
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("pizza\tmode=pr\tstate=read", status.stdout)

    def test_two_projects_can_sync_same_docs_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            home = root / "home"
            home.mkdir()
            for name in ["backend", "frontend"]:
                project = root / name
                project.mkdir()
                self.assertEqual(run(["init"], cwd=project, env={"HOME": str(home)}).returncode, 0)
                result = run(
                    ["add", "pizza", str(docs), "--branch", "main", "--mode", "readOnly"],
                    cwd=project,
                    env={"HOME": str(home)},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((project / ".disgust-docs" / "pizza" / "README.md").exists())

    def test_edit_requires_pr_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            self.assertEqual(run(["init"], cwd=project, env={"HOME": str(home)}).returncode, 0)
            self.assertEqual(
                run(["add", "pizza", str(docs), "--branch", "main", "--mode", "readOnly"], cwd=project, env={"HOME": str(home)}).returncode,
                0,
            )

            result = run(["edit", "pizza", "--branch", "docs/change"], cwd=project, env={"HOME": str(home)})

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mode: pr", result.stderr)

    def test_publish_uses_gh_and_returns_to_read_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            gh = fake_bin / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"auth\" ]; then exit 0; fi\n"
                "if [ \"$1\" = \"pr\" ]; then echo https://github.com/org/pizza-docs/pull/1; exit 0; fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            env = {
                "HOME": str(home),
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "GIT_AUTHOR_NAME": "Tests",
                "GIT_AUTHOR_EMAIL": "tests@example.com",
                "GIT_COMMITTER_NAME": "Tests",
                "GIT_COMMITTER_EMAIL": "tests@example.com",
            }

            self.assertEqual(run(["init"], cwd=project, env=env).returncode, 0)
            add = run(["add", "pizza", str(docs), "--branch", "main", "--mode", "pr"], cwd=project, env=env)
            self.assertEqual(add.returncode, 0, add.stderr)
            edit = run(["edit", "pizza", "--branch", "docs/change"], cwd=project, env=env)
            self.assertEqual(edit.returncode, 0, edit.stderr)
            docs_readme = project / ".disgust-docs" / "pizza" / "README.md"
            docs_readme.write_text("# Pizza Docs\n\nUpdated.\n", encoding="utf-8")

            published = run(
                [
                    "publish",
                    "pizza",
                    "--message",
                    "Update docs",
                    "--title",
                    "Update docs",
                    "--body",
                    "Test body",
                ],
                cwd=project,
                env=env,
            )

            self.assertEqual(published.returncode, 0, published.stderr)
            self.assertIn("https://github.com/org/pizza-docs/pull/1", published.stdout)
            self.assertIn("state=read", run(["status", "pizza"], cwd=project, env=env).stdout)
            branches = git(["branch", "--list", "docs/change"], cwd=docs).stdout
            self.assertIn("docs/change", branches)


if __name__ == "__main__":
    unittest.main()
