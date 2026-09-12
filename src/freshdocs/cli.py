from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any

from . import __version__
from .core import (
    active_model_info,
    add_library,
    cached_release_dates,
    context_pack,
    detect_project_libs,
    doctor,
    ensure_registry,
    STATE_PATH,
    export_synapse,
    gap_verdicts,
    load_json,
    model_cutoff,
    outdated_index_versions,
    measured_cutoffs,
    project_analysis,
    prune_outdated_index,
    record_measured_cutoff,
    set_model_cutoff,
    search,
    status_rows,
    sync_library,
)
from . import bench
from .analyzer import detected_versions
from .gap import DEFAULT_MODEL_CUTOFFS, summarise
from .routing import routed_context
from .sources import build_source_plan, render_source_plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="freshdocs",
        description="Local, version-pinned documentation context for coding agents.",
    )
    p.add_argument("--version", action="version", version=f"freshdocs {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    sub.add_parser("init", help="create default registry and local database")

    sync = sub.add_parser("sync", help="fetch and index docs")
    sync.add_argument("--lib", action="append", help="library name; repeatable")
    sync.add_argument("--all", action="store_true", help="sync every registered library")
    sync.add_argument(
        "--outdated",
        action="store_true",
        help="re-index every cached version built by an older indexer, including pinned older versions",
    )
    sync.add_argument("--force", action="store_true", help="re-index even when version is unchanged")
    sync.add_argument("--project", help="detect libraries and exact versions from this project")
    sync.add_argument("--version", help="exact version; requires one --lib")
    sync.add_argument("--latest", action="store_true", help="sync the latest upstream version for each library, not the project-pinned one")
    sync.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="parallel sync workers (default 4); use 1 for sequential",
    )

    st = sub.add_parser("status", help="show registry and freshness state")
    st.add_argument("--json", action="store_true")

    add = sub.add_parser("add", help="register a library")
    add.add_argument("name")
    add.add_argument("--gh", required=True, help="GitHub owner/repo")
    add.add_argument("--eco", default="npm", choices=["npm", "cargo", "crates", "pypi", "gh"])
    add.add_argument("--branch", default="main")
    add.add_argument("--pkg")
    add.add_argument("--path")
    add.add_argument("--llms")
    add.add_argument("--docs-gh", help="separate docs repository, e.g. honojs/website")
    add.add_argument("--docs-branch", default="main", help="branch of the docs repository")

    ctx = sub.add_parser("context", help="print a compact context pack for an agent prompt")
    ctx.add_argument("query")
    ctx.add_argument("--project", default=".")
    ctx.add_argument("--lib", action="append", help="library name; repeatable")
    ctx.add_argument("--limit", type=int, default=6)
    ctx.add_argument("--sync-stale", action="store_true")
    ctx.add_argument("--model", help="override auto-detected model id")
    ctx.add_argument("--cutoff", help="override the model's training cutoff, YYYY-MM-DD")

    srch = sub.add_parser("search", help="search cached docs")
    srch.add_argument("query")
    srch.add_argument("--lib", action="append")
    srch.add_argument("--limit", type=int, default=8)
    srch.add_argument("--json", action="store_true")

    det = sub.add_parser("detect", help="detect registered libraries used by a project")
    det.add_argument("--project", default=".")

    analyze = sub.add_parser("analyze", help="analyze project languages, manifests, packages, and exact versions")
    analyze.add_argument("--project", default=".")
    analyze.add_argument("--json", action="store_true")

    hook = sub.add_parser("hook", help="local-only adaptive context hook for coding agents")
    hook.add_argument("--client", choices=["codex", "claude", "raw"], default="codex")
    hook.add_argument("--limit", type=int, default=3)

    sub.add_parser("doctor", help="check local cache and FTS index")
    sub.add_parser("mcp", help="run MCP stdio server")

    gap = sub.add_parser("gap", help="show which libraries a model's training cannot cover")
    gap.add_argument("--project", default=".")
    gap.add_argument("--model", help="override auto-detected model id")
    gap.add_argument("--cutoff", help="override the model's training cutoff, YYYY-MM-DD")
    gap.add_argument("--json", action="store_true")

    models = sub.add_parser("models", help="list, measure, or override model training cutoffs")
    models.add_argument("--set", nargs=2, metavar=("MODEL", "CUTOFF"), help="record a cutoff for a model id")
    models.add_argument("--probe", action="store_true", help="print the knowledge probe for the calling model to answer")
    models.add_argument(
        "--record",
        nargs="+",
        metavar="VALUE",
        help="score ANSWER_JSON for the auto-detected model; MODEL ANSWER_JSON remains compatible",
    )
    models.add_argument("--import", dest="import_path", metavar="FILE", help="import a cutoff_bench.py database")
    models.add_argument("--json", action="store_true")

    prune = sub.add_parser("prune", help="drop cached versions built by an older indexer")
    prune.add_argument(
        "--include-current",
        action="store_true",
        help="also drop the version each library currently tracks",
    )
    prune.add_argument("--dry-run", action="store_true", help="list what would be dropped")

    sources = sub.add_parser("sources", help="print source, repo, and tool harvest plan for language ecosystems")
    sources.add_argument("--top-languages", type=int, default=50, help="number of language rows to emit; use 300 for broad agent coverage")
    sources.add_argument("--live", action="store_true", help="refresh GitHut and GitHub Linguist language sources before rendering")
    sources.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")

    deprecations = sub.add_parser("deprecations", help="scan cached docs for @deprecated markers and breaking changes")
    deprecations.add_argument("--project", default=".")
    deprecations.add_argument("--lib", action="append", help="limit to specific libraries")
    deprecations.add_argument("--json", action="store_true")

    drift = sub.add_parser("drift", help="compare cached docs against live repo for new major versions")
    drift.add_argument("--project", default=".")
    drift.add_argument("--lib", action="append", help="limit to specific libraries")
    drift.add_argument("--json", action="store_true")

    auto_reg = sub.add_parser("auto-registry", help="discover and register libraries from project lockfiles")
    auto_reg.add_argument("--project", default=".")
    auto_reg.add_argument("--json", action="store_true")
    auto_reg.add_argument("--limit", type=int, default=20, help="max new libraries to add")

    backfill = sub.add_parser("backfill", help="backfill is_code and embeddings for existing docs")
    backfill.add_argument("--lib", action="append", help="limit to specific libraries")
    backfill.add_argument("--embeddings", action="store_true", help="also generate embeddings (slow)")
    backfill.add_argument("--limit", type=int, default=0, help="max docs to process (0=all)")

    return p


