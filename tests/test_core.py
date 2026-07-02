import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class FreshdocsCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FRESHDOCS_HOME"] = self.tmp.name
        os.environ["FRESHDOCS_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "registry.json")
        os.environ["FRESHDOCS_STATE"] = str(pathlib.Path(self.tmp.name) / "state.json")
        os.environ["FRESHDOCS_DB"] = str(pathlib.Path(self.tmp.name) / "freshdocs.db")
        import importlib
        import freshdocs.core as core

        self.core = importlib.reload(core)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chunk_markdown_splits_headers(self):
        chunks = self.core.chunk_markdown("# A\none\n## B\ntwo", size=100)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("# A"))

    def test_index_and_search(self):
        inserted = self.core.index_docs("demo", "1.0.0", "# Demo\nUse middleware with cookies.", "2026-07-02")
        self.assertEqual(inserted, 1)
        hits = self.core.search("middleware cookies", ["demo"], limit=3)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["lib"], "demo")

    def test_search_normalizes_scoped_package_names(self):
        self.core.index_docs("demo", "1.0.0", "# Demo\nUse @tanstack/react-query mutations.", "2026-07-02")
        hits = self.core.search("@tanstack/react-query", ["demo"], limit=3)
        self.assertEqual(len(hits), 1)

    def test_fetch_refuses_non_https_urls(self):
        with self.assertRaises(ValueError):
            self.core.fetch_url("file:///etc/passwd")

    def test_detect_package_json(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "package.json").write_text(json.dumps({"dependencies": {"hono": "^4.0.0"}}))
        self.core.ensure_registry()
        self.assertIn("hono", self.core.detect_project_libs(root))

    def test_detect_cargo_toml(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "Cargo.toml").write_text("[dependencies]\ntokio = \"1\"\n")
        self.core.ensure_registry()
        self.assertIn("tokio", self.core.detect_project_libs(root))

    def test_detect_pyproject_optional_dependencies(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "pyproject.toml").write_text("[project.optional-dependencies]\napi = ['fastapi>=0.100']\n")
        self.core.ensure_registry()
        self.assertIn("fastapi", self.core.detect_project_libs(root))

    def test_source_plan_has_top_language_and_repo_commands(self):
        from freshdocs.sources import build_source_plan

        plan = build_source_plan(3, live=False)
        self.assertEqual(plan["languages"][0]["language"], "Python")
        self.assertIn("ghmax_top_repos", {source["id"] for source in plan["languages"][0]["repo_sources"]})


if __name__ == "__main__":
    unittest.main()
