"""Conservative active-model discovery for CLIs, hooks, and MCP clients.

There is no standard MCP field for the active LLM.  Freshdocs therefore accepts the
identity through several *evidence-bearing* channels and never guesses from a client
name ("Claude Desktop" can run a gateway model, for example).  If no exact identity is
exposed, discovery returns ``None`` and gap-aware retrieval keeps full documentation.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import shlex
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from typing import Any


@dataclasses.dataclass(frozen=True)
class ModelIdentity:
    model: str | None
    source: str
    detail: str = ""

    @property
    def detected(self) -> bool:
        return self.model is not None


# FRESHDOCS_MODEL is an intentional override.  The remaining names are narrow model
# selectors used by provider SDKs and agent launchers.  Generic MODEL is deliberately
# excluded: in development shells it commonly points to an embedding or local ML file.
MODEL_ENV_VARS: tuple[str, ...] = (
    "OPENAI_MODEL",
    "ANTHROPIC_MODEL",
    "CLAUDE_MODEL",
    "GEMINI_MODEL",
    "GOOGLE_GENERATIVE_AI_MODEL",
    "OPENROUTER_MODEL",
    "MISTRAL_MODEL",
    "COHERE_MODEL",
    "GROQ_MODEL",
    "DEEPSEEK_MODEL",
    "OLLAMA_MODEL",
    "AIDER_MODEL",
    "CURSOR_MODEL",
    "COPILOT_MODEL",
    "CODY_MODEL",
    "OPENCODE_MODEL",
    "LLM_MODEL",
    "AI_MODEL",
)

MODEL_KEYS: tuple[str, ...] = (
    "model",
    "model_id",
    "modelId",
    "model_name",
    "modelName",
    "llm_model",
    "llmModel",
)

_METADATA_CONTAINERS: tuple[str, ...] = (
    "_meta",
    "metadata",
    "freshdocs",
    "agent",
    "llm",
    "runtime",
    "clientInfo",
)

_KNOWN_AGENT_COMMANDS = frozenset(
    {"codex", "claude", "gemini", "aider", "cursor", "opencode", "continue", "cline", "copilot"}
)
_INVALID_MODELS = frozenset({"", "auto", "automatic", "default", "none", "null", "unknown"})


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.lower() in _INVALID_MODELS or len(value) > 200 or "\n" in value or "\x00" in value:
        return None
    # Model ids are opaque but in practice use this conservative printable alphabet.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+@\[\]-]*", value):
        return None
    return value


def model_from_metadata(metadata: Mapping[str, Any] | None) -> ModelIdentity:
    """Read explicit model fields from hook/MCP metadata, never from client names."""
    if not isinstance(metadata, Mapping):
        return ModelIdentity(None, "metadata", "no model metadata")

    visited: set[int] = set()

    def inspect(node: Mapping[str, Any], path: str, depth: int) -> tuple[str, str] | None:
        if id(node) in visited or depth > 4:
            return None
        visited.add(id(node))
        for key in MODEL_KEYS:
            if model := _clean(node.get(key)):
                return model, f"{path}{key}"
        for key in _METADATA_CONTAINERS:
            child = node.get(key)
            if isinstance(child, Mapping):
                if found := inspect(child, f"{path}{key}.", depth + 1):
                    return found
        # MCP reserves capabilities.experimental for negotiated extensions. Support
        # {capabilities:{experimental:{freshdocs:{model: ...}}}} without interpreting
        # arbitrary capability payloads.
        capabilities = node.get("capabilities")
        if isinstance(capabilities, Mapping):
            experimental = capabilities.get("experimental")
            if isinstance(experimental, Mapping):
                freshdocs = experimental.get("freshdocs")
                if isinstance(freshdocs, Mapping):
                    if found := inspect(freshdocs, f"{path}capabilities.experimental.freshdocs.", depth + 1):
                        return found
        return None

    found = inspect(metadata, "", 0)
    if not found:
        return ModelIdentity(None, "metadata", "no exact model field")
    return ModelIdentity(found[0], f"metadata:{found[1]}")


def model_from_environment(environ: Mapping[str, str] | None = None) -> ModelIdentity:
    env = os.environ if environ is None else environ
    if model := _clean(env.get("FRESHDOCS_MODEL")):
        return ModelIdentity(model, "env:FRESHDOCS_MODEL")

    candidates: list[tuple[str, str]] = []
    for key in MODEL_ENV_VARS:
        if model := _clean(env.get(key)):
            candidates.append((key, model))
    distinct = {model.lower() for _, model in candidates}
    if len(distinct) == 1 and candidates:
        keys = ",".join(key for key, _ in candidates)
        return ModelIdentity(candidates[0][1], f"env:{keys}")
    if len(distinct) > 1:
        keys = ", ".join(key for key, _ in candidates)
        return ModelIdentity(None, "ambiguous-environment", f"conflicting model selectors: {keys}")
    return ModelIdentity(None, "environment", "no model selector exported")


def _command_agents(command: str) -> set[str]:
    try:
        parts = shlex.split(command)
    except ValueError:
        return set()
    # Wrappers often start as node/python followed by a known agent executable.
    names = {pathlib.Path(part).name.lower() for part in parts[:4] if not part.startswith("-")}
    return names & _KNOWN_AGENT_COMMANDS


def _command_model(command: str) -> str | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts or not _command_agents(command):
        return None
    for i, part in enumerate(parts):
        if part.startswith("--model="):
            return _clean(part.partition("=")[2])
        if part in {"--model", "-m"} and i + 1 < len(parts):
            return _clean(parts[i + 1])
    return None


def parent_commands(max_depth: int = 6) -> list[str]:
    """Best-effort process ancestry; empty on unsupported/restricted systems."""
    commands: list[str] = []
    pid = os.getppid()
    for _ in range(max_depth):
        if pid <= 1:
            break
        try:
            proc = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid=", "-o", "command="],
                capture_output=True,
                text=True,
                timeout=0.5,
                check=False,
            )
            line = proc.stdout.strip()
            if not line:
                break
            parent, command = line.split(None, 1)
            commands.append(command)
            pid = int(parent)
        except (OSError, ValueError, subprocess.SubprocessError):
            break
    return commands


def model_from_commands(commands: Sequence[str]) -> ModelIdentity:
    for depth, command in enumerate(commands):
        if model := _command_model(command):
            return ModelIdentity(model, f"process-argv:{depth}")
    return ModelIdentity(None, "process-argv", "no exact --model in known agent ancestry")


def model_from_host_config(commands: Sequence[str], home: pathlib.Path | None = None) -> ModelIdentity:
    """Read only the config belonging to a positively identified parent agent."""
    agents: set[str] = set()
    for command in commands:
        agents.update(_command_agents(command))
    if not agents:
        return ModelIdentity(None, "host-config", "no known parent agent")
    root = pathlib.Path.home() if home is None else home
    candidates: list[tuple[str, pathlib.Path, str]] = []
    if "codex" in agents:
        candidates.append(("codex", root / ".codex" / "config.toml", "toml"))
    if "claude" in agents:
        candidates.append(("claude", root / ".claude" / "settings.json", "json"))
    if "gemini" in agents:
        candidates.append(("gemini", root / ".gemini" / "settings.json", "json"))
    if "opencode" in agents:
        candidates.append(("opencode", root / ".config" / "opencode" / "opencode.json", "json"))

    found: list[tuple[str, str]] = []
    for agent, path, kind in candidates:
        try:
            raw = path.read_bytes()
            data = tomllib.loads(raw.decode()) if kind == "toml" else json.loads(raw)
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, json.JSONDecodeError):
            continue
        value = data.get("model") if isinstance(data, Mapping) else None
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("id")
        if model := _clean(value):
            found.append((agent, model))
    distinct = {model.lower() for _, model in found}
    if len(distinct) == 1 and found:
        return ModelIdentity(found[0][1], f"host-config:{found[0][0]}")
    if len(distinct) > 1:
        return ModelIdentity(None, "ambiguous-host-config", "multiple parent agents select different models")
    return ModelIdentity(None, "host-config", "known parent did not configure an exact model")


def detect_model(
    explicit: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    commands: Sequence[str] | None = None,
    home: pathlib.Path | None = None,
) -> ModelIdentity:
    """Resolve exact identity; contradictory evidence intentionally returns None."""
    if model := _clean(explicit):
        return ModelIdentity(model, "explicit")

    meta = model_from_metadata(metadata)
    env = model_from_environment(environ)
    if env.source == "ambiguous-environment":
        return env
    command_list = parent_commands() if commands is None else commands
    argv = model_from_commands(command_list)
    config = model_from_host_config(command_list, home)
    if config.source == "ambiguous-host-config":
        return config

    evidence = [item for item in (meta, env, argv, config) if item.detected]

    def base(value: str) -> str:
        # A provider-qualified id and its bare API id are the same evidence, e.g.
        # openai/gpt-5.6-sol and gpt-5.6-sol.
        return value.lower().rsplit("/", 1)[-1]

    if len({base(item.model or "") for item in evidence}) > 1:
        summary = ", ".join(f"{item.source}={item.model}" for item in evidence)
        return ModelIdentity(None, "ambiguous-runtime", f"conflicting model evidence: {summary}")
    if evidence:
        # Order retains the strongest source for reporting: protocol metadata, then
        # environment, exact argv, and finally the positively identified host config.
        return evidence[0]
    detail = "; ".join(filter(None, (meta.detail, env.detail, argv.detail, config.detail)))
    return ModelIdentity(None, "unresolved", detail)
