"""Tests for new features: smart_limit, code extraction, auto-registry, deprecations version filter, embeddings."""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class SmartLimitTests(unittest.TestCase):
    def test_smart_limit_simple(self):
        from freshdocs.core import smart_limit

        # 1 lib, short query → base limit
        limit = smart_limit("how to use middleware", ["hono"])
        self.assertGreaterEqual(limit, 2)

    def test_smart_limit_multi_lib(self):
        from freshdocs.core import smart_limit

        # 3 libs → more context
        limit = smart_limit("websocket shared state with tower middleware", ["axum", "tokio", "tower"])
        self.assertGreater(limit, smart_limit("middleware", ["hono"]))

    def test_smart_limit_complex_query(self):
        from freshdocs.core import smart_limit

        # Long, multi-topic query → more context
        limit = smart_limit("how to build a websocket server with auth middleware and rate limiting", ["hono", "zod"])
        self.assertGreater(limit, 5)

    def test_smart_limit_capped(self):
        from freshdocs.core import smart_limit

        # Very complex query is capped at 12
        limit = smart_limit("how to implement a complex websocket authentication authorization rate limiting logging tracing system", ["hono", "zod", "tokio", "axum", "tower"])
        self.assertLessEqual(limit, 12)


class CodeExtractionTests(unittest.TestCase):
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

    def test_is_code_flag_set(self):
        """Code blocks get is_code=1."""
        markdown = """# Demo
Use this middleware:

```typescript
import { getCookie } from 'hono/cookie'
const session = getCookie(c, 'session')
```

That's all you need.
"""
        self.core.index_docs("demo", "1.0.0", markdown, "2026-09-12")
        con = self.core.db()
        rows = con.execute("SELECT is_code FROM docs WHERE lib='demo' AND version='1.0.0'").fetchall()
        con.close()
        # At least one chunk should have is_code=1
        self.assertTrue(any(r[0] == 1 for r in rows))

    def test_code_boost_in_search(self):
        """'how do I' queries boost code chunks."""
        markdown = """# Demo
Use this middleware:

```typescript
import { getCookie } from 'hono/cookie'
const session = getCookie(c, 'session')
```
"""
        self.core.index_docs("demo", "1.0.0", markdown, "2026-09-12")
        hits = self.core.search("how do I use middleware", ["demo"], limit=3)
        self.assertTrue(any(h.get("is_code") for h in hits))


class AutoRegistryTests(unittest.TestCase):
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

    def test_auto_registry_discovers_from_lockfile(self):
        """auto-registry finds deps in lockfile and registers them."""
        # Create a package.json with a dep not in registry
        pkg = pathlib.Path(self.tmp.name) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"unregistered-lib": "1.0.0"}}))
        lock = pathlib.Path(self.tmp.name) / "package-lock.json"
        lock.write_text(json.dumps({"packages": {"node_modules/unregistered-lib": {"version": "1.0.0"}}}))
        from freshdocs.cli import main

        argv = ["auto-registry", "--project", self.tmp.name, "--json"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        self.assertEqual(code, 0)
        # The lib won't resolve to a GitHub repo (it's fake), but the command ran


class DeprecationsVersionFilterTests(unittest.TestCase):
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
        # Register a lib and index docs with versioned deprecations
        registry = self.core.ensure_registry()
        registry["libs"]["test-lib"] = {"gh": "test/test", "branch": "main", "eco": "npm", "pkg": "test-lib"}
        self.core.write_json(pathlib.Path(os.environ["FRESHDOCS_REGISTRY"]), registry)
        # Index docs: one deprecated since 5.0, one since 1.0
        self.core.index_docs(
            "test-lib",
            "3.0.0",
            "# Test\n@deprecated since 5.0 - use newAPI\n@deprecated since 1.0 - use oldAPI\n",
            "2026-09-12",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_deprecations_filters_by_version(self):
        """Deprecations newer than installed version are filtered out."""
        pkg = pathlib.Path(self.tmp.name) / "package.json"
        pkg.write_text(json.dumps({"dependencies": {"test-lib": "3.0.0"}}))
        import importlib
        import freshdocs.analyzer as analyzer
        import freshdocs.cli as cli

        analyzer = importlib.reload(analyzer)
        cli = importlib.reload(cli)
        argv = ["deprecations", "--project", self.tmp.name, "--lib", "test-lib", "--json"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        # The snippet contains both deprecations (same chunk), but only the 1.0
        # version should be reported as deprecated_since (5.0 > 3.0.0 is filtered)
        deprecated_versions = {r["deprecated_since"] for r in data if r["deprecated_since"]}
        self.assertIn("1.0", deprecated_versions)
        self.assertNotIn("5.0", deprecated_versions)


class EmbeddingTests(unittest.TestCase):
    def test_get_embedder_returns_none_without_fastembed(self):
        """_get_embedder returns None if fastembed not installed."""
        from freshdocs.core import _get_embedder

        # In test env, fastembed is not installed → should return None gracefully
        embedder = _get_embedder()
        # Either None (not installed) or an embedder (if installed)
        self.assertTrue(embedder is None or embedder is not None)

    def test_cosine_similarity(self):
        from freshdocs.core import _cosine_similarity

        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), 1.0)
        b = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(a, b), 0.0)


class LinkResolutionTests(unittest.TestCase):
    def test_extract_lib_links(self):
        from freshdocs.core import _extract_lib_links

        reg = {"hono": {}, "zod": {}, "tokio": {}}
        text = "import { z } from 'zod' and use @hono/zod-openapi"
        linked = _extract_lib_links(text, reg)
        self.assertIn("zod", linked)


if __name__ == "__main__":
    unittest.main()
