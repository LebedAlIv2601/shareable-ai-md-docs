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


def commit_docs(docs: Path, text: str, message: str) -> None:
    (docs / "README.md").write_text(text, encoding="utf-8")
    git(["add", "README.md"], cwd=docs)
    git(["commit", "-m", message], cwd=docs)


def make_fake_gh(root: Path, *, fail_first_pr: bool = False) -> Path:
    fake_bin = root / "bin"
    fake_bin.mkdir()
    marker = root / "gh-pr-attempted"
    gh = fake_bin / "gh"
    failure = (
        f'if [ ! -f "{marker}" ]; then touch "{marker}"; echo temporary failure >&2; exit 1; fi\n'
        if fail_first_pr
        else ""
    )
    gh.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"auth\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"pr\" ]; then\n"
        f"{failure}"
        "  echo https://github.com/org/pizza-docs/pull/1\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def git_env(home: Path, fake_bin: Path | None = None) -> dict[str, str]:
    env = {
        "HOME": str(home),
        "GIT_AUTHOR_NAME": "Tests",
        "GIT_AUTHOR_EMAIL": "tests@example.com",
        "GIT_COMMITTER_NAME": "Tests",
        "GIT_COMMITTER_EMAIL": "tests@example.com",
    }
    if fake_bin:
        env["PATH"] = f"{fake_bin}:{os.environ['PATH']}"
    return env


