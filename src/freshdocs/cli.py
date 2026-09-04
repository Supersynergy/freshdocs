from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

from . import __version__
from .core import (
    add_library,
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
    project_analysis,
    prune_outdated_index,
    set_model_cutoff,
    search,
    status_rows,
    sync_library,
)
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
    ctx.add_argument("--model", help="target model id; loads only what its training cannot cover")
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
    gap.add_argument("--model", help="target model id; defaults to $FRESHDOCS_MODEL")
    gap.add_argument("--cutoff", help="override the model's training cutoff, YYYY-MM-DD")
    gap.add_argument("--json", action="store_true")

    models = sub.add_parser("models", help="list or override model training cutoffs")
    models.add_argument("--set", nargs=2, metavar=("MODEL", "CUTOFF"), help="record a cutoff for a model id")

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
    return p


def cmd_init() -> int:
    ensure_registry()
    code, messages = doctor()
    print("\n".join(messages))
    return code


def cmd_gap(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.project).expanduser().resolve()
    versions = detected_versions(project_analysis(root))
    model, matched, cutoff = model_cutoff(args.model, args.cutoff)
    if not model:
        print("no model given: pass --model or set FRESHDOCS_MODEL", file=sys.stderr)
        return 2
    verdicts = gap_verdicts(versions, model, args.cutoff)
    if args.json:
        print(json.dumps({
            "model": model,
            "matched": matched,
            "cutoff": cutoff,
            "verdicts": [verdict.as_dict() for verdict in verdicts],
        }, indent=1))
        return 0
    origin = f"matched {matched}" if matched else "no cutoff known"
    print(f"model: {model} ({origin}, cutoff {cutoff or 'unknown'})")
    if not verdicts:
        print("no project libraries with exact versions were detected")
        return 0
    for verdict in verdicts:
        flag = "LOAD" if verdict.needs_full_context else "skip"
        print(f"  {flag}  {verdict.lib:18} {verdict.version:14} {verdict.label()}")
    print(summarise(verdicts))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    if args.set:
        model, cutoff = args.set
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cutoff):
            print("cutoff must be YYYY-MM-DD", file=sys.stderr)
            return 2
        set_model_cutoff(model, cutoff)
        print(f"{model}: cutoff {cutoff}")
        return 0
    overrides = ensure_registry().get("models")
    overrides = overrides if isinstance(overrides, dict) else {}
    for model, cutoff in sorted({**DEFAULT_MODEL_CUTOFFS, **overrides}.items()):
        origin = "override" if model in overrides else "default (approximate)"
        print(f"  {model:22} {cutoff}  {origin}")
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
        targets = [(lib, args.version or versions.get(lib)) for lib in libs]

    failed = 0
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
    context = routed_context(prompt, root, args.limit)
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
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
