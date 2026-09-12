from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from . import __version__
from . import bench
from .analyzer import detected_versions
from .core import (
    active_model_info,
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
from .identity import ModelIdentity
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
        "description": "Return version-pinned docs, automatically spending full context only on gaps in the active model. Model identity is read from MCP metadata or the host environment; model is only an override.",
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
                    "description": "optional override; omit when the host exposes the active model",
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
        "name": "freshdocs_identity",
        "description": "Show the automatically detected model/profile and whether retrieval is safely using full or gap-only context.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "freshdocs_probe",
        "description": (
            "Measure the automatically detected active model once. Call with no answer, answer "
            "from memory, then call again with answer. Include model only if identity reports that "
            "the host did not expose it. Afterwards context uses the profile automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "optional identity override when the host omits it"},
                "answer": {"type": "string", "description": "the JSON object you produced for the probe question"},
            },
        },
    },
    {
        "name": "freshdocs_gap",
        "description": "Per-library gap verdict for the automatically detected active model; unknown identity fails safe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "."},
                "model": {"type": "string"},
                "cutoff": {"type": "string"},
            },
        },
    },
    {
        "name": "freshdocs_deprecations",
        "description": "Scan cached docs for @deprecated markers, version-filtered against installed versions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "."},
                "libs": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "freshdocs_drift",
        "description": "Compare cached docs against live repos for new major versions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "."},
                "libs": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "freshdocs_auto_registry",
        "description": "Discover unregistered dependencies from project lockfiles and register them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "default": "."},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
]


