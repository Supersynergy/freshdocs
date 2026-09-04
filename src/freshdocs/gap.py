"""Model-aware gap detection: fetch what a model cannot already know.

Loading a library's whole documentation into every prompt is wasteful when the model
was trained on that exact release. It is also the wrong safety trade: the expensive
failure is not redundancy, it is the model confidently using an API that changed after
its training data ended.

This module compares one number against one date: when the project's installed version
was published, versus when the model stopped learning. Four outcomes, and only one of
them is cheap:

``ahead``
    The installed release is newer than the model's cutoff. The model cannot know it.
    This is the real gap, and it gets the full context pack.
``behind``
    The installed release predates the cutoff, but a newer release does too, so the
    model most likely learned the newer API while the project is pinned to the older
    one. Also full context: this is where a model invents a function that exists
    upstream but not here.
``covered``
    The installed release predates the cutoff and nothing newer did. The model's
    knowledge and the project agree, so a compact confirmation is enough.
``unknown``
    Any input is missing. Never guess: fall back to the full pack and say why.

Every failure path resolves to ``unknown``, so a network outage, an unrecognised model,
or an unpublished version degrades to today's behaviour instead of silently starving
the prompt.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import urllib.parse
from typing import Any

# Approximate training cutoffs, matched by longest prefix. They are deliberately
# conservative: a cutoff that is too early only costs tokens, while one that is too
# late would suppress documentation the model actually needs. Override per model with
# `freshdocs models set <id> <YYYY-MM-DD>`, or per call with `--cutoff`.
DEFAULT_MODEL_CUTOFFS: dict[str, str] = {
    "gpt-4o": "2023-10-01",
    "gpt-4.1": "2024-06-01",
    "gpt-5": "2024-09-01",
    "o3": "2024-06-01",
    "o4": "2024-06-01",
    "claude-3-5": "2024-04-01",
    "claude-3-7": "2024-10-01",
    "claude-sonnet-4": "2025-01-01",
    "claude-opus-4": "2025-01-01",
    "gemini-1.5": "2023-11-01",
    "gemini-2": "2024-06-01",
    "gemini-3": "2025-01-01",
    "llama-3": "2023-12-01",
    "llama-4": "2024-08-01",
    "qwen-3": "2024-09-01",
    "deepseek-v3": "2024-07-01",
    "mistral-large": "2024-06-01",
}

# A published cutoff is a boundary, not a guarantee: material released just before it
# is thinly represented in training data. Treat this window as not-yet-known.
CUTOFF_MARGIN_DAYS = 45

STATUS_AHEAD = "ahead"
STATUS_BEHIND = "behind"
STATUS_COVERED = "covered"
STATUS_UNKNOWN = "unknown"

# Only `covered` is cheap. Everything else, including every error path, stays full.
FULL_CONTEXT_STATUSES = frozenset({STATUS_AHEAD, STATUS_BEHIND, STATUS_UNKNOWN})


@dataclasses.dataclass(frozen=True)
class GapVerdict:
    """Why one library either needs documentation in the prompt or does not."""

    lib: str
    version: str
    status: str
    reason: str
    released: str | None = None
    cutoff: str | None = None
    newest_before_cutoff: str | None = None

    @property
    def needs_full_context(self) -> bool:
        return self.status in FULL_CONTEXT_STATUSES

    def label(self) -> str:
        if self.status == STATUS_COVERED:
            return f"covered by training (released {self.released}, cutoff {self.cutoff})"
        if self.status == STATUS_AHEAD:
            return f"training gap (released {self.released}, after cutoff {self.cutoff})"
        if self.status == STATUS_BEHIND:
            return f"pinned behind training (project {self.version}, model likely knows {self.newest_before_cutoff})"
        return f"unverified ({self.reason})"

    def as_dict(self) -> dict[str, Any]:
        return {**dataclasses.asdict(self), "needs_full_context": self.needs_full_context}


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None


def resolve_cutoff(model: str | None, overrides: dict[str, str] | None = None) -> tuple[str | None, str | None]:
    """Return (matched model key, cutoff date) using longest-prefix matching.

    Model identifiers carry vendor prefixes, dates and quantisation suffixes, so an
    exact lookup would miss almost every real name. The longest matching prefix wins,
    which keeps `claude-sonnet-4-5` from matching a broader `claude-3` entry.
    """
    if not model:
        return None, None
    table = {**DEFAULT_MODEL_CUTOFFS, **(overrides or {})}
    needle = re.sub(r"[^a-z0-9.-]+", "-", model.lower())
    best: tuple[str, str] | None = None
    for key, cutoff in table.items():
        if key in needle and (best is None or len(key) > len(best[0])):
            best = (key, cutoff)
    return best if best else (None, None)


def _npm_dates(pkg: str, fetch: Any) -> dict[str, str]:
    encoded = urllib.parse.quote(pkg, safe="")
    payload = json.loads(fetch(f"https://registry.npmjs.org/{encoded}"))
    times = payload.get("time", {})
    return {k: v for k, v in times.items() if k not in {"created", "modified"}}


def _pypi_dates(pkg: str, fetch: Any) -> dict[str, str]:
    payload = json.loads(fetch(f"https://pypi.org/pypi/{urllib.parse.quote(pkg)}/json"))
    dates: dict[str, str] = {}
    for version, files in (payload.get("releases") or {}).items():
        stamps = [f.get("upload_time_iso_8601") or f.get("upload_time") for f in files or []]
        stamps = [s for s in stamps if s]
        if stamps:
            dates[version] = min(stamps)
    return dates


def _crates_dates(pkg: str, fetch: Any) -> dict[str, str]:
    payload = json.loads(fetch(f"https://crates.io/api/v1/crates/{urllib.parse.quote(pkg)}"))
    return {
        str(item.get("num")): str(item.get("created_at"))
        for item in payload.get("versions") or []
        if item.get("num") and item.get("created_at")
    }


def release_dates(meta: dict[str, Any], fetch: Any) -> dict[str, str]:
    """Publication date per version, or an empty map when the ecosystem cannot say.

    An empty map is a legitimate answer; it resolves to `unknown` upstream, which keeps
    the full context pack rather than guessing that a version is old enough to skip.
    """
    eco = str(meta.get("eco", "gh"))
    pkg = str(meta.get("pkg") or str(meta.get("gh", "")).split("/")[-1])
    if not pkg:
        return {}
    try:
        if eco == "npm":
            return _npm_dates(pkg, fetch)
        if eco == "pypi":
            return _pypi_dates(pkg, fetch)
        if eco in {"cargo", "crates"}:
            return _crates_dates(pkg, fetch)
    except Exception:
        return {}
    return {}


def _normalise(version: str) -> str:
    return str(version).lstrip("v").strip()


def lookup_release(dates: dict[str, str], version: str) -> str | None:
    if not version:
        return None
    if version in dates:
        return dates[version]
    wanted = _normalise(version)
    for key, value in dates.items():
        if _normalise(key) == wanted:
            return value
    return None


def classify(
    lib: str,
    version: str,
    dates: dict[str, str],
    cutoff: str | None,
    today: dt.date | None = None,
    measured: bool = False,
) -> GapVerdict:
    """Decide whether this library's docs must enter the prompt.

    ``measured`` means the cutoff is the release date of a version this exact model
    named correctly in a probe. That is direct evidence of knowledge, so the safety
    margin that guards an approximate vendor date does not apply: the release on the
    cutoff day itself is known, and only strictly newer releases are gaps.
    """
    if not cutoff:
        return GapVerdict(lib, version, STATUS_UNKNOWN, "no training cutoff known for this model")
    cutoff_date = parse_date(cutoff)
    if not cutoff_date:
        return GapVerdict(lib, version, STATUS_UNKNOWN, f"unreadable cutoff {cutoff!r}", cutoff=cutoff)
    if not version or version == "?":
        return GapVerdict(lib, version, STATUS_UNKNOWN, "no exact project version", cutoff=cutoff)

    raw_released = lookup_release(dates, version)
    released = parse_date(raw_released)
    if not released:
        return GapVerdict(lib, version, STATUS_UNKNOWN, "no publication date for this version", cutoff=cutoff)

    horizon = cutoff_date if measured else cutoff_date - dt.timedelta(days=CUTOFF_MARGIN_DAYS)
    released_text = released.isoformat()
    if released > horizon:
        return GapVerdict(lib, version, STATUS_AHEAD, "released at or after the training cutoff", released_text, cutoff)

    # The model may have learned a newer release than the project pins to, which is how
    # an agent invents an API that exists upstream but not in this checkout.
    newest_before, newest_before_date = None, None
    for candidate, stamp in dates.items():
        stamp_date = parse_date(stamp)
        if not stamp_date or stamp_date > horizon:
            continue
        if re.search(r"[a-zA-Z]", _normalise(candidate).replace(".", "")):
            continue  # ignore prereleases: alpha, beta, rc
        if newest_before_date is None or stamp_date > newest_before_date:
            newest_before, newest_before_date = candidate, stamp_date
    if newest_before and newest_before_date and newest_before_date > released:
        return GapVerdict(
            lib,
            version,
            STATUS_BEHIND,
            "a newer release also predates the cutoff, so the model likely knows a different API",
            released_text,
            cutoff,
            str(newest_before),
        )
    return GapVerdict(lib, version, STATUS_COVERED, "released well before the training cutoff", released_text, cutoff)


def summarise(verdicts: list[GapVerdict]) -> str:
    counts: dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict.status] = counts.get(verdict.status, 0) + 1
    order = [STATUS_AHEAD, STATUS_BEHIND, STATUS_UNKNOWN, STATUS_COVERED]
    parts = [f"{counts[status]} {status}" for status in order if status in counts]
    return ", ".join(parts) if parts else "nothing to classify"