def cmd_init() -> int:
    ensure_registry()
    code, messages = doctor()
    print("\n".join(messages))
    return code


def cmd_gap(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.project).expanduser().resolve()
    versions = detected_versions(project_analysis(root))
    identity = active_model_info(args.model)
    model, matched, cutoff = model_cutoff(identity.model, args.cutoff)
    verdicts = gap_verdicts(versions, model, args.cutoff)
    if args.json:
        print(json.dumps({
            "model": model,
            "detection_source": identity.source,
            "matched": matched,
            "cutoff": cutoff,
            "fail_safe": model is None or cutoff is None,
            "verdicts": [verdict.as_dict() for verdict in verdicts],
        }, indent=1))
        return 0
    if model:
        origin = f"matched {matched}" if matched else "no cutoff known"
        print(f"model: {model} (auto source {identity.source}; {origin}, cutoff {cutoff or 'unknown'})")
    else:
        print("model: not exposed by host (fail-safe: every library is loaded)")
    if not verdicts:
        print("no project libraries with exact versions were detected")
        return 0
    for verdict in verdicts:
        flag = "LOAD" if verdict.needs_full_context else "skip"
        print(f"  {flag}  {verdict.lib:18} {verdict.version:14} {verdict.label()}")
    print(summarise(verdicts))
    return 0


def _panel_dates() -> dict[str, dict[str, str]]:
    reg = ensure_registry()["libs"]
    return {lib: cached_release_dates(lib, reg[lib]) for lib in bench.PROBE_PANEL if lib in reg}


