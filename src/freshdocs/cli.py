from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import __version__
from .core import (
    add_library,
    context_pack,
    detect_project_libs,
    doctor,
    ensure_registry,
    export_synapse,
    search,
    status_rows,
    sync_library,
)
from .sources import build_source_plan, render_source_plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="freshdocs",
        description="Local, version-pinned documentation context for coding agents.",
    )
    p.add_argument("--version", action="version", version=f"freshdocs {__version__}")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("init", help="create default registry and local database")

    sync = sub.add_parser("sync", help="fetch and index docs")
    sync.add_argument("--lib", action="append", help="library name; repeatable")
    sync.add_argument("--all", action="store_true", help="sync every registered library")
    sync.add_argument("--force", action="store_true", help="re-index even when version is unchanged")

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

    ctx = sub.add_parser("context", help="print a compact context pack for an agent prompt")
    ctx.add_argument("query")
    ctx.add_argument("--project", default=".")
    ctx.add_argument("--lib", action="append", help="library name; repeatable")
    ctx.add_argument("--limit", type=int, default=6)
    ctx.add_argument("--sync-stale", action="store_true")

    srch = sub.add_parser("search", help="search cached docs")
    srch.add_argument("query")
    srch.add_argument("--lib", action="append")
    srch.add_argument("--limit", type=int, default=8)
    srch.add_argument("--json", action="store_true")

    det = sub.add_parser("detect", help="detect registered libraries used by a project")
    det.add_argument("--project", default=".")

    sub.add_parser("doctor", help="check local cache and FTS index")
    sub.add_parser("export-synapse", help="optional: export cached docs into synx")
    sub.add_parser("mcp", help="run MCP stdio server")

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


def cmd_sync(args: argparse.Namespace) -> int:
    reg = ensure_registry()["libs"]
    libs = args.lib or ([] if not args.all else sorted(reg))
    if not libs:
        print("nothing to sync: pass --lib NAME or --all", file=sys.stderr)
        return 2
    failed = 0
    for lib in libs:
        try:
            result = sync_library(lib, force=args.force)
            print(f"{result['lib']:18} {result['version']:14} {result['status']} inserted={result['inserted']} checked={result['checked']}")
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
    add_library(args.name, args.gh, args.eco, args.branch, args.pkg, args.path, args.llms)
    print(f"added {args.name} -> {args.gh}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root = pathlib.Path(args.project).expanduser().resolve()
    print(context_pack(args.query, root, args.lib, args.limit, args.sync_stale), end="")
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


def main(argv: list[str] | None = None) -> int:
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
    if args.cmd == "doctor":
        code, messages = doctor()
        print("\n".join(messages))
        return code
    if args.cmd == "export-synapse":
        count = export_synapse()
        print(f"exported {count} docs to synx")
        return 0
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
