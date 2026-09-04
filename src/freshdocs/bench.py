"""Measure a model's knowledge cutoff instead of guessing it.

Vendors publish a training cutoff, if at all, as a single month. What matters for a
coding agent is narrower and measurable: for each library, which release is the newest
one the model can name correctly?

The probe asks a model, from memory and without tools, for the newest version it knows
of each library in a fixed panel. Every answer is checked against the package registry:

- a version that exists gets the publication date of that release
- a version that does not exist is a hallucination and is recorded as such
- a version that exists but is far behind is a weak spot for that library

The model's effective cutoff is the median publication date across libraries with a
verified answer. The median, not the maximum, because one lucky late answer must not
pull the cutoff forward and suppress documentation the model actually needs. Per-library
dates are kept as well, because coverage is uneven: a model may know polars to last
month and ruff only to last year.

Nothing here decides anything at prompt time. It produces evidence that
``freshdocs models`` records, and gap detection then trusts.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import statistics
from typing import Any, Callable

PROBE_PANEL: tuple[str, ...] = (
    "react",
    "typescript",
    "vite",
    "vitest",
    "hono",
    "zod",
    "tailwindcss",
    "astro",
    "bun",
    "drizzle-orm",
    "biome",
    "fastapi",
    "pydantic",
    "polars",
    "ruff",
    "uv",
    "tokio",
    "axum",
    "ratatui",
    "tauri",
)

# Wording matters more than expected. A prompt that says "unsure is worse than old"
# pushed the same model a full year earlier with no gain in accuracy: zero hallucinations
# either way, but twelve months of real knowledge discarded. Ask for best recollection,
# forbid invention, and let the registry check catch what slips.
PROBE_PROMPT = """From memory only. Do not use tools or search.

For each package below, state the newest RELEASED stable version you know of. Give
your best recollection of the most recent one. You do not have to be certain, but do
not invent a version you have never seen.

Packages: {packages}

Answer with one JSON object and nothing else, mapping package name to version string:
{{"react": "18.2.0", ...}}"""

# Anything after a hyphen is a prerelease tag under semver (rc, beta, canary, insiders,
# experimental, a commit hash), and 0.0.0 is the version number nightlies hide behind.
PRERELEASE = re.compile(r"(-|alpha|beta|rc\d*$|canary|next|dev|nightly|pre|^0\.0\.0)", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class LibraryProbe:
    lib: str
    claimed: str | None
    exists: bool
    released: str | None
    newest_known: str | None
    newest_date: str | None
    lag_days: int | None

    @property
    def hallucinated(self) -> bool:
        return self.claimed is not None and not self.exists


@dataclasses.dataclass(frozen=True)
class CutoffEstimate:
    model: str
    cutoff: str | None
    method: str
    verified: int
    hallucinated: int
    unanswered: int
    per_library: dict[str, str]
    probes: tuple[LibraryProbe, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "cutoff": self.cutoff,
            "method": self.method,
            "verified": self.verified,
            "hallucinated": self.hallucinated,
            "unanswered": self.unanswered,
            "per_library": self.per_library,
            "probes": [dataclasses.asdict(p) for p in self.probes],
        }


def build_prompt(panel: tuple[str, ...] = PROBE_PANEL) -> str:
    return PROBE_PROMPT.format(packages=", ".join(panel))


def parse_answer(text: str) -> dict[str, str]:
    """Extract the package->version map; tolerate fences, prose, and trailing junk."""
    body = text.strip()
    if body.startswith("```"):
        parts = body.split("```")
        if len(parts) > 1:
            body = parts[1].removeprefix("json").strip()
    i, j = body.find("{"), body.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        raw = json.loads(body[i : j + 1])
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for key, value in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(value, (str, int, float)):
            out[str(key).strip().lower()] = str(value).strip().lstrip("v")
    return out


def _stable(dates: dict[str, str]) -> list[tuple[str, str]]:
    pairs = [(v.lstrip("v"), t[:10]) for v, t in dates.items() if not PRERELEASE.search(v)]
    return sorted(pairs, key=lambda p: p[1])


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:4]) or (0,)


def evaluate_library(lib: str, claimed: str | None, dates: dict[str, str]) -> LibraryProbe:
    stable = _stable(dates)
    newest_known, newest_date = (stable[-1] if stable else (None, None))
    if not claimed:
        return LibraryProbe(lib, None, False, None, newest_known, newest_date, None)
    lookup = {v: t for v, t in stable}
    claimed = claimed.lstrip("v")
    released = lookup.get(claimed)
    if released is None and claimed.endswith(".0"):
        # "5.6.0" for a project that only ever ships 5.6.2 is real knowledge minus a
        # patch digit, not a hallucination. Credit the earliest release of that minor.
        minor = claimed[: -len(".0")] + "."
        candidates = sorted((t, v) for v, t in stable if v.startswith(minor))
        if candidates:
            released, matched = candidates[0]
            claimed = f"{claimed}~{matched}"
    if released is None:
        return LibraryProbe(lib, claimed, False, None, newest_known, newest_date, None)
    lag = None
    if newest_date:
        lag = (dt.date.fromisoformat(newest_date) - dt.date.fromisoformat(released)).days
    return LibraryProbe(lib, claimed, True, released, newest_known, newest_date, lag)


def estimate_cutoff(model: str, answers: dict[str, str], dates_by_lib: dict[str, dict[str, str]]) -> CutoffEstimate:
    probes = tuple(evaluate_library(lib, answers.get(lib), dates_by_lib.get(lib, {})) for lib in dates_by_lib)
    verified = [p for p in probes if p.exists and p.released]
    hallucinated = sum(1 for p in probes if p.hallucinated)
    unanswered = sum(1 for p in probes if p.claimed is None)
    per_library = {p.lib: p.released for p in verified if p.released}
    if len(verified) < 3:
        return CutoffEstimate(model, None, "insufficient verified answers", len(verified), hallucinated, unanswered, per_library, probes)
    ordinals = sorted(dt.date.fromisoformat(p.released).toordinal() for p in verified if p.released)
    median = dt.date.fromordinal(int(statistics.median(ordinals)))
    return CutoffEstimate(
        model,
        median.isoformat(),
        f"median release date of {len(verified)} verified answers",
        len(verified),
        hallucinated,
        unanswered,
        per_library,
        probes,
    )


def run_probe(
    model: str,
    ask: Callable[[str, str], str],
    dates_by_lib: dict[str, dict[str, str]],
    panel: tuple[str, ...] = PROBE_PANEL,
) -> CutoffEstimate:
    """Ask one model the panel and score it. ``ask(model, prompt)`` returns raw text."""
    text = ask(model, build_prompt(panel))
    answers = parse_answer(text)
    return estimate_cutoff(model, answers, {lib: dates_by_lib.get(lib, {}) for lib in panel})


def render(est: CutoffEstimate) -> str:
    lines = [f"model: {est.model}"]
    lines.append(f"cutoff: {est.cutoff or 'undetermined'}  ({est.method})")
    lines.append(f"verified {est.verified}  hallucinated {est.hallucinated}  unanswered {est.unanswered}")
    for p in est.probes:
        if p.claimed is None:
            mark, detail = "  --  ", "no answer"
        elif not p.exists:
            mark, detail = " HALL ", f"claimed {p.claimed} (does not exist)"
        else:
            mark = "  ok  "
            detail = f"{p.claimed} released {p.released}"
            if p.lag_days is not None:
                detail += f", {p.lag_days}d behind {p.newest_known}"
        lines.append(f"{mark}{p.lib:14} {detail}")
    return "\n".join(lines)
