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
                    path="docs",
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
                        path="docs",
                    ),
                    root,
                )

    def test_rejects_overlapping_doc_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = add_doc(
                empty_config(),
                DocConfig(
                    alias="product",
                    repo="git@github.com:org/product-docs.git",
                    path="docs",
                ),
                root,
            )

            with self.assertRaises(DisgustDocsError):
                add_doc(
                    first,
                    DocConfig(
                        alias="api",
                        repo="git@github.com:org/api-docs.git",
                        path="docs/api",
                    ),
                    root,
                )

    def test_rejects_internal_state_directory_as_doc_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(DisgustDocsError):
                add_doc(
                    empty_config(),
                    DocConfig(
                        alias="product",
                        repo="git@github.com:org/product-docs.git",
                        path=".disgust-docs",
                    ),
                    root,
                )

    def test_rejects_path_inside_internal_state_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in [".disgust-docs/product", ".disgust-docs/state.json/product"]:
                with self.subTest(path=path), self.assertRaises(DisgustDocsError):
                    add_doc(
                        empty_config(),
                        DocConfig(
                            alias="product",
                            repo="git@github.com:org/product-docs.git",
                            path=path,
                        ),
                        root,
                    )


if __name__ == "__main__":
    unittest.main()
