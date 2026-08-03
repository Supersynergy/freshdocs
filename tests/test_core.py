import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class FreshdocsCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FRESHDOCS_HOME"] = self.tmp.name
        os.environ["FRESHDOCS_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "registry.json")
        os.environ["FRESHDOCS_STATE"] = str(pathlib.Path(self.tmp.name) / "state.json")
        os.environ["FRESHDOCS_DB"] = str(pathlib.Path(self.tmp.name) / "freshdocs.db")
        os.environ["FRESHDOCS_LEGACY_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "legacy-registry.json")
        import importlib
        import freshdocs.core as core

        self.core = importlib.reload(core)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chunk_markdown_splits_headers(self):
        chunks = self.core.chunk_markdown("# A\none\n## B\ntwo", size=100)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("# A"))

    def test_registry_migrates_legacy_entries_once(self):
        legacy = pathlib.Path(os.environ["FRESHDOCS_LEGACY_REGISTRY"])
        legacy.write_text(json.dumps({"libs": {"legacy-demo": {"gh": "example/demo", "eco": "gh"}}}))
        registry = self.core.ensure_registry()
        self.assertIn("legacy-demo", registry["libs"])
        self.assertIn("legacy_registry", registry["_migrations"])

    def test_atomic_json_write_leaves_no_temporary_file(self):
        target = pathlib.Path(self.tmp.name) / "state.json"
        self.core.write_json(target, {"ok": True})
        self.assertEqual(self.core.load_json(target, {}), {"ok": True})
        self.assertEqual(list(target.parent.glob(".state.json.*")), [])

    def test_index_and_search(self):
        inserted = self.core.index_docs("demo", "1.0.0", "# Demo\nUse middleware with cookies.", "2026-07-02")
        self.assertEqual(inserted, 1)
        hits = self.core.search("middleware cookies", ["demo"], limit=3)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["lib"], "demo")

    def test_clear_index_removes_fts_rows(self):
        self.core.index_docs("demo", "1.0.0", "# Demo\nUse middleware with cookies.", "2026-07-02")
        self.core.clear_indexed_docs("demo", "1.0.0")
        self.assertEqual(self.core.search("middleware", ["demo"]), [])

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

    def test_analyze_monorepo_uses_exact_package_lock_version(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        app = root / "apps" / "web"
        app.mkdir(parents=True)
        (app / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}}))
        (root / "package-lock.json").write_text(
            json.dumps(
                {
                    "packages": {
                        "node_modules/react": {"version": "19.2.7"},
                        "node_modules/legacy/node_modules/react": {"version": "18.3.1"},
                    }
                }
            )
        )
        analysis = self.core.project_analysis(root)
        react = next(item for item in analysis["libraries"] if item["lib"] == "react")
        self.assertEqual(react["resolved"], "19.2.7")
        self.assertIn("apps/web/package.json", react["manifests"])
        self.assertIn("JavaScript/TypeScript", {item["language"] for item in analysis["languages"]})

    def test_detect_cargo_toml(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "Cargo.toml").write_text("[dependencies]\ntokio = \"1\"\n")
        self.core.ensure_registry()
        self.assertIn("tokio", self.core.detect_project_libs(root))

    def test_analyze_cargo_lock_uses_exact_version(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "Cargo.toml").write_text('[dependencies]\ntokio = "1"\n')
        (root / "Cargo.lock").write_text('[[package]]\nname = "tokio"\nversion = "1.52.3"\n')
        analysis = self.core.project_analysis(root)
        tokio = next(item for item in analysis["libraries"] if item["lib"] == "tokio")
        self.assertEqual(tokio["resolved"], "1.52.3")

    def test_detect_pyproject_optional_dependencies(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "pyproject.toml").write_text("[project.optional-dependencies]\napi = ['fastapi>=0.100']\n")
        self.core.ensure_registry()
        self.assertIn("fastapi", self.core.detect_project_libs(root))

    def test_analyze_uv_lock_uses_normalized_python_package_name(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "pyproject.toml").write_text("[project]\ndependencies = ['pydantic>=2']\n")
        (root / "uv.lock").write_text('[[package]]\nname = "pydantic"\nversion = "2.13.4"\n')
        analysis = self.core.project_analysis(root)
        pydantic = next(item for item in analysis["libraries"] if item["lib"] == "pydantic")
        self.assertEqual(pydantic["resolved"], "2.13.4")

    def test_context_filters_out_wrong_cached_version(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
        (root / "package-lock.json").write_text(
            json.dumps({"packages": {"node_modules/react": {"version": "18.3.1"}}})
        )
        self.core.index_docs("react", "18.3.1", "# Middleware\nUse the React 18 API.", "2026-07-09")
        self.core.index_docs("react", "19.2.7", "# Middleware\nUse the React 19 API.", "2026-07-09")
        context = self.core.context_pack("middleware API", root)
        self.assertIn("react 18.3.1", context)
        self.assertIn("React 18 API", context)
        self.assertNotIn("React 19 API", context)

    def test_adaptive_hook_routes_code_prompt_and_skips_smalltalk(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
        (root / "package-lock.json").write_text(
            json.dumps({"packages": {"node_modules/react": {"version": "18.3.1"}}})
        )
        from freshdocs.routing import routed_context

        routed = routed_context("Implementiere die aktuelle React API", root)
        self.assertIn("react 18.3.1", routed)
        self.assertIn("untrusted reference data", routed)
        self.assertEqual(routed_context("Wie geht es dir?", root), "")

    def test_sync_records_content_fetch_separately_from_version_check(self):
        source = self.core.DocSource(
            "README.md",
            "https://raw.githubusercontent.com/example/demo/v1.2.3/README.md",
            "v1.2.3",
            "# Demo\n" + "current API " * 30,
        )
        fetched = self.core.LibraryFetch("1.2.3", "v1.2.3", True, (source,))
        registry = self.core.ensure_registry()
        registry["libs"]["demo"] = {"gh": "example/demo", "eco": "npm", "pkg": "demo"}
        self.core.write_json(self.core.REGISTRY_PATH, registry)
        with mock.patch.object(self.core, "fetch_library", return_value=fetched) as fetch:
            result = self.core.sync_library("demo", version="1.2.3")
            cached = self.core.sync_library("demo", version="1.2.3")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result["status"], "indexed")
        self.assertEqual(cached["status"], "cache-hit")
        state = self.core.load_json(self.core.STATE_PATH, {})["demo"]["versions"]["1.2.3"]
        self.assertEqual(state["version_checked"], self.core.today())
        self.assertEqual(state["content_fetched"], self.core.today())
        self.assertTrue(state["exact_ref"])

    def test_fetch_library_marks_branch_fallback_as_unpinned(self):
        branch_source = self.core.DocSource(
            "README.md",
            "https://raw.githubusercontent.com/example/demo/main/README.md",
            "main",
            "# Demo\n" + "current API " * 30,
        )

        def fake_fetch(_repo, _prefixes, ref):
            return [branch_source] if ref == "main" else []

        with mock.patch.object(self.core, "_fetch_repo_sources", side_effect=fake_fetch):
            result = self.core.fetch_library("demo", {"gh": "example/demo", "branch": "main"}, "1.2.3")
        self.assertIsNotNone(result)
        self.assertFalse(result.exact_ref)
        self.assertEqual(result.ref, "main")

    def test_optional_llms_failure_is_visible(self):
        exact_source = self.core.DocSource(
            "README.md",
            "https://raw.githubusercontent.com/example/demo/v1.2.3/README.md",
            "v1.2.3",
            "# Demo\n" + "current API " * 30,
        )
        with mock.patch.object(self.core, "_fetch_repo_sources", return_value=[exact_source]):
            with mock.patch.object(self.core, "fetch_url", side_effect=RuntimeError("offline")):
                result = self.core.fetch_library(
                    "demo",
                    {"gh": "example/demo", "llms": "https://example.com/llms.txt"},
                    "1.2.3",
                )
        self.assertEqual(result.warnings, ("optional llms.txt failed: RuntimeError",))

    def test_mcp_analyze_matches_core_contract(self):
        root = pathlib.Path(self.tmp.name) / "repo"
        root.mkdir()
        (root / "Cargo.toml").write_text('[dependencies]\ntokio = "1"\n')
        (root / "Cargo.lock").write_text('[[package]]\nname = "tokio"\nversion = "1.52.3"\n')
        from freshdocs.mcp import call_tool

        response = call_tool("freshdocs_analyze", {"project": str(root)})
        analysis = json.loads(response["content"][0]["text"])
        tokio = next(item for item in analysis["libraries"] if item["lib"] == "tokio")
        self.assertEqual(tokio["resolved"], "1.52.3")

    def test_source_plan_has_top_language_and_repo_commands(self):
        from freshdocs.sources import build_source_plan

        plan = build_source_plan(3, live=False)
        self.assertEqual(plan["languages"][0]["language"], "Python")
        self.assertIn("ghmax_top_repos", {source["id"] for source in plan["languages"][0]["repo_sources"]})

    def test_help_hides_private_export_command(self):
        import freshdocs.cli as cli

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertNotIn("export-synapse", out.getvalue())

    def test_private_export_rejects_unknown_args(self):
        import freshdocs.cli as cli

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(["export-synapse", "--unknown"])
        self.assertEqual(code, 2)
        self.assertIn("unexpected argument: --unknown", err.getvalue())


if __name__ == "__main__":
    unittest.main()
