import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import freshdocs.bench as bench  # noqa: E402

DATES = {
    "typescript": {
        "5.4.2": "2024-03-06T00:00:00Z",
        "5.4.5": "2024-04-10T00:00:00Z",
        "5.6.2": "2024-09-09T00:00:00Z",
        "7.0.2": "2026-07-08T00:00:00Z",
        "5.7.0-beta": "2024-10-01T00:00:00Z",
    },
    "react": {
        "18.2.0": "2022-06-14T00:00:00Z",
        "19.0.0": "2024-12-05T00:00:00Z",
        "0.0.0-experimental-abc": "2026-09-03T00:00:00Z",
    },
    "zod": {"3.22.4": "2023-10-05T00:00:00Z", "3.23.8": "2024-05-14T00:00:00Z"},
    "hono": {"4.3.0": "2024-05-01T00:00:00Z"},
}


class ParseTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        text = 'Sure!\n```json\n{"react": "18.2.0", "zod": "v3.22.4"}\n```\nDone.'
        self.assertEqual(bench.parse_answer(text), {"react": "18.2.0", "zod": "3.22.4"})

    def test_garbage_yields_empty_map(self):
        self.assertEqual(bench.parse_answer("I cannot help with that."), {})

    def test_keys_are_lowercased(self):
        self.assertEqual(bench.parse_answer('{"React": "18.2.0"}'), {"react": "18.2.0"})


class EvaluateTests(unittest.TestCase):
    def test_existing_version_gets_its_release_date(self):
        p = bench.evaluate_library("react", "18.2.0", DATES["react"])
        self.assertTrue(p.exists)
        self.assertEqual(p.released, "2022-06-14")
        self.assertEqual(p.newest_known, "19.0.0")

    def test_prereleases_and_nightlies_never_count_as_newest(self):
        p = bench.evaluate_library("react", "18.2.0", DATES["react"])
        self.assertEqual(p.newest_known, "19.0.0")
        p = bench.evaluate_library("typescript", "5.4.2", DATES["typescript"])
        self.assertEqual(p.newest_known, "7.0.2")

    def test_nonexistent_version_is_a_hallucination(self):
        p = bench.evaluate_library("zod", "3.99.0", DATES["zod"])
        self.assertTrue(p.hallucinated)
        self.assertFalse(p.exists)

    def test_dot_zero_for_a_project_without_dot_zero_releases_is_credited_to_that_minor(self):
        p = bench.evaluate_library("typescript", "5.6.0", DATES["typescript"])
        self.assertTrue(p.exists)
        self.assertEqual(p.released, "2024-09-09")
        self.assertIn("5.6.2", p.claimed)

    def test_dot_zero_for_an_unknown_minor_stays_a_hallucination(self):
        p = bench.evaluate_library("typescript", "9.9.0", DATES["typescript"])
        self.assertTrue(p.hallucinated)

    def test_no_answer_is_neither_verified_nor_hallucinated(self):
        p = bench.evaluate_library("hono", None, DATES["hono"])
        self.assertIsNone(p.claimed)
        self.assertFalse(p.hallucinated)


class EstimateTests(unittest.TestCase):
    def test_cutoff_is_the_median_not_the_max(self):
        answers = {"react": "18.2.0", "zod": "3.22.4", "typescript": "5.4.5", "hono": "4.3.0"}
        est = bench.estimate_cutoff("m", answers, DATES)
        # dates: 2022-06-14, 2023-10-05, 2024-04-10, 2024-05-01 -> median between the middle two
        self.assertEqual(est.verified, 4)
        self.assertTrue("2023-10-05" < est.cutoff < "2024-05-01")
        self.assertLess(est.cutoff, "2024-05-01")

    def test_too_few_verified_answers_give_no_cutoff(self):
        est = bench.estimate_cutoff("m", {"react": "18.2.0"}, DATES)
        self.assertIsNone(est.cutoff)
        self.assertIn("insufficient", est.method)

    def test_hallucinations_are_counted_but_do_not_move_the_cutoff(self):
        answers = {"react": "18.2.0", "zod": "3.22.4", "typescript": "5.4.5", "hono": "99.0.0"}
        est = bench.estimate_cutoff("m", answers, DATES)
        self.assertEqual(est.hallucinated, 1)
        self.assertEqual(est.verified, 3)

    def test_per_library_dates_are_kept(self):
        answers = {"react": "18.2.0", "zod": "3.22.4", "typescript": "5.4.5"}
        est = bench.estimate_cutoff("m", answers, DATES)
        self.assertEqual(est.per_library["zod"], "2023-10-05")

    def test_run_probe_round_trip(self):
        def ask(model, prompt):
            self.assertIn("react", prompt)
            return '{"react": "18.2.0", "zod": "3.22.4", "typescript": "5.4.5", "hono": "4.3.0"}'

        est = bench.run_probe("m", ask, DATES, panel=("react", "zod", "typescript", "hono"))
        self.assertEqual(est.verified, 4)
        self.assertIn("cutoff:", bench.render(est))


if __name__ == "__main__":
    unittest.main()
