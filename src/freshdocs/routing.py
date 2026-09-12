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

# Autosync: spawn a background sync for stale libraries so the next prompt finds
# a fresh cache without blocking the current one. The process is detached so it
# survives the hook's short lifetime and never delays the response.
AUTOSYNC_TRIGGER = re.compile(
    r"\b(?:api|sdk|framework|library|package|dependency|version|migration|"
    r"deprecated|deprecation|breaking|changelog|docs|documentation|"
    r"aktuell|neueste|bibliothek|paket|abhängigkeit|upgrade|update)\b",
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


def _spawn_autosync(analysis: dict, root: pathlib.Path) -> None:
    """Spawn a detached background sync for stale libraries.

    The hook must return in under a few seconds, so we never block on network.
    Instead we fork a `freshdocs sync --project` process that refreshes stale
    entries in parallel. The next prompt finds a fresh cache.
    """
    libs = [item.get("lib") for item in analysis.get("libraries", []) if item.get("lib")]
    if not libs:
        return
    # Only spawn if at least one library is stale or missing
    state = core.load_json(core.STATE_PATH, {})
    reg = core.ensure_registry()["libs"]
    needs_sync = False
    for lib in libs:
        meta = reg.get(lib, {})
        version = state.get(lib, {}).get("version", "")
        if not version or core.is_stale(state, lib, version, meta) or not core.has_indexed_docs(lib, version):
            needs_sync = True
            break
    if not needs_sync:
        return
    import os
    import sys

    try:
        # Detach: setsid + nohup so the child survives the hook's exit
        import subprocess

        subprocess.Popen(
            [sys.executable, "-m", "freshdocs", "sync", "--project", str(root), "--jobs", "4"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        pass


def routed_context(
    prompt: str,
    root: pathlib.Path,
    limit: int | None = None,
    model: str | None = None,
    metadata: dict | None = None,
) -> str:
    if not FRESH_RISK.search(prompt) and not CODE_ACTION.search(prompt):
        return ""
    analysis = cached_project_analysis(root)
    if not needs_fresh_context(prompt, analysis):
        return ""
    # Autosync: spawn background refresh for stale libraries (non-blocking)
    if AUTOSYNC_TRIGGER.search(prompt):
        _spawn_autosync(analysis, root)
    # Hook payloads commonly expose model/model_id/modelId. Let core validate and
    # resolve those aliases so the user never has to duplicate the model on a CLI flag.
    context = core.context_pack(
        prompt,
        root,
        limit=limit,
        sync_stale=False,
        analysis=analysis,
        model=model,
        model_metadata=metadata,
    )
    return f"<freshdocs>\n{context.strip()}\n</freshdocs>"[:6_000]
