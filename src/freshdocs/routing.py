from __future__ import annotations

import pathlib
import re
import time

from . import core

FRESH_RISK = re.compile(
    r"\b(?:aktuell|aktuelle|current|fresh|latest|neueste|version|api|sdk|framework|bibliothek|library|package|paket|"
    r"dependency|dependencies|abhängigkeit|upgrade|update|migration|migrate|deprecated|deprecation|breaking|"
    r"release|changelog|docs|documentation|dokumentation)\b",
    re.IGNORECASE,
)
CODE_ACTION = re.compile(
    r"\b(?:bau|baue|build|implement|schreib|write|fix|reparier|debug|install|integrier|refactor|compile|test|"
    r"programmier|code|fehler|error)\w*\b",
    re.IGNORECASE,
)


def needs_fresh_context(prompt: str, analysis: dict) -> bool:
    if not prompt.strip() or len(prompt) > 12_000 or not analysis.get("libraries"):
        return False
    if FRESH_RISK.search(prompt):
        return True
    if not CODE_ACTION.search(prompt):
        return False
    lowered = prompt.lower()
    return any(
        str(item.get("lib", "")).lower() in lowered or str(item.get("package", "")).lower() in lowered
        for item in analysis["libraries"]
    ) or bool(re.search(r"\b(?:import|dependency|compile|build|test|fehler|error)\b", lowered))


def _manifest_fingerprint(root: pathlib.Path, analysis: dict) -> list[list[int | str]]:
    fingerprint: list[list[int | str]] = []
    for relative in analysis.get("manifests", []):
        try:
            stat = (root / relative).stat()
        except OSError:
            return []
        fingerprint.append([relative, stat.st_mtime_ns, stat.st_size])
    return fingerprint


def cached_project_analysis(root: pathlib.Path, max_age_seconds: int = 300) -> dict:
    cache_path = core.APP_DIR / "analysis-cache.json"
    cache = core.load_json(cache_path, {})
    key = str(root)
    cached = cache.get(key, {})
    if cached and time.time() - float(cached.get("cached_at", 0)) <= max_age_seconds:
        analysis = cached.get("analysis", {})
        if cached.get("fingerprint") == _manifest_fingerprint(root, analysis):
            return analysis
    analysis = core.project_analysis(root)
    cache[key] = {
        "cached_at": time.time(),
        "fingerprint": _manifest_fingerprint(root, analysis),
        "analysis": analysis,
    }
    core.write_json(cache_path, cache)
    return analysis


def routed_context(prompt: str, root: pathlib.Path, limit: int = 3) -> str:
    if not FRESH_RISK.search(prompt) and not CODE_ACTION.search(prompt):
        return ""
    analysis = cached_project_analysis(root)
    if not needs_fresh_context(prompt, analysis):
        return ""
    context = core.context_pack(prompt, root, limit=limit, sync_stale=False, analysis=analysis)
    return f"<freshdocs>\n{context.strip()}\n</freshdocs>"[:6_000]
