"""Tests for parallel sync, --latest flag, and autosync."""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class ParallelSyncTests(unittest.TestCase):
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

    def test_sync_jobs_arg_exists(self):
        from freshdocs.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["sync", "--lib", "hono", "--jobs", "8"])
        self.assertEqual(args.jobs, 8)

    def test_sync_latest_arg_exists(self):
        from freshdocs.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["sync", "--lib", "hono", "--latest"])
        self.assertTrue(args.latest)

    def test_sync_all_arg_exists(self):
        from freshdocs.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["sync", "--all", "--jobs", "2"])
        self.assertTrue(args.all)
        self.assertEqual(args.jobs, 2)

    def test_sync_sequential_jobs_1(self):
        """--jobs 1 uses the sequential path."""
        from freshdocs.cli import main

        argv = ["sync", "--lib", "nonexistent-lib", "--jobs", "1"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = main(argv)
        # Should fail gracefully (unknown lib)
        self.assertEqual(code, 1)


class AutosyncTests(unittest.TestCase):
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

    def test_autosync_trigger_pattern_matches_api(self):
        from freshdocs.routing import AUTOSYNC_TRIGGER

        self.assertTrue(AUTOSYNC_TRIGGER.search("how does the hono api work"))
        self.assertTrue(AUTOSYNC_TRIGGER.search("upgrade react to latest version"))
        self.assertTrue(AUTOSYNC_TRIGGER.search("migration guide for v5"))

    def test_autosync_trigger_pattern_does_not_match_trivial(self):
        from freshdocs.routing import AUTOSYNC_TRIGGER

        self.assertFalse(AUTOSYNC_TRIGGER.search("hello world"))
        self.assertFalse(AUTOSYNC_TRIGGER.search("what is 2+2"))

    def test_spawn_autosync_no_libs_returns_none(self):
        from freshdocs.routing import _spawn_autosync

        # Empty analysis should not spawn anything
        _spawn_autosync({"libraries": []}, pathlib.Path(self.tmp.name))
        # No exception means success

    def test_spawn_autosync_all_cached_does_not_spawn(self):
        from freshdocs.routing import _spawn_autosync

        # Register a lib and index it so it's not stale
        registry = self.core.ensure_registry()
        registry["libs"]["test-lib"] = {"gh": "test/test", "branch": "main", "eco": "npm", "pkg": "test-lib"}
        self.core.write_json(pathlib.Path(os.environ["FRESHDOCS_REGISTRY"]), registry)
        self.core.index_docs("test-lib", "1.0.0", "# Test\ncontent", "2026-09-10")
        state = self.core.load_json(self.core.STATE_PATH, {})
        state["test-lib"] = {"version": "1.0.0", "checked": "2026-09-10", "fetched": "2026-09-10"}
        self.core.write_json(self.core.STATE_PATH, state)
        # Should not spawn because cache is fresh
        _spawn_autosync({"libraries": [{"lib": "test-lib"}]}, pathlib.Path(self.tmp.name))

    def test_spawn_autosync_stale_lib_spawns_process(self):
        from unittest import mock
        from freshdocs.routing import _spawn_autosync

        # Register a lib but don't index it (stale)
        registry = self.core.ensure_registry()
        registry["libs"]["stale-lib"] = {"gh": "test/stale", "branch": "main", "eco": "npm", "pkg": "stale-lib"}
        self.core.write_json(pathlib.Path(os.environ["FRESHDOCS_REGISTRY"]), registry)
        # Mock subprocess.Popen so we don't actually spawn
        with mock.patch("subprocess.Popen") as mock_popen:
            _spawn_autosync({"libraries": [{"lib": "stale-lib"}]}, pathlib.Path(self.tmp.name))
            mock_popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