def cmd_models(args: argparse.Namespace) -> int:
    if args.set:
        model, cutoff = args.set
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cutoff):
            print("cutoff must be YYYY-MM-DD", file=sys.stderr)
            return 2
        set_model_cutoff(model, cutoff)
        print(f"{model}: cutoff {cutoff}")
        return 0

    if args.probe:
        identity = active_model_info()
        print(bench.build_prompt())
        print()
        if identity.model:
            print(f"# Active model auto-detected as {identity.model} via {identity.source}.")
            print("# Answer from memory, then record it without repeating the model:")
            print("#   freshdocs models --record '<the JSON you produced>'")
        else:
            print("# The host did not expose its model. Answer from memory, then record with:")
            print("#   freshdocs models --record <your-model-id> '<the JSON you produced>'")
        return 0

    if args.record:
        if len(args.record) == 1:
            identity = active_model_info()
            if not identity.model:
                print("active model was not exposed; use --record MODEL ANSWER_JSON once", file=sys.stderr)
                return 2
            model, raw = identity.model, args.record[0]
        elif len(args.record) == 2:
            model, raw = args.record
        else:
            print("--record accepts ANSWER_JSON or MODEL ANSWER_JSON", file=sys.stderr)
            return 2
        if raw.startswith("@"):
            raw = pathlib.Path(raw[1:]).read_text()
        answers = bench.parse_answer(raw)
        if not answers:
            print("could not parse a package->version JSON object from the answer", file=sys.stderr)
            return 2
        est = bench.estimate_cutoff(model, answers, _panel_dates())
        print(bench.render(est))
        if not est.cutoff:
            print("not recorded: too few verified answers to trust a cutoff", file=sys.stderr)
            return 1
        record_measured_cutoff(model, est.cutoff, est.per_library, "self-probe")
        print(f"recorded: {model} -> {est.cutoff} ({est.verified} libraries measured)")
        return 0

    if args.import_path:
        db = json.loads(pathlib.Path(args.import_path).read_text())
        count = 0
        for model, rec in (db.get("probed") or {}).items():
            # "model@variant" entries are experiment notes (a different prompt or
            # context for the same model), kept in the database as evidence but never
            # matched against a live model id.
            if "@" in model:
                continue
            if rec.get("cutoff") and isinstance(rec.get("per_library"), dict):
                record_measured_cutoff(model, rec["cutoff"], rec["per_library"], rec.get("source") or "cutoff_bench")
                count += 1
        print(f"imported {count} measured cutoff(s) from {args.import_path}")
        return 0

    measured = measured_cutoffs()
    overrides = ensure_registry().get("models")
    overrides = overrides if isinstance(overrides, dict) else {}
    if args.json:
        print(json.dumps({"measured": measured, "overrides": overrides, "defaults": DEFAULT_MODEL_CUTOFFS}, indent=1))
        return 0
    if measured:
        print("measured (by probe; per-library dates apply):")
        for model, rec in sorted(measured.items()):
            libs = len(rec.get("per_library") or {})
            print(f"  {model:44} {rec.get('cutoff')}  {libs} libraries, {rec.get('source')} {rec.get('recorded')}")
    print("manual and default:")
    for model, cutoff in sorted({**DEFAULT_MODEL_CUTOFFS, **overrides}.items()):
        origin = "override" if model in overrides else "default (approximate)"
        print(f"  {model:44} {cutoff}  {origin}")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    if args.dry_run:
        stale = outdated_index_versions()
        if not args.include_current:
            state = load_json(STATE_PATH, {})
            stale = [
                (lib, version)
                for lib, version in stale
                if not (isinstance(state.get(lib), dict) and state[lib].get("version") == version)
            ]
        for lib, version in stale:
            print(f"would drop {lib} {version}")
        print(f"{len(stale)} cached version(s) would be dropped")
        return 0
    removed = prune_outdated_index(keep_current=not args.include_current)
    for lib, version in removed:
        print(f"dropped {lib} {version}")
    print(f"{len(removed)} cached version(s) dropped; each is re-fetched with the current indexer when a project needs it")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    reg = ensure_registry()["libs"]
    analysis = None
    versions: dict[str, str] = {}
    if args.project:
        analysis = project_analysis(pathlib.Path(args.project).expanduser().resolve())
        versions = detected_versions(analysis)

    # Each entry is (library, explicit version or None). --outdated is the only mode
    # that names older pinned versions, which --all never revisits.
    targets: list[tuple[str, str | None]] = []
    if args.outdated:
        targets = [(lib, version) for lib, version in outdated_index_versions() if lib in reg]
        if not targets:
            print("nothing outdated: every cached version was built by the current indexer")
            return 0
    else:
        libs = args.lib or ([item["lib"] for item in analysis["libraries"]] if analysis else []) or ([] if not args.all else sorted(reg))
        if not libs:
            print("nothing to sync: pass --lib NAME, --project PATH, --all, or --outdated", file=sys.stderr)
            return 2
        if args.version and len(libs) != 1:
            print("--version requires exactly one --lib", file=sys.stderr)
            return 2
        # --latest: fetch the upstream latest version, not the project-pinned one
        if getattr(args, "latest", False):
            from .core import github_latest, latest_version

            targets = []
            for lib in libs:
                meta = reg.get(lib, {})
                try:
                    upstream = latest_version(meta) or github_latest(meta.get("gh", ""))
                except Exception:
                    upstream = None
                targets.append((lib, upstream or None))
        else:
            targets = [(lib, args.version or versions.get(lib)) for lib in libs]

    failed = 0
    jobs = max(1, getattr(args, "jobs", 4))
    if jobs == 1 or len(targets) <= 1:
        # Sequential path: preserves exact output ordering for single-lib or --jobs 1
        for lib, target in targets:
            try:
                result = sync_library(lib, force=args.force or args.outdated, version=target)
                pin = "exact-ref" if result.get("exact_ref") else "branch-fallback"
                print(
                    f"{result['lib']:18} {result['version']:14} {result['status']} "
                    f"inserted={result['inserted']} fetched={result['checked']} {pin}"
                )
                for warning in result.get("warnings", []):
                    print(f"  warning: {warning}", file=sys.stderr)
                if result["status"] == "failed":
                    failed += 1
            except Exception as e:
                failed += 1
                print(f"{lib}: FAIL {e}", file=sys.stderr)
    else:
        # Parallel path: ThreadPoolExecutor for network-bound sync
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[tuple[int, dict[str, Any]]] = []
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {
                pool.submit(sync_library, lib, force=args.force or args.outdated, version=target): i
                for i, (lib, target) in enumerate(targets)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results.append((idx, future.result()))
                except Exception as e:
                    results.append((idx, {"lib": targets[idx][0], "version": targets[idx][1] or "?", "status": "failed", "inserted": 0, "checked": "-", "warnings": [str(e)]}))
                    failed += 1
        for idx, result in sorted(results, key=lambda r: r[0]):
            pin = "exact-ref" if result.get("exact_ref") else "branch-fallback"
            print(
                f"{result['lib']:18} {result['version']:14} {result['status']} "
                f"inserted={result['inserted']} fetched={result['checked']} {pin}"
            )
            for warning in result.get("warnings", []):
                print(f"  warning: {warning}", file=sys.stderr)
    return 1 if failed else 0


def cmd_status(args: argparse.Namespace) -> int:
    rows = status_rows()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"\nfreshdocs - {len(rows)} libs registered\n")
    for row in rows:
        if row.get("version"):
            age = row.get("age")
            mark = "STALE" if age is not None and age > 14 else "ok"
            print(f"  {row['lib']:18} {row['version']:14} checked={row.get('checked', '-')} age={age if age is not None else '-'}d chunks={row.get('chunks', '-')} {mark}")
        else:
            print(f"  {row['lib']:18} not synced")
    print()
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    add_library(
        args.name,
        args.gh,
        args.eco,
        args.branch,
        args.pkg,
        args.path,
        args.llms,
        args.docs_gh,
        args.docs_branch,
    )
    print(f"added {args.name} -> {args.gh}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.project).expanduser().resolve()
    print(
        context_pack(
            args.query,
            root,
            args.lib,
            args.limit,
            args.sync_stale,
            model=args.model,
            cutoff=args.cutoff,
        ),
        end="",
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    hits = search(args.query, args.lib, args.limit)
    if args.json:
        print(json.dumps(hits, indent=2))
        return 0
    for i, hit in enumerate(hits, 1):
        print(f"[{i}] {hit['lib']} {hit['version']} checked {hit['checked']} - {hit['title']}")
        text = hit["text"].replace("\n", " ")
        print(f"    {text[:260]}{'...' if len(text) > 260 else ''}")
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.project).expanduser().resolve()
    for lib in detect_project_libs(root):
        print(lib)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.project).expanduser().resolve()
    analysis = project_analysis(root)
    if args.json:
        print(json.dumps(analysis, indent=2))
        return 0
    languages = ", ".join(item["language"] for item in analysis["languages"][:8]) or "none"
    print(f"project: {analysis['project']}")
    print(f"languages: {languages}")
    print(f"ecosystems: {', '.join(analysis['ecosystems']) or 'none'}")
    print(f"manifests: {len(analysis['manifests'])}")
    print("registered libraries:")
    for item in analysis["libraries"]:
        version = item.get("resolved") or f"unresolved ({item.get('requested') or 'no constraint'})"
        print(f"  {item['lib']:18} {version:18} {item['ecosystem']} via {', '.join(item['manifests'])}")
    if not analysis["libraries"]:
        print("  none")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    prompt = str(payload.get("prompt") or payload.get("user_prompt") or payload.get("message") or "")
    root = pathlib.Path(payload.get("cwd") or os.getcwd()).expanduser().resolve()
    # Hooks already carry the active model in common model/model_id/modelId fields.
    # Forward the payload as evidence instead of requiring duplicate configuration.
    context = routed_context(prompt, root, None, metadata=payload)
    if not context:
        return 0
    if args.client == "raw":
        print(context)
    elif args.client == "claude":
        print(json.dumps({"additionalContext": context}))
    else:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    }
                }
            )
        )
    return 0