def call_tool(
    name: str,
    args: dict[str, Any],
    session_model: str | None = None,
    metadata: dict[str, Any] | None = None,
    identity_override: ModelIdentity | None = None,
) -> dict[str, Any]:
    if identity_override is not None:
        identity = identity_override
    elif args.get("model"):
        identity = active_model_info(args.get("model"), metadata)
    elif session_model:
        identity = ModelIdentity(session_model, "mcp-session")
    else:
        identity = active_model_info(metadata=metadata)
    if name == "freshdocs_context":
        text = context_pack(
            args["query"],
            pathlib.Path(args.get("project", ".")).expanduser().resolve(),
            args.get("libs"),
            int(args.get("limit", 6)),
            bool(args.get("sync_stale", False)),
            model=identity.model,
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
    if name == "freshdocs_identity":
        _, matched, cutoff = model_cutoff(identity.model)
        return tool_text(json.dumps({
            "model": identity.model,
            "detection_source": identity.source,
            "detail": identity.detail or None,
            "matched": matched,
            "cutoff": cutoff,
            "mode": "gap-aware" if identity.model and cutoff else "safe-full",
            "next_action": None if identity.model and cutoff else (
                "restart with one consistent model identity" if identity.source.startswith("ambiguous")
                else "run freshdocs_probe once" if identity.model
                else "host should expose exact model in MCP _meta.model"
            ),
        }, indent=1))
    if name == "freshdocs_probe":
        model, answer = identity.model, args.get("answer")
        if not answer:
            return tool_text(
                bench.build_prompt()
                + "\n\nAnswer from memory, then call freshdocs_probe again with answer. "
                + (f"Active model already detected as {model}." if model else "Your host omitted identity; include your exact model id.")
            )
        answers = bench.parse_answer(str(answer))
        if not answers or not model:
            return tool_text("could not parse a package->version JSON object; nothing recorded")
        est = bench.estimate_cutoff(str(model), answers, _panel_dates())
        if est.cutoff:
            record_measured_cutoff(str(model), est.cutoff, est.per_library, "mcp-self-probe")
            tail = f"\n\nrecorded: {model} -> {est.cutoff}. It will be selected automatically whenever the host exposes this id."
        else:
            tail = "\n\nnot recorded: too few verified answers."
        return tool_text(bench.render(est) + tail)
    if name == "freshdocs_gap":
        root = pathlib.Path(args.get("project", ".")).expanduser().resolve()
        versions = detected_versions(project_analysis(root))
        verdicts = gap_verdicts(versions, identity.model, args.get("cutoff"))
        _, matched, cutoff = model_cutoff(identity.model, args.get("cutoff"))
        return tool_text(json.dumps({
            "model": identity.model,
            "detection_source": identity.source,
            "fail_safe": identity.model is None or cutoff is None,
            "matched": matched,
            "cutoff": cutoff,
            "verdicts": [v.as_dict() for v in verdicts],
            "summary": summarise(verdicts),
        }, indent=1))
    if name == "freshdocs_deprecations":
        root = pathlib.Path(args.get("project", ".")).expanduser().resolve()
        import argparse as _ap
        import contextlib as _cl
        import io as _io
        from .cli import cmd_deprecations

        ns = _ap.Namespace(project=str(root), lib=args.get("libs"), json=True)
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            cmd_deprecations(ns)
        return tool_text(buf.getvalue().strip())
    if name == "freshdocs_drift":
        root = pathlib.Path(args.get("project", ".")).expanduser().resolve()
        import argparse as _ap
        import contextlib as _cl
        import io as _io
        from .cli import cmd_drift

        ns = _ap.Namespace(project=str(root), lib=args.get("libs"), json=True)
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            cmd_drift(ns)
        return tool_text(buf.getvalue().strip())
    if name == "freshdocs_auto_registry":
        root = pathlib.Path(args.get("project", ".")).expanduser().resolve()
        import argparse as _ap
        import contextlib as _cl
        import io as _io
        from .cli import cmd_auto_registry

        ns = _ap.Namespace(project=str(root), json=True, limit=int(args.get("limit", 20)))
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            cmd_auto_registry(ns)
        return tool_text(buf.getvalue().strip())
    raise KeyError(f"unknown tool: {name}")


def _panel_dates() -> dict[str, dict[str, str]]:
    reg = ensure_registry()["libs"]
    return {lib: cached_release_dates(lib, reg[lib]) for lib in bench.PROBE_PANEL if lib in reg}


def run_stdio() -> int:
    session_model: str | None = None
    session_conflicted = False

    def bind(candidate: ModelIdentity) -> None:
        nonlocal session_model, session_conflicted
        if session_conflicted:
            return
        if candidate.source.startswith("ambiguous"):
            session_model = None
            session_conflicted = True
            return
        if not candidate.model:
            return
        if session_model is None:
            session_model = candidate.model
            return
        old = session_model.lower().rsplit("/", 1)[-1]
        new = candidate.model.lower().rsplit("/", 1)[-1]
        if old != new:
            session_model = None
            session_conflicted = True

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")
            params = req.get("params") if isinstance(req.get("params"), dict) else {}
            # Bind identity once. Contradictory later evidence permanently switches
            # this stdio connection to safe/full mode; no request may silently replace
            # the model profile used by subsequent calls.
            bind(active_model_info(metadata=params))
            if method == "initialize":
                respond(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "freshdocs", "version": __version__},
                        "instructions": (
                            "Freshdocs selects measured knowledge gaps automatically. "
                            "Expose the exact active model as params._meta.model or "
                            "capabilities.experimental.freshdocs.model when available; "
                            "otherwise it fails safe and suppresses no documentation."
                        ),
                    },
                )
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                respond(req_id, {"tools": TOOLS})
            elif method == "tools/call":
                arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                # Legacy clients can bind once through a tool argument. A different
                # later value is a conflict, not an identity switch.
                if arguments.get("model"):
                    bind(active_model_info(arguments.get("model")))
                forced = (
                    ModelIdentity(None, "ambiguous-mcp-session", "conflicting identity evidence; full context forced")
                    if session_conflicted
                    else None
                )
                respond(
                    req_id,
                    call_tool(params.get("name"), arguments, session_model, params, forced),
                )
            else:
                respond(req_id, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as e:
            respond(None, error={"code": -32000, "message": str(e)})
    return 0
