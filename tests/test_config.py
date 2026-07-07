from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from disgust_docs_cli.config import DocConfig, add_doc, empty_config, load_config, save_config
from disgust_docs_cli.errors import DisgustDocsError


class ConfigTests(unittest.TestCase):
    def test_round_trips_v1_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = add_doc(
                empty_config(),
                DocConfig(
                    alias="pizza",
                    repo="git@github.com:org/pizza-docs.git",
                    branch="main",
                    provider="github",
                    mode="pr",
                    path=".disgust-docs/pizza",
                ),
                root,
            )
            save_config(root, config)

            loaded = load_config(root)

            self.assertEqual(loaded.version, 1)
            self.assertEqual(loaded.docs["pizza"].repo, "git@github.com:org/pizza-docs.git")
            self.assertEqual(loaded.docs["pizza"].mode, "pr")

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(DisgustDocsError):
                add_doc(
                    empty_config(),
                    DocConfig(
                        alias="pizza",
                        repo="git@github.com:org/pizza-docs.git",
                        branch="main",
                        provider="github",
                        mode="pr",
                        path="../pizza",
                    ),
                    root,
                )

    def test_rejects_unsafe_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(DisgustDocsError):
                add_doc(
                    empty_config(),
                    DocConfig(
                        alias="../pizza",
                        repo="git@github.com:org/pizza-docs.git",
                        branch="main",
                        provider="github",
                        mode="pr",
                        path=".disgust-docs/pizza",
                    ),
                    root,
                )


if __name__ == "__main__":
    unittest.main()