def cmd_deprecations(args: argparse.Namespace) -> int:
    """Scan cached docs for @deprecated markers and breaking change indicators."""
    root = pathlib.Path(args.project).expanduser().resolve()
    analysis = project_analysis(root)
    versions = detected_versions(analysis)
    # Also include requested versions for libraries without lockfiles
    for item in analysis.get("libraries", []):
        lib = item.get("lib", "")
        if lib not in versions and item.get("requested"):
            v = item["requested"]
            # Strip version constraints like >=, ~=, ==
            v = re.sub(r"^[<>=~!]+", "", v).strip()
            if v and re.match(r"\d+(?:\.\d+)*", v):
                versions[lib] = v
    libs = set(args.lib) if args.lib else set(versions.keys())
    if not libs:
        print("no registered libraries detected; sync first")
        return 0
    from .core import db

    con = db()
    results: list[dict[str, Any]] = []
    # FTS5 query for @deprecated, DEPRECATED, breaking, removed, migration
    patterns = [
        "@deprecated",
        "DEPRECATED",
        "breaking change",
        "breaking-change",
        "BREAKING",
        "removed in",
        "will be removed",
        "migration guide",
        "migrating from",
        "no longer supported",
        "use instead",
        "replaced by",
    ]
    for lib in sorted(libs):
        version = versions.get(lib, "")
        if not version:
            continue
        installed_major = int(version.split(".")[0]) if version.split(".")[0].isdigit() else 0
        for pattern in patterns:
            try:
                rows = con.execute(
                    "SELECT title, text, source FROM docs WHERE lib = ? AND version = ? AND text LIKE ? LIMIT 5",
                    (lib, version, f"%{pattern}%"),
                ).fetchall()
            except Exception:
                rows = []
            for title, text, source in rows:
                # Extract all occurrences of the pattern, check version for each
                idx = 0
                while True:
                    idx = text.lower().find(pattern.lower(), idx)
                    if idx == -1:
                        break
                    # Extract version AFTER the pattern match (not just first in snippet)
                    after_pattern = text[idx:idx + len(pattern) + 120]
                    ver_match = re.search(
                        r"(?:since|in|deprecated in|removed in|introduced in)\s+v?(\d+(?:\.\d+)*)",
                        after_pattern,
                        re.IGNORECASE,
                    )
                    start = max(0, idx - 80)
                    end = min(len(text), idx + len(pattern) + 120)
                    snippet = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
                    deprecation_version = None
                    if ver_match:
                        deprecation_version = ver_match.group(1)
                        dep_major = int(deprecation_version.split(".")[0]) if deprecation_version.split(".")[0].isdigit() else 0
                        if dep_major > installed_major:
                            idx += len(pattern)
                            continue  # Deprecation is newer than installed version
                    results.append(
                        {
                            "lib": lib,
                            "version": version,
                            "pattern": pattern,
                            "title": title,
                            "source": source,
                            "snippet": snippet.strip(),
                            "deprecated_since": deprecation_version,
                        }
                    )
                    idx += len(pattern)
    con.close()
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    if not results:
        print("no deprecation or breaking-change markers found in cached docs")
        return 0
    print(f"DEPRECATION SCAN: {len(results)} markers across {len(set(r['lib'] for r in results))} libraries")
    print()
    for r in results:
        ver_note = f" (since {r['deprecated_since']})" if r.get("deprecated_since") else ""
        print(f"[{r['lib']} {r['version']}]{ver_note} {r['pattern']}")
        print(f"  title: {r['title']}")
        print(f"  source: {r['source']}")
        print(f"  {r['snippet']}")
        print()
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    """Compare cached docs against live repo for new major versions."""
    root = pathlib.Path(args.project).expanduser().resolve()
    analysis = project_analysis(root)
    versions = detected_versions(analysis)
    libs = set(args.lib) if args.lib else set(versions.keys())
    if not libs:
        print("no registered libraries detected; sync first")
        return 0
    from .core import ensure_registry, github_latest, latest_version

    registry = ensure_registry()
    results: list[dict[str, Any]] = []
    for lib in sorted(libs):
        meta = registry.get("libs", {}).get(lib)
        if not meta:
            continue
        installed = versions.get(lib, "")
        if not installed:
            continue
        try:
            upstream_latest = latest_version(meta) or github_latest(meta.get("gh", ""))
        except Exception:
            upstream_latest = ""
        if not upstream_latest:
            continue
        # Compare major versions
        installed_major = installed.split(".")[0] if installed else ""
        upstream_major = upstream_latest.split(".")[0] if upstream_latest else ""
        drifted = installed_major != upstream_major
        results.append(
            {
                "lib": lib,
                "installed": installed,
                "upstream_latest": upstream_latest,
                "major_drift": drifted,
                "repo": meta.get("gh", ""),
            }
        )
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    if not results:
        print("no drift data available; ensure libraries are synced")
        return 0
    drifted = [r for r in results if r["major_drift"]]
    print(f"DRIFT SCAN: {len(results)} libraries checked, {len(drifted)} with major-version drift")
    print()
    for r in results:
        marker = "  DRIFT" if r["major_drift"] else "  ok"
        print(f"{marker} [{r['lib']}] installed={r['installed']} upstream={r['upstream_latest']} repo={r['repo']}")
    return 0