class CliIntegrationTests(unittest.TestCase):
    def test_skill_install_creates_project_local_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "backend"
            project.mkdir()

            result = run(["skill", "install"], cwd=project)

            self.assertEqual(result.returncode, 0, result.stderr)
            skill = project / ".agents" / "skills" / "disgust-docs"
            self.assertTrue((skill / "SKILL.md").exists())
            self.assertTrue((skill / "agents" / "openai.yaml").exists())
            self.assertTrue((skill / "templates" / "publish.md").exists())
            self.assertTrue((skill / "templates" / "disgust-docs.yml").exists())
            skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("--project <project-root>", skill_text)
            self.assertIn("disgust-docs remove <alias>", skill_text)
            self.assertIn(str(skill), result.stdout)

    def test_skill_install_overwrites_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "backend"
            project.mkdir()
            skill = project / ".agents" / "skills" / "disgust-docs"
            skill.mkdir(parents=True)
            stale = skill / "stale.txt"
            stale.write_text("old\n", encoding="utf-8")

            result = run(["skill", "install"], cwd=project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(stale.exists())
            self.assertIn("name: disgust-docs", (skill / "SKILL.md").read_text(encoding="utf-8"))

    def test_skill_install_global_uses_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "backend"
            project.mkdir()
            codex_home = root / "codex-home"

            result = run(["skill", "install", "--global"], cwd=project, env={"CODEX_HOME": str(codex_home)})

            self.assertEqual(result.returncode, 0, result.stderr)
            skill = codex_home / "skills" / "disgust-docs"
            self.assertTrue((skill / "SKILL.md").exists())
            self.assertTrue((skill / "agents" / "openai.yaml").exists())

    def test_help_exposes_snapshot_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run(["--help"], cwd=Path(tmp))

            self.assertEqual(result.returncode, 0, result.stderr)
            for command in ["setup", "update", "status", "diff", "publish", "skill"]:
                self.assertIn(command, result.stdout)

    def test_global_project_option_targets_another_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "backend"
            project.mkdir()
            outside = root / "outside"
            outside.mkdir()

            result = run(["--project", str(project), "setup"], cwd=outside)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / ".disgust-docs.yml").exists())
            self.assertTrue((project / ".gitignore").exists())
            self.assertFalse((outside / ".disgust-docs.yml").exists())

    def test_setup_add_update_creates_gitless_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            env = git_env(home)

            setup = run(["setup"], cwd=project, env=env)
            self.assertEqual(setup.returncode, 0, setup.stderr)
            self.assertIn("# product:", (project / ".disgust-docs.yml").read_text(encoding="utf-8"))
            add = run(["add", "pizza", str(docs), "--mode", "pr"], cwd=project, env=env)

            self.assertEqual(add.returncode, 0, add.stderr)
            self.assertEqual((project / "docs" / "README.md").read_text(encoding="utf-8"), "# Pizza Docs\n")
            self.assertFalse((project / "docs" / ".git").exists())
            gitignore = (project / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("/docs/", gitignore)
            self.assertIn("/.disgust-docs/", gitignore)
            self.assertTrue(any((home / ".disgust-docs" / "repos").iterdir()))
            status = run(["status", "pizza"], cwd=project, env=env)
            self.assertIn("state=synced", status.stdout)

    def test_setup_moves_managed_ignores_after_negation_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "backend"
            project.mkdir()
            git(["init", "-b", "main"], cwd=project)
            (project / ".gitignore").write_text(
                "/docs/\n!/docs/\n/.disgust-docs/\n!/.disgust-docs/\n",
                encoding="utf-8",
            )

            first = run(["setup"], cwd=project)
            second = run(["setup"], cwd=project)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            lines = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[-2:], ["/.disgust-docs/", "/docs/"])
            self.assertEqual(lines.count("/.disgust-docs/"), 1)
            self.assertEqual(lines.count("/docs/"), 1)
            (project / "docs").mkdir()
            (project / "docs" / "README.md").write_text("ignored\n", encoding="utf-8")
            ignored = git(["check-ignore", "--quiet", "--", "docs/README.md"], cwd=project)
            self.assertEqual(ignored.returncode, 0)

    def test_two_projects_have_independent_snapshots_from_one_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            home = root / "home"
            home.mkdir()
            env = git_env(home)
            projects = [root / "backend", root / "frontend"]
            for project in projects:
                project.mkdir()
                self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)
                result = run(["add", "pizza", str(docs)], cwd=project, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)

            backend_docs = projects[0] / "docs" / "README.md"
            backend_docs.write_text("# Local backend edit\n", encoding="utf-8")
            update_frontend = run(["update", "pizza"], cwd=projects[1], env=env)

            self.assertEqual(update_frontend.returncode, 0, update_frontend.stderr)
            self.assertEqual(backend_docs.read_text(encoding="utf-8"), "# Local backend edit\n")
            self.assertIn("state=modified", run(["status", "pizza"], cwd=projects[0], env=env).stdout)

    def test_update_refuses_local_changes_unless_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            env = git_env(home)
            self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)
            self.assertEqual(run(["add", "pizza", str(docs)], cwd=project, env=env).returncode, 0)
            snapshot = project / "docs" / "README.md"
            snapshot.write_text("# Unpublished local edit\n", encoding="utf-8")
            commit_docs(docs, "# Remote update\n", "Remote update")

            diff = run(["diff", "pizza"], cwd=project, env=env)
            self.assertEqual(diff.returncode, 0, diff.stderr)
            self.assertIn("Unpublished local edit", diff.stdout)

            refused = run(["update", "pizza"], cwd=project, env=env)
            discarded = run(["update", "pizza", "--discard-local"], cwd=project, env=env)

            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("would be overwritten", refused.stderr)
            self.assertEqual(discarded.returncode, 0, discarded.stderr)
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "# Remote update\n")

    def test_publish_requires_pr_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            env = git_env(home)
            self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)
            self.assertEqual(run(["add", "pizza", str(docs)], cwd=project, env=env).returncode, 0)
            (project / "docs" / "README.md").write_text("changed\n", encoding="utf-8")

            result = run(
                ["publish", "pizza", "--message", "Update", "--title", "Update"],
                cwd=project,
                env=env,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("publish requires mode: pr", result.stderr)

    def test_publish_creates_pr_and_keeps_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            fake_bin = make_fake_gh(root)
            env = git_env(home, fake_bin)
            self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)
            self.assertEqual(
                run(["add", "pizza", str(docs), "--mode", "pr"], cwd=project, env=env).returncode,
                0,
            )
            snapshot = project / "docs" / "README.md"
            snapshot.write_text("# Pizza Docs\n\nUpdated.\n", encoding="utf-8")

            published = run(
                [
                    "publish",
                    "pizza",
                    "--branch",
                    "docs/change",
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
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "# Pizza Docs\n\nUpdated.\n")
            self.assertFalse((project / "docs" / ".git").exists())
            self.assertIn("state=published", run(["status", "pizza"], cwd=project, env=env).stdout)
            branch_contents = git(["show", "docs/change:README.md"], cwd=docs).stdout
            self.assertEqual(branch_contents, "# Pizza Docs\n\nUpdated.\n")

            snapshot.write_text("# Pizza Docs\n\nUpdated again.\n", encoding="utf-8")
            republished = run(
                [
                    "publish",
                    "pizza",
                    "--message",
                    "Update docs again",
                    "--title",
                    "Update docs",
                ],
                cwd=project,
                env=env,
            )
            self.assertEqual(republished.returncode, 0, republished.stderr)
            branch_contents = git(["show", "docs/change:README.md"], cwd=docs).stdout
            self.assertEqual(branch_contents, "# Pizza Docs\n\nUpdated again.\n")
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "# Pizza Docs\n\nUpdated again.\n")

            refreshed = run(["update", "pizza"], cwd=project, env=env)
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "# Pizza Docs\n")
            self.assertIn("state=synced", run(["status", "pizza"], cwd=project, env=env).stdout)

    def test_publish_retries_pr_creation_after_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            fake_bin = make_fake_gh(root, fail_first_pr=True)
            env = git_env(home, fake_bin)
            self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)
            self.assertEqual(
                run(["add", "pizza", str(docs), "--mode", "pr"], cwd=project, env=env).returncode,
                0,
            )
            (project / "docs" / "README.md").write_text("# Retry me\n", encoding="utf-8")
            args = [
                "publish",
                "pizza",
                "--branch",
                "docs/retry",
                "--message",
                "Retry docs",
                "--title",
                "Retry docs",
            ]

            first = run(args, cwd=project, env=env)
            second = run(args, cwd=project, env=env)

            self.assertNotEqual(first.returncode, 0)
            self.assertIn("temporary failure", first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("https://github.com/org/pizza-docs/pull/1", second.stdout)
            self.assertIn("state=published", run(["status", "pizza"], cwd=project, env=env).stdout)

    def test_update_rejects_docs_already_tracked_by_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_repo = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            git(["init", "-b", "main"], cwd=project)
            git(["config", "user.email", "tests@example.com"], cwd=project)
            git(["config", "user.name", "Tests"], cwd=project)
            (project / "docs").mkdir()
            (project / "docs" / "local.md").write_text("tracked\n", encoding="utf-8")
            git(["add", "docs/local.md"], cwd=project)
            git(["commit", "-m", "Track local docs"], cwd=project)
            home = root / "home"
            home.mkdir()
            env = git_env(home)
            self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)

            result = run(
                ["add", "pizza", str(docs_repo), "--path", "docs"],
                cwd=project,
                env=env,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already tracked", result.stderr)
            self.assertEqual((project / "docs" / "local.md").read_text(encoding="utf-8"), "tracked\n")

    def test_remove_deletes_a_safe_snapshot_and_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = make_docs_repo(root)
            project = root / "backend"
            project.mkdir()
            home = root / "home"
            home.mkdir()
            env = git_env(home)
            self.assertEqual(run(["setup"], cwd=project, env=env).returncode, 0)
            self.assertEqual(run(["add", "pizza", str(docs)], cwd=project, env=env).returncode, 0)

            removed = run(["remove", "pizza", "--yes"], cwd=project, env=env)

            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse((project / "docs").exists())
            self.assertNotIn("pizza:", (project / ".disgust-docs.yml").read_text(encoding="utf-8"))
            unknown = run(["status", "pizza"], cwd=project, env=env)
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("Unknown docs alias", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
