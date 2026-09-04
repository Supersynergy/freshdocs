from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from . import __version__
from . import bench
from .analyzer import detected_versions
from .core import (
    cached_release_dates,
    context_pack,
    detect_project_libs,
    ensure_registry,
    gap_verdicts,
    model_cutoff,
    project_analysis,
    record_measured_cutoff,
    search,
    sync_library,
)
from .gap import summarise
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
                "model": {
                    "type": "string",
                    "description": "your own model id; loads only what your training cannot cover",
                },
                "cutoff": {
                    "type": "string",
                    "description": "override your training cutoff, YYYY-MM-DD",
                },
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
                "version": {"type": "string", "description": "Exact project version; omit only for latest-version research."},
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
        "name": "freshdocs_analyze",
        "description": "Analyze project languages, manifests, dependencies, and exact lockfile versions.",
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
    {
        "name": "freshdocs_probe",
        "description": (
            "Measure your own knowledge cutoff. Call once with no answer to get the question; "
            "answer it from memory; call again with model and answer to record the result. "
            "Afterwards freshdocs_context loads only what your training cannot cover."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "your model identifier"},
                "answer": {"type": "string", "description": "the JSON object you produced for the probe question"},
            },
        },
    },
    {
        "name": "freshdocs_gap",
        "description": "Per-library verdict: which of a project's dependencies a model's training cannot cover.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "."},
                "model": {"type": "string"},
                "cutoff": {"type": "string"},
            },
            "required": ["model"],
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
            model=args.get("model"),
            cutoff=args.get("cutoff"),
        )
        return tool_text(text)
    if name == "freshdocs_search":
        hits = search(args["query"], args.get("libs"), int(args.get("limit", 8)))
        return tool_text(json.dumps(hits, indent=2))
    if name == "freshdocs_sync":
        return tool_text(
            json.dumps(
                sync_library(args["lib"], bool(args.get("force", False)), args.get("version")),
                indent=2,
            )
        )
    if name == "freshdocs_detect":
        libs = detect_project_libs(pathlib.Path(args.get("project", ".")).expanduser().resolve())
        return tool_text("\n".join(libs) if libs else "No registered libraries detected.")
    if name == "freshdocs_analyze":
        analysis = project_analysis(pathlib.Path(args.get("project", ".")).expanduser().resolve())
        return tool_text(json.dumps(analysis, indent=2))
    if name == "freshdocs_sources":
        top_languages = int(args.get("top_languages", 50))
        fmt = str(args.get("format", "markdown"))
        return tool_text(render_source_plan(build_source_plan(top_languages, bool(args.get("live", False))), fmt))
    if name == "freshdocs_probe":
        model, answer = args.get("model"), args.get("answer")
        if not answer:
            return tool_text(
                bench.build_prompt()
                + "\n\nAnswer from memory, then call freshdocs_probe again with model and answer."
            )
        answers = bench.parse_answer(str(answer))
        if not answers or not model:
            return tool_text("could not parse a package->version JSON object; nothing recorded")
        est = bench.estimate_cutoff(str(model), answers, _panel_dates())
        if est.cutoff:
            record_measured_cutoff(str(model), est.cutoff, est.per_library, "mcp-self-probe")
            tail = f"\n\nrecorded: {model} -> {est.cutoff}. Pass model={model!r} to freshdocs_context from now on."
        else:
            tail = "\n\nnot recorded: too few verified answers."
        return tool_text(bench.render(est) + tail)
    if name == "freshdocs_gap":
        root = pathlib.Path(args.get("project", ".")).expanduser().resolve()
        versions = detected_versions(project_analysis(root))
        verdicts = gap_verdicts(versions, args.get("model"), args.get("cutoff"))
        _, matched, cutoff = model_cutoff(args.get("model"), args.get("cutoff"))
        return tool_text(json.dumps({
            "model": args.get("model"),
            "matched": matched,
            "cutoff": cutoff,
            "verdicts": [v.as_dict() for v in verdicts],
            "summary": summarise(verdicts),
        }, indent=1))
    raise KeyError(f"unknown tool: {name}")


def _panel_dates() -> dict[str, dict[str, str]]:
    reg = ensure_registry()["libs"]
    return {lib: cached_release_dates(lib, reg[lib]) for lib in bench.PROBE_PANEL if lib in reg}


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
                        "serverInfo": {"name": "freshdocs", "version": __version__},
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