def _github_repo_from_url(url: str) -> str | None:
    """Extract owner/repo from a repository URL."""
    if not url:
        return None
    # Handle git+https://github.com/owner/repo.git, https://github.com/owner/repo
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _resolve_registry(lib: str, eco: str, pkg: str) -> str | None:
    """Try to resolve a package to a GitHub repo via its package registry."""
    import urllib.request
    import urllib.parse

    # Strip @types/ prefix — types packages resolve to the type repo, not the lib repo
    if pkg.startswith("@types/"):
        pkg = pkg[7:]
    headers = {"User-Agent": "freshdocs/0.6"}
    urls = {
        "npm": f"https://registry.npmjs.org/{urllib.parse.quote(pkg, safe='')}/latest",
        "pypi": f"https://pypi.org/pypi/{urllib.parse.quote(pkg, safe='')}/json",
        "crates": f"https://crates.io/api/v1/crates/{urllib.parse.quote(pkg, safe='')}",
        "cargo": f"https://crates.io/api/v1/crates/{urllib.parse.quote(pkg, safe='')}",
        "rubygems": f"https://rubygems.org/api/v1/gems/{urllib.parse.quote(pkg, safe='')}.json",
        "packagist": f"https://repo.packagist.org/p2/{urllib.parse.quote(pkg, safe='')}.json",
        "go": f"https://proxy.golang.org/{urllib.parse.quote(pkg, safe='')}/@latest",
        "hex": f"https://hex.pm/api/packages/{urllib.parse.quote(pkg, safe='')}",
        "pub": f"https://pub.dev/api/packages/{urllib.parse.quote(pkg, safe='')}",
    }
    url = urls.get(eco)
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers=headers)
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        # Extract repository URL from various fields
        repo_url = ""
        if eco == "npm":
            repo_url = data.get("repository", {}).get("url", "")
        elif eco == "pypi":
            repo_url = data.get("info", {}).get("project_urls", {}).get("Repository", "") or data.get("info", {}).get("home_page", "")
        elif eco in {"crates", "cargo"}:
            repo_url = data.get("crate", {}).get("repository", "") or data.get("crate", {}).get("homepage", "")
        elif eco == "rubygems":
            repo_url = data.get("source_code_uri", "") or data.get("homepage_uri", "")
        elif eco == "packagist":
            if isinstance(data, list) and data:
                repo_url = data[0].get("repository", "") or data[0].get("source", {}).get("url", "")
            elif isinstance(data, dict):
                repo_url = data.get("repository", "") or data.get("source", {}).get("url", "")
        elif eco == "go":
            repo_url = data.get("module", "") or pkg
        elif eco == "hex":
            repo_url = data.get("meta", {}).get("links", {}).get("GitHub", "") or data.get("meta", {}).get("repository", "")
        elif eco == "pub":
            repo_url = data.get("latest", {}).get("pubspec", {}).get("repository", "") or data.get("latest", {}).get("pubspec", {}).get("homepage", "")
        gh = _github_repo_from_url(repo_url)
        # Sanity check: don't resolve to DefinitelyTyped unless the package IS a type package
        if gh == "DefinitelyTyped/DefinitelyTyped" and not pkg.startswith("@types/"):
            return None
        return gh
    except Exception:
        return None


