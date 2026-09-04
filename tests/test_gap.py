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


class GapClassificationTests(unittest.TestCase):
    def setUp(self):
        import freshdocs.gap as gap

        self.gap = gap
        self.dates = {
            "1.0.0": "2024-01-10T00:00:00Z",
            "2.0.0": "2024-06-10T00:00:00Z",
            "3.0.0": "2026-08-01T00:00:00Z",
            "3.1.0-rc.1": "2026-08-20T00:00:00Z",
        }

    def test_release_after_cutoff_is_a_gap(self):
        verdict = self.gap.classify("demo", "3.0.0", self.dates, "2025-01-01")
        self.assertEqual(verdict.status, self.gap.STATUS_AHEAD)
        self.assertTrue(verdict.needs_full_context)

    def test_newest_release_before_cutoff_is_covered(self):
        verdict = self.gap.classify("demo", "2.0.0", self.dates, "2025-01-01")
        self.assertEqual(verdict.status, self.gap.STATUS_COVERED)
        self.assertFalse(verdict.needs_full_context)

    def test_older_pin_than_training_still_loads(self):
        verdict = self.gap.classify("demo", "1.0.0", self.dates, "2025-01-01")
        self.assertEqual(verdict.status, self.gap.STATUS_BEHIND)
        self.assertTrue(verdict.needs_full_context)
        self.assertEqual(verdict.newest_before_cutoff, "2.0.0")

    def test_prerelease_never_counts_as_the_version_a_model_learned(self):
        dates = {"1.0.0": "2024-01-10T00:00:00Z", "1.1.0-beta.1": "2024-03-01T00:00:00Z"}
        verdict = self.gap.classify("demo", "1.0.0", dates, "2025-01-01")
        self.assertEqual(verdict.status, self.gap.STATUS_COVERED)

    def test_version_inside_the_cutoff_margin_is_treated_as_unknown_to_the_model(self):
        dates = {"9.9.9": "2024-12-20T00:00:00Z"}
        verdict = self.gap.classify("demo", "9.9.9", dates, "2025-01-01")
        self.assertEqual(verdict.status, self.gap.STATUS_AHEAD)

    def test_v_prefixed_versions_match(self):
        verdict = self.gap.classify("demo", "v2.0.0", self.dates, "2025-01-01")
        self.assertEqual(verdict.status, self.gap.STATUS_COVERED)

    def test_every_missing_input_fails_safe_to_full_context(self):
        cases = [
            ("demo", "2.0.0", self.dates, None),
            ("demo", "2.0.0", self.dates, "not-a-date"),
            ("demo", "?", self.dates, "2025-01-01"),
            ("demo", "2.0.0", {}, "2025-01-01"),
            ("demo", "99.0.0", self.dates, "2025-01-01"),
        ]
        for lib, version, dates, cutoff in cases:
            with self.subTest(version=version, cutoff=cutoff):
                verdict = self.gap.classify(lib, version, dates, cutoff)
                self.assertEqual(verdict.status, self.gap.STATUS_UNKNOWN)
                self.assertTrue(verdict.needs_full_context)

    def test_cutoff_matching_prefers_the_longest_model_prefix(self):
        table = {"claude-3": "2024-01-01", "claude-sonnet-4": "2025-01-01"}
        key, cutoff = self.gap.resolve_cutoff("anthropic/claude-sonnet-4-5-20260101", table)
        self.assertEqual((key, cutoff), ("claude-sonnet-4", "2025-01-01"))

    def test_unknown_model_resolves_to_no_cutoff(self):
        self.assertEqual(self.gap.resolve_cutoff("some-unlisted-model", {}), (None, None))

    def test_registry_fetch_failure_yields_no_dates_rather_than_raising(self):
        def boom(url, *args, **kwargs):
            raise RuntimeError("offline")

        self.assertEqual(self.gap.release_dates({"eco": "npm", "pkg": "demo"}, boom), {})

    def test_npm_dates_drop_registry_bookkeeping_keys(self):
        payload = json.dumps({"time": {"created": "x", "modified": "y", "1.0.0": "2024-01-01T00:00:00Z"}})
        dates = self.gap.release_dates({"eco": "npm", "pkg": "demo"}, lambda url, **kw: payload)
        self.assertEqual(dates, {"1.0.0": "2024-01-01T00:00:00Z"})

    def test_pypi_dates_use_the_earliest_upload_per_version(self):
        payload = json.dumps({
            "releases": {
                "1.0.0": [
                    {"upload_time_iso_8601": "2024-02-02T00:00:00Z"},
                    {"upload_time_iso_8601": "2024-01-01T00:00:00Z"},
                ],
                "1.1.0": [],
            }
        })
        dates = self.gap.release_dates({"eco": "pypi", "pkg": "demo"}, lambda url, **kw: payload)
        self.assertEqual(dates, {"1.0.0": "2024-01-01T00:00:00Z"})


class GapIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FRESHDOCS_HOME"] = self.tmp.name
        os.environ["FRESHDOCS_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "registry.json")
        os.environ["FRESHDOCS_STATE"] = str(pathlib.Path(self.tmp.name) / "state.json")
        os.environ["FRESHDOCS_DB"] = str(pathlib.Path(self.tmp.name) / "freshdocs.db")
        os.environ["FRESHDOCS_LEGACY_REGISTRY"] = str(pathlib.Path(self.tmp.name) / "legacy.json")
        os.environ.pop("FRESHDOCS_MODEL", None)
        import importlib

        import freshdocs.core as core

        self.core = importlib.reload(core)

    def tearDown(self):
        os.environ.pop("FRESHDOCS_MODEL", None)
        self.tmp.cleanup()

    def test_release_dates_are_cached_so_a_prompt_costs_no_network(self):
        calls = []

        def fake(meta, fetch):
            calls.append(meta)
            return {"4.13.5": "2026-08-26T00:00:00Z"}

        with mock.patch.object(self.core, "release_dates", side_effect=fake):
            first = self.core.cached_release_dates("hono", {"eco": "npm", "pkg": "hono"})
            second = self.core.cached_release_dates("hono", {"eco": "npm", "pkg": "hono"})
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    def test_a_failed_refresh_keeps_the_previous_answer(self):
        with mock.patch.object(self.core, "release_dates", return_value={"1.0.0": "2024-01-01T00:00:00Z"}):
            self.core.cached_release_dates("hono", {"eco": "npm", "pkg": "hono"})
        with mock.patch.object(self.core, "release_dates", return_value={}):
            kept = self.core.cached_release_dates("hono", {"eco": "npm", "pkg": "hono"}, refresh=True)
        self.assertEqual(kept, {"1.0.0": "2024-01-01T00:00:00Z"})

    def test_unregistered_library_fails_safe(self):
        verdicts = self.core.gap_verdicts({"nosuchlib": "1.0.0"}, model="claude-sonnet-4-5")
        self.assertEqual(verdicts[0].status, "unknown")
        self.assertTrue(verdicts[0].needs_full_context)

    def test_registry_override_beats_the_built_in_cutoff(self):
        self.core.set_model_cutoff("housemodel", "2030-01-01")
        _, matched, cutoff = self.core.model_cutoff("housemodel")
        self.assertEqual((matched, cutoff), ("housemodel", "2030-01-01"))

    def test_explicit_cutoff_beats_everything(self):
        self.core.set_model_cutoff("housemodel", "2030-01-01")
        _, matched, cutoff = self.core.model_cutoff("housemodel", "2020-05-05")
        self.assertEqual((matched, cutoff), ("explicit", "2020-05-05"))

    def test_model_comes_from_the_environment_when_not_passed(self):
        os.environ["FRESHDOCS_MODEL"] = "claude-sonnet-4-5"
        model, matched, _ = self.core.model_cutoff(None)
        self.assertEqual(model, "claude-sonnet-4-5")
        self.assertEqual(matched, "claude-sonnet-4")

    def test_covered_libraries_shrink_the_pack_without_emptying_it(self):
        root = pathlib.Path(self.tmp.name) / "proj"
        root.mkdir()
        (root / "package.json").write_text(json.dumps({"dependencies": {"hono": "4.13.5"}}))
        (root / "package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {"node_modules/hono": {"version": "4.13.5"}}})
        )
        for i in range(8):
            self.core.index_docs("hono", "4.13.5", f"## Auth {i}\nbearer auth middleware guards the route.\n", "2026-09-04")

        with mock.patch.object(self.core, "release_dates", return_value={"4.13.5": "2026-01-01T00:00:00Z"}):
            covered = self.core.context_pack("bearer auth", root, limit=6, model="m", cutoff="2026-12-01")
            gapped = self.core.context_pack("bearer auth", root, limit=6, model="m", cutoff="2025-01-01")
        self.assertIn("covered by training", covered)
        self.assertIn("budget: reduced", covered)
        self.assertIn("[1]", covered)
        self.assertLess(len(covered), len(gapped))
        self.assertIn("training gap", gapped)

    def _two_lib_project(self, name: str) -> pathlib.Path:
        root = pathlib.Path(self.tmp.name) / name
        root.mkdir()
        (root / "package.json").write_text(json.dumps({"dependencies": {"hono": "4.13.5", "zod": "4.5.4"}}))
        (root / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/hono": {"version": "4.13.5"},
                    "node_modules/zod": {"version": "4.5.4"},
                },
            })
        )
        return root

    def test_sync_stale_refetches_only_the_libraries_the_model_cannot_cover(self):
        root = self._two_lib_project("mixed")
        synced = []

        def dates(meta, fetch):
            # hono predates the cutoff, zod does not.
            if meta.get("pkg") == "hono":
                return {"4.13.5": "2024-01-01T00:00:00Z"}
            return {"4.5.4": "2026-08-29T00:00:00Z"}

        with mock.patch.object(self.core, "release_dates", side_effect=dates):
            with mock.patch.object(self.core, "sync_library", side_effect=lambda lib, **kw: synced.append(lib)):
                pack = self.core.context_pack(
                    "bearer auth", root, limit=6, sync_stale=True, model="m", cutoff="2025-01-01"
                )
        self.assertEqual(synced, ["zod"])
        self.assertIn("sync: 1 covered library not refetched", pack)

    def test_sync_stale_without_a_model_still_refreshes_everything(self):
        root = self._two_lib_project("plainsync")
        synced = []
        with mock.patch.object(self.core, "sync_library", side_effect=lambda lib, **kw: synced.append(lib)):
            self.core.context_pack("bearer auth", root, limit=6, sync_stale=True)
        self.assertEqual(sorted(synced), ["hono", "zod"])

    def test_an_unclassifiable_library_is_never_skipped_by_sync(self):
        root = self._two_lib_project("unknowns")
        synced = []
        with mock.patch.object(self.core, "release_dates", return_value={}):
            with mock.patch.object(self.core, "sync_library", side_effect=lambda lib, **kw: synced.append(lib)):
                self.core.context_pack(
                    "bearer auth", root, limit=6, sync_stale=True, model="m", cutoff="2025-01-01"
                )
        self.assertEqual(sorted(synced), ["hono", "zod"])

    def test_no_model_leaves_the_pack_untouched(self):
        root = pathlib.Path(self.tmp.name) / "plain"
        root.mkdir()
        pack = self.core.context_pack("anything", root, limit=6)
        self.assertNotIn("model:", pack)

    def test_gap_command_reports_and_json_round_trips(self):
        import freshdocs.cli as cli

        root = pathlib.Path(self.tmp.name) / "proj2"
        root.mkdir()
        (root / "package.json").write_text(json.dumps({"dependencies": {"hono": "4.13.5"}}))
        (root / "package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": {"node_modules/hono": {"version": "4.13.5"}}})
        )
        out = io.StringIO()
        with mock.patch.object(self.core, "release_dates", return_value={"4.13.5": "2026-08-26T00:00:00Z"}):
            with contextlib.redirect_stdout(out):
                code = cli.main(["gap", "--project", str(root), "--model", "claude-sonnet-4-5", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["verdicts"][0]["status"], "ahead")
        self.assertTrue(payload["verdicts"][0]["needs_full_context"])

    def test_gap_command_without_a_model_is_an_error(self):
        import freshdocs.cli as cli

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(["gap", "--project", self.tmp.name])
        self.assertEqual(code, 2)
        self.assertIn("no model given", err.getvalue())

    def test_models_set_rejects_a_malformed_cutoff(self):
        import freshdocs.cli as cli

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(["models", "--set", "m", "januar-2025"])
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", err.getvalue())


if __name__ == "__main__":
    unittest.main()
