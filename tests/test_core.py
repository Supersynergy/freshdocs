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

    def test_version_cached_by_an_older_indexer_counts_as_stale(self):
        meta = {"gh": "example/demo", "eco": "npm"}
        fresh_today = self.core.today()
        state = {
            "demo": {
                "version": "1.0.0",
                "versions": {
                    "1.0.0": {"content_fetched": fresh_today, "index_format": 1},
                    "2.0.0": {"content_fetched": fresh_today, "index_format": self.core.INDEX_FORMAT},
                },
            }
        }
        self.assertTrue(self.core.is_stale(state, "demo", "1.0.0", meta))
        self.assertFalse(self.core.is_stale(state, "demo", "2.0.0", meta))

    def test_doctor_reports_versions_built_by_an_older_indexer(self):
        self.core.write_json(
            self.core.STATE_PATH,
            {"demo": {"version": "1.0.0", "versions": {"1.0.0": {"content_fetched": "2026-07-27", "index_format": 1}}}},
        )
        self.assertEqual(self.core.outdated_index_versions(), [("demo", "1.0.0")])
        _, messages = self.core.doctor()
        self.assertTrue(any("older indexer" in line for line in messages))

    def test_version_candidates_cover_name_prefixed_release_tags(self):
        candidates = self.core.version_ref_candidates("bun", {"pkg": "bun"}, "1.4.0")
        self.assertIn("v1.4.0", candidates)
        self.assertIn("bun-v1.4.0", candidates)

    def test_registry_gains_new_default_fields_without_losing_user_values(self):
        self.core.write_json(
            self.core.REGISTRY_PATH,
            {"libs": {"hono": {"gh": "honojs/hono", "branch": "custom", "eco": "npm"}}},
        )
        entry = self.core.ensure_registry()["libs"]["hono"]
        self.assertEqual(entry["branch"], "custom")
        self.assertEqual(entry.get("docs_gh"), "honojs/website")

    def test_link_density_separates_navigation_from_prose(self):
        nav = "## Docs\n- [Select](https://x.dev/select.md)\n- [Insert](https://x.dev/insert.md)\n"
        prose = "## Auth\nUse the bearerAuth middleware to guard a route before the handler runs.\n"
        self.assertTrue(self.core.is_navigation_chunk(nav))
        self.assertFalse(self.core.is_navigation_chunk(prose))

    def test_navigation_chunks_rank_below_prose(self):
        nav = "## Middleware index\n" + "".join(
            f"- [middleware auth page {i}](https://x.dev/auth{i}.md)\n" for i in range(12)
        )
        prose = (
            "## Middleware auth\n"
            "Register the auth middleware before the route handler. "
            "The middleware reads the auth cookie and rejects the request when it is absent.\n"
        )
        self.core.index_docs("demo", "1.0.0", nav, "2026-09-03")
        self.core.index_docs("demo", "1.0.0", prose, "2026-09-03")
        hits = self.core.search("middleware auth", libs=["demo"], limit=2)
        self.assertTrue(hits)
        self.assertIn("Register the auth middleware", hits[0]["text"])

    def test_search_prefers_chunks_covering_every_term(self):
        partial = "## Features\nUltrafast router. Lightweight. Batteries included middleware.\n"
        full = "## Cookie auth\nThe auth middleware validates the signed cookies on each request.\n"
        self.core.index_docs("demo", "1.0.0", partial, "2026-09-03")
        self.core.index_docs("demo", "1.0.0", full, "2026-09-03")
        hits = self.core.search("middleware auth cookies", libs=["demo"], limit=1)
        self.assertTrue(hits)
        self.assertIn("Cookie auth", hits[0]["title"])

    def test_search_falls_back_to_partial_match_when_no_chunk_has_every_term(self):
        self.core.index_docs("demo", "1.0.0", "## Routing\nThe router matches a path pattern.\n", "2026-09-03")
        hits = self.core.search("router nonexistentterm", libs=["demo"], limit=2)
        self.assertTrue(hits)

    def test_parse_llms_links_resolves_relative_doc_pages(self):
        text = "- [Select](/docs/select.md): rows\n- [Site](https://x.dev/)\n- [Abs](https://x.dev/a/insert.md)\n"
        links = self.core.parse_llms_links(text, "https://x.dev/llms.txt")
        self.assertEqual(
            links,
            [("Select", "https://x.dev/docs/select.md"), ("Abs", "https://x.dev/a/insert.md")],
        )

    def test_parse_llms_links_targets_markdown_for_extensionless_routes(self):
        text = "- [Select](https://x.dev/docs/select)\n- [Logo](https://x.dev/logo.png)\n"
        links = self.core.parse_llms_links(text, "https://x.dev/llms.txt")
        self.assertEqual(links, [("Select", "https://x.dev/docs/select.md")])

    def test_html_pages_are_never_indexed_as_documentation(self):
        index = "# Docs\n- [Page](https://x.dev/p.md)\n"
        html = "<!DOCTYPE html><html><head><title>Docs</title></head><body>" + "x" * 500
        with mock.patch.object(self.core, "fetch_url", return_value=html):
            pages = self.core._fetch_llms_pages(index, "https://x.dev/llms.txt", 50_000)
        self.assertEqual(pages, [])

    def test_llms_index_is_replaced_by_the_pages_it_points_at(self):
        index = "# Docs\n" + "".join(f"- [Page {i}](https://x.dev/p{i}.md)\n" for i in range(6))
        page = "# Page\n" + "The bearerAuth middleware guards the route. " * 12
        with mock.patch.object(self.core, "fetch_url", return_value=page):
            pages = self.core._fetch_llms_pages(index, "https://x.dev/llms.txt", 50_000)
        self.assertTrue(pages)
        self.assertTrue(all("bearerAuth" in page_source.text for page_source in pages))
        self.assertTrue(all(page_source.url.endswith(".md") for page_source in pages))

    def test_rank_doc_paths_prefers_guides_and_drops_boilerplate(self):
        paths = [
            "docs/CONTRIBUTING.md",
            "docs/CODE_OF_CONDUCT.md",
            "docs/guides/middleware.md",
            "docs/i18n/zh/guide.md",
            "node_modules/pkg/docs/a.md",
            "README.md",
        ]
        ranked = self.core.rank_doc_paths(paths, [""])
        self.assertEqual(ranked[0], "docs/guides/middleware.md")
        for excluded in (
            "README.md",
            "docs/CONTRIBUTING.md",
            "docs/CODE_OF_CONDUCT.md",
            "docs/i18n/zh/guide.md",
            "node_modules/pkg/docs/a.md",
        ):
            self.assertNotIn(excluded, ranked)

    def test_separate_docs_repository_is_fetched_and_marked_live(self):
        readme = self.core.DocSource(
            "README.md",
            "https://raw.githubusercontent.com/example/demo/v1.2.3/README.md",
            "v1.2.3",
            "# Demo\n" + "current API " * 30,
        )
        page = self.core.DocSource(
            "docs/guide.md", "https://raw.githubusercontent.com/example/site/main/docs/guide.md", "main", "prose" * 100
        )

        def fake_tree(repo, prefixes, ref, budget):
            return ([page], True) if repo == "example/site" else ([], True)

        with mock.patch.object(self.core, "_fetch_repo_sources", return_value=[readme]):
            with mock.patch.object(self.core, "_fetch_docs_tree", side_effect=fake_tree):
                result = self.core.fetch_library(
                    "demo",
                    {"gh": "example/demo", "docs_gh": "example/site", "docs_branch": "main"},
                    "1.2.3",
                )
        guide = [source for source in result.sources if source.name == "docs/guide.md"]
        self.assertEqual(len(guide), 1)
        self.assertEqual(guide[0].ref, "live")
        self.assertTrue(result.exact_ref)

    def test_docs_tree_network_failure_is_not_reported_as_missing_docs(self):
        with mock.patch.object(self.core, "_github_tree", side_effect=RuntimeError("offline")):
            sources, listed = self.core._fetch_docs_tree("example/demo", [""], "v1.0.0", 10_000)
        self.assertEqual(sources, [])
        self.assertFalse(listed)

    def test_miss_states_cause_and_forbids_retrying_variants(self):
        pack = self.core.context_pack(
            "cookie auth middleware", pathlib.Path(self.tmp.name), libs=["demo"], limit=3
        )
        self.assertIn("RESULT: no matching documentation", pack)
        self.assertIn("Do not retry reworded queries", pack)
        self.assertIn("--sync-stale", pack)


if __name__ == "__main__":
    unittest.main()