def cmd_auto_registry(args: argparse.Namespace) -> int:
    """Discover and register libraries from project lockfiles."""
    root = pathlib.Path(args.project).expanduser().resolve()
    analysis = project_analysis(root)
    registry = ensure_registry()
    reg_libs = registry.get("libs", {})
    existing = set(reg_libs.keys())

    # Collect dependencies not yet in registry
    discovered: list[dict[str, Any]] = []
    for item in analysis.get("dependencies", []):
        eco = item.get("ecosystem", "")
        pkg = item.get("package", "")
        if not pkg or pkg in existing:
            continue
        discovered.append(item)

    if not discovered:
        print("no new libraries to register; all dependencies already in registry")
        return 0

    # Resolve each to a GitHub repo
    added = 0
    for item in discovered[: args.limit]:
        eco = item["ecosystem"]
        pkg = item["package"]
        lib_name = pkg.replace("/", "-").replace(":", "-").replace("@", "").replace("~", "-").lower()
        # Prefer short name for npm scoped packages
        if eco == "npm" and "/" in pkg:
            lib_name = pkg.split("/")[-1].lower()
        gh_repo = _resolve_registry(lib_name, eco, pkg)
        if gh_repo:
            add_library(lib_name, gh_repo, eco, pkg=pkg)
            print(f"  registered: {lib_name:25s} {eco:10s} {gh_repo}")
            added += 1
        else:
            print(f"  skipped:   {lib_name:25s} {eco:10s} (no GitHub repo found)")

    if added:
        print(f"\n{added} new libraries registered; run freshdocs sync --project . to fetch docs")
    else:
        print("no libraries could be resolved to a GitHub repository")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Backfill is_code and embeddings for existing docs."""
    from .core import db, _embed_text, _get_embedder

    con = db()
    # 1. Update is_code for all chunks — only mark chunks where code covers >40%
    # Fetch all chunks and check individually for accuracy
    all_rows = con.execute("SELECT id, text FROM docs WHERE is_code = 0").fetchall()
    updated = 0
    for doc_id, text in all_rows:
        stripped = text.strip()
        if stripped.startswith("```"):
            con.execute("UPDATE docs SET is_code = 1 WHERE id = ?", (doc_id,))
            updated += 1
        else:
            fenced = re.findall(r"```[\w]*\n(.*?)```", text, re.DOTALL)
            code_chars = sum(len(block) for block in fenced)
            if code_chars > len(text) * 0.4:
                con.execute("UPDATE docs SET is_code = 1 WHERE id = ?", (doc_id,))
                updated += 1
    con.commit()
    print(f"is_code updated: {updated} chunks marked as code")

    # 2. Generate embeddings if requested
    if args.embeddings:
        embedder = _get_embedder()
        if not embedder:
            print("fastembed not installed; skipping embeddings", file=sys.stderr)
            con.close()
            return 0
        scope = ""
        if args.lib:
            scope = " AND d.lib IN (" + ",".join("?" * len(args.lib)) + ")"
        limit_clause = f" LIMIT {args.limit}" if args.limit else ""
        rows = con.execute(
            f"SELECT d.id, d.lib, d.version, d.text FROM docs d LEFT JOIN doc_embeddings e ON e.doc_id = d.id WHERE e.doc_id IS NULL{scope}{limit_clause}",
            args.lib if args.lib else [],
        ).fetchall()
        print(f"generating embeddings for {len(rows)} chunks...")
        for i, (doc_id, lib, version, text) in enumerate(rows):
            emb = _embed_text(text)
            if emb:
                con.execute(
                    "INSERT OR REPLACE INTO doc_embeddings(doc_id, lib, version, embedding) VALUES (?, ?, ?, ?)",
                    (doc_id, lib, version, json.dumps(emb)),
                )
            if (i + 1) % 500 == 0:
                con.commit()
                print(f"  {i + 1}/{len(rows)}...", end="\r")
        con.commit()
        print(f"  {len(rows)} embeddings generated")
    con.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "export-synapse":
        if len(argv) > 1 and argv[1] in {"-h", "--help"}:
            print("usage: freshdocs export-synapse")
            return 0
        if len(argv) > 1:
            print(f"freshdocs export-synapse: unexpected argument: {argv[1]}", file=sys.stderr)
            return 2
        count = export_synapse()
        print(f"exported {count} docs to synx")
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "sync":
        return cmd_sync(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "context":
        return cmd_context(args)
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "detect":
        return cmd_detect(args)
    if args.cmd == "analyze":
        return cmd_analyze(args)
    if args.cmd == "hook":
        return cmd_hook(args)
    if args.cmd == "doctor":
        code, messages = doctor()
        print("\n".join(messages))
        return code
    if args.cmd == "prune":
        return cmd_prune(args)
    if args.cmd == "gap":
        return cmd_gap(args)
    if args.cmd == "models":
        return cmd_models(args)
    if args.cmd == "mcp":
        from .mcp import run_stdio

        return run_stdio()
    if args.cmd == "sources":
        print(render_source_plan(build_source_plan(args.top_languages, live=args.live), args.format), end="")
        return 0
    if args.cmd == "deprecations":
        return cmd_deprecations(args)
    if args.cmd == "drift":
        return cmd_drift(args)
    if args.cmd == "auto-registry":
        return cmd_auto_registry(args)
    if args.cmd == "backfill":
        return cmd_backfill(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
