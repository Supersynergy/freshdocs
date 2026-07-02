from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from .core import context_pack, detect_project_libs, search, sync_library
from .sources import build_source_plan, render_source_plan


def respond(req_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    print(json.dumps(msg), flush=True)


def tool_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


TOOLS = [
    {
        "name": "freshdocs_context",
        "description": "Return compact, version-pinned docs context for an agent prompt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string", "default": "."},
                "libs": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 6},
                "sync_stale": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    {
        "name": "freshdocs_search",
        "description": "Search cached docs by query and optional library names.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "libs": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "freshdocs_sync",
        "description": "Fetch and index a registered library.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lib": {"type": "string"},
                "force": {"type": "boolean", "default": False},
            },
            "required": ["lib"],
        },
    },
    {
        "name": "freshdocs_detect",
        "description": "Detect registered libraries used by a local project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string", "default": "."}},
        },
    },
    {
        "name": "freshdocs_sources",
        "description": "Return a language ecosystem source plan with repo/tool harvest commands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_languages": {"type": "integer", "default": 50},
                "live": {"type": "boolean", "default": False},
                "format": {"type": "string", "enum": ["markdown", "json", "jsonl"], "default": "markdown"},
            },
        },
    },
]


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "freshdocs_context":
        text = context_pack(
            args["query"],
            pathlib.Path(args.get("project", ".")).expanduser().resolve(),
            args.get("libs"),
            int(args.get("limit", 6)),
            bool(args.get("sync_stale", False)),
        )
        return tool_text(text)
    if name == "freshdocs_search":
        hits = search(args["query"], args.get("libs"), int(args.get("limit", 8)))
        return tool_text(json.dumps(hits, indent=2))
    if name == "freshdocs_sync":
        return tool_text(json.dumps(sync_library(args["lib"], bool(args.get("force", False))), indent=2))
    if name == "freshdocs_detect":
        libs = detect_project_libs(pathlib.Path(args.get("project", ".")).expanduser().resolve())
        return tool_text("\n".join(libs) if libs else "No registered libraries detected.")
    if name == "freshdocs_sources":
        top_languages = int(args.get("top_languages", 50))
        fmt = str(args.get("format", "markdown"))
        return tool_text(render_source_plan(build_source_plan(top_languages, bool(args.get("live", False))), fmt))
    raise KeyError(f"unknown tool: {name}")


def run_stdio() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")
            if method == "initialize":
                respond(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "freshdocs", "version": "0.1.0"},
                    },
                )
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                respond(req_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = req.get("params", {})
                respond(req_id, call_tool(params.get("name"), params.get("arguments", {})))
            else:
                respond(req_id, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as e:
            respond(None, error={"code": -32000, "message": str(e)})
    return 0
