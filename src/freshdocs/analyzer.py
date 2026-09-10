from __future__ import annotations

import json
import os
import pathlib
import re
import tomllib
from typing import Any

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

MANIFESTS = {
    "package.json",
    "package-lock.json",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "go.mod",
    "go.sum",
    "pom.xml",
    "packages.lock.json",
    "composer.json",
    "composer.lock",
    "Gemfile",
    "Gemfile.lock",
    "Package.swift",
    "Package.resolved",
    "pubspec.yaml",
    "pubspec.lock",
    "mix.exs",
    "mix.lock",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "build.sbt",
    "project.clj",
    "deps.edn",
    "shadow-cljs.edn",
    "CMakeLists.txt",
    "meson.build",
    "vcpkg.json",
    "conanfile.txt",
    "conanfile.py",
    "Podfile",
    "Podfile.lock",
    "Cartfile",
    "Cartfile.resolved",
    "deno.json",
    "deno.jsonc",
    "deno.lock",
    "bun.lock",
    "bun.lockb",
    "flake.nix",
    "Project.toml",
    "Manifest.toml",
    "shard.yml",
    "shard.lock",
    "nimble.nimble",
    "nimble.lock",
    "dune-project",
    "dune",
    "opam",
    "esy.json",
    "cabal.project",
    "stack.yaml",
    "stack.yaml.lock",
    "renv.lock",
    "DESCRIPTION",
    "rebar.config",
    "rebar.lock",
    "WORKSPACE",
    "WORKSPACE.bazel",
    "BUILD",
    "BUILD.bazel",
    "BUCK",
    "Buck.toml",
    "glide.yaml",
    "Gopkg.toml",
    "Gopkg.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "Pipfile.lock",
    "setup.py",
    "setup.cfg",
}

EXTENSION_LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".fs": "F#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".lua": "Lua",
    ".r": "R",
    ".c": "C",
    ".h": "C/C++",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".zig": "Zig",
    ".nix": "Nix",
    ".scala": "Scala",
    ".sc": "Scala",
    ".sbt": "Scala",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".cljc": "Clojure",
    ".edn": "Clojure/EDN",
    ".nim": "Nim",
    ".cr": "Crystal",
    ".d": "D",
    ".di": "D",
    ".jl": "Julia",
    ".vala": "Vala",
    ".v": "Verilog",
    ".sv": "SystemVerilog",
    ".vhd": "VHDL",
    ".vhdl": "VHDL",
    ".asm": "Assembly",
    ".s": "Assembly",
    ".S": "Assembly",
    ".f90": "Fortran",
    ".f": "Fortran",
    ".f95": "Fortran",
    ".f03": "Fortran",
    ".pas": "Pascal",
    ".pp": "Pascal",
    ".pl": "Perl",
    ".pm": "Perl",
    ".t": "Perl",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".psd1": "PowerShell",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".fish": "Fish",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".astro": "Astro",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".proto": "Protocol Buffers",
    ".thrift": "Thrift",
    ".sql": "SQL",
    ".rkt": "Racket",
    ".scm": "Scheme",
    ".ss": "Scheme",
    ".lisp": "Common Lisp",
    ".lsp": "Common Lisp",
    ".cl": "Common Lisp",
    ".el": "Emacs Lisp",
    ".vim": "Vimscript",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".ps": "PostScript",
    ".eps": "PostScript",
    ".groovy": "Groovy",
    ".gradle": "Groovy",
    ".tf": "Terraform",
    ".tfvars": "Terraform",
    ".hcl": "HCL",
    ".dockerfile": "Dockerfile",
    ".makefile": "Makefile",
    ".mk": "Makefile",
    ".cmake": "CMake",
    ".star": "Starlark",
    ".bzl": "Starlark",
    ".bazel": "Starlark",
}

MANIFEST_LANGUAGES = {
    "package.json": ("JavaScript/TypeScript", "npm"),
    "package-lock.json": ("JavaScript/TypeScript", "npm"),
    "Cargo.toml": ("Rust", "cargo"),
    "pyproject.toml": ("Python", "pypi"),
    "uv.lock": ("Python", "pypi"),
    "poetry.lock": ("Python", "pypi"),
    "requirements.txt": ("Python", "pypi"),
    "Pipfile": ("Python", "pypi"),
    "Pipfile.lock": ("Python", "pypi"),
    "setup.py": ("Python", "pypi"),
    "setup.cfg": ("Python", "pypi"),
    "go.mod": ("Go", "go"),
    "go.sum": ("Go", "go"),
    "pom.xml": ("Java/Kotlin", "maven"),
    "packages.lock.json": ("C#/F#", "nuget"),
    "composer.json": ("PHP", "packagist"),
    "composer.lock": ("PHP", "packagist"),
    "Gemfile": ("Ruby", "rubygems"),
    "Gemfile.lock": ("Ruby", "rubygems"),
    "Package.swift": ("Swift", "swiftpm"),
    "Package.resolved": ("Swift", "swiftpm"),
    "pubspec.yaml": ("Dart", "pub"),
    "pubspec.lock": ("Dart", "pub"),
    "mix.exs": ("Elixir/Erlang", "hex"),
    "mix.lock": ("Elixir/Erlang", "hex"),
    "build.gradle": ("Java/Kotlin", "gradle"),
    "build.gradle.kts": ("Kotlin/Java", "gradle"),
    "settings.gradle": ("Java/Kotlin", "gradle"),
    "settings.gradle.kts": ("Kotlin/Java", "gradle"),
    "build.sbt": ("Scala", "sbt"),
    "CMakeLists.txt": ("C/C++", "cmake"),
    "meson.build": ("C/C++/Python", "meson"),
    "vcpkg.json": ("C++", "vcpkg"),
    "conanfile.txt": ("C++", "conan"),
    "conanfile.py": ("C++", "conan"),
    "Podfile": ("Swift/Objective-C", "cocoapods"),
    "Podfile.lock": ("Swift/Objective-C", "cocoapods"),
    "Cartfile": ("Swift/Objective-C", "carthage"),
    "Cartfile.resolved": ("Swift/Objective-C", "carthage"),
    "deno.json": ("TypeScript/JavaScript", "deno"),
    "deno.jsonc": ("TypeScript/JavaScript", "deno"),
    "deno.lock": ("TypeScript/JavaScript", "deno"),
    "bun.lock": ("JavaScript/TypeScript", "bun"),
    "bun.lockb": ("JavaScript/TypeScript", "bun"),
    "flake.nix": ("Nix", "nix"),
    "Project.toml": ("Julia", "julia"),
    "Manifest.toml": ("Julia", "julia"),
    "shard.yml": ("Crystal", "shards"),
    "shard.lock": ("Crystal", "shards"),
    "nimble.nimble": ("Nim", "nimble"),
    "nimble.lock": ("Nim", "nimble"),
    "dune-project": ("OCaml", "dune"),
    "dune": ("OCaml", "dune"),
    "opam": ("OCaml", "opam"),
    "esy.json": ("OCaml/Reason", "esy"),
    "cabal.project": ("Haskell", "cabal"),
    "stack.yaml": ("Haskell", "stack"),
    "stack.yaml.lock": ("Haskell", "stack"),
    "renv.lock": ("R", "cran"),
    "DESCRIPTION": ("R", "cran"),
    "rebar.config": ("Erlang", "rebar3"),
    "rebar.lock": ("Erlang", "rebar3"),
    "WORKSPACE": ("Bazel", "bazel"),
    "WORKSPACE.bazel": ("Bazel", "bazel"),
    "BUILD": ("Bazel", "bazel"),
    "BUILD.bazel": ("Bazel", "bazel"),
    "BUCK": ("Buck", "buck"),
    "Buck.toml": ("Buck", "buck"),
    "deps.edn": ("Clojure", "clojure"),
    "shadow-cljs.edn": ("ClojureScript", "clojure"),
    "project.clj": ("Clojure", "clojure"),
    "Gopkg.toml": ("Go", "dep"),
    "Gopkg.lock": ("Go", "dep"),
    "glide.yaml": ("Go", "glide"),
}


def normalize_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def clean_version(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"v?\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?", value):
        return value.removeprefix("v")
    return None


def _project_files(root: pathlib.Path, max_files: int = 20_000) -> tuple[list[pathlib.Path], dict[str, int]]:
    manifests: list[pathlib.Path] = []
    language_counts: dict[str, int] = {}
    seen = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".cache"))
        for filename in sorted(files):
            seen += 1
            if seen > max_files:
                return manifests, language_counts
            path = pathlib.Path(current) / filename
            if filename in MANIFESTS:
                manifests.append(path)
            language = EXTENSION_LANGUAGES.get(path.suffix.lower())
            if language:
                language_counts[language] = language_counts.get(language, 0) + 1
    return manifests, language_counts


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _load_toml(path: pathlib.Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _npm_locked(path: pathlib.Path) -> dict[str, str]:
    data = _load_json(path)
    locked: dict[str, str] = {}
    packages = data.get("packages", {})
    for package_path, meta in sorted(packages.items(), key=lambda item: item[0].count("node_modules/")):
        marker = "node_modules/"
        if marker not in package_path or not isinstance(meta, dict):
            continue
        name = package_path.rsplit(marker, 1)[-1]
        if version := clean_version(str(meta.get("version", ""))):
            locked.setdefault(name, version)
    for name, meta in data.get("dependencies", {}).items():
        if isinstance(meta, dict) and (version := clean_version(str(meta.get("version", "")))):
            locked.setdefault(name, version)
    return locked


def _toml_locked(path: pathlib.Path) -> dict[str, str]:
    data = _load_toml(path)
    locked: dict[str, str] = {}
    for item in data.get("package", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if name and (version := clean_version(str(item.get("version", "")))):
            locked[name] = version
    return locked


def _composer_locked(path: pathlib.Path) -> dict[str, str]:
    data = _load_json(path)
    locked: dict[str, str] = {}
    for group in ("packages", "packages-dev"):
        for item in data.get(group, []):
            if isinstance(item, dict) and item.get("name"):
                version = clean_version(str(item.get("version", "")).lstrip("v"))
                if version:
                    locked[str(item["name"])] = version
    return locked


def _nuget_locked(path: pathlib.Path) -> dict[str, str]:
    data = _load_json(path)
    locked: dict[str, str] = {}
    for target in data.get("dependencies", {}).values():
        if not isinstance(target, dict):
            continue
        for name, meta in target.items():
            if isinstance(meta, dict) and (version := clean_version(str(meta.get("resolved", "")))):
                locked[name] = version
    return locked


def _swift_locked(path: pathlib.Path) -> dict[str, str]:
    data = _load_json(path)
    pins = data.get("pins") or data.get("object", {}).get("pins") or []
    locked: dict[str, str] = {}
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        name = str(pin.get("identity") or pin.get("package") or "")
        state = pin.get("state", {})
        if name and isinstance(state, dict) and (version := clean_version(str(state.get("version", "")))):
            locked[name] = version
    return locked


def _gem_locked(path: pathlib.Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"^    ([A-Za-z0-9_.-]+) \((\d+(?:\.\d+)+(?:[-.][A-Za-z0-9.-]+)?)\)", text, re.MULTILINE)
    }


def _go_dependencies(path: pathlib.Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    return {
        match.group(1): match.group(2).removeprefix("v")
        for match in re.finditer(r"^\s*([^\s()]+)\s+v(\d+(?:\.\d+)+(?:[-+][^\s]+)?)", text, re.MULTILINE)
    }


def _maven_dependencies(path: pathlib.Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    locked: dict[str, str] = {}
    for match in re.finditer(r"<dependency\b[^>]*>(.*?)</dependency>", text, re.DOTALL):
        block = match.group(1)

        def tag(name: str) -> str:
            value = re.search(rf"<{name}>\s*([^<]+?)\s*</{name}>", block)
            return value.group(1).strip() if value else ""

        group = tag("groupId")
        artifact = tag("artifactId")
        version = clean_version(tag("version"))
        if artifact and version:
            locked[f"{group}:{artifact}" if group else artifact] = version
    return locked


def _gradle_dependencies(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from Gradle build files (Groovy or Kotlin DSL)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    locked: dict[str, str] = {}
    # Match group:artifact:version patterns (Gradle coordinate notation)
    for match in re.finditer(
        r"['\"]([a-zA-Z0-9_.-]+):([a-zA-Z0-9_.-]+):(\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?)['\"]",
        text,
    ):
        group, artifact, version = match.group(1), match.group(2), match.group(3)
        key = f"{group}:{artifact}" if group else artifact
        if v := clean_version(version):
            locked[key] = v
    return locked


def _sbt_dependencies(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from SBT build files."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    locked: dict[str, str] = {}
    # SBT uses %% and % for Scala and Java dependencies
    for match in re.finditer(
        r"['\"]([a-zA-Z0-9_.-]+)\s*%%?\s*([a-zA-Z0-9_.-]+)\s*%\s*['\"](\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?)['\"]",
        text,
    ):
        group, artifact, version = match.group(1), match.group(2), match.group(3)
        key = f"{group}:{artifact}" if group else artifact
        if v := clean_version(version):
            locked[key] = v
    return locked


def _vcpkg_locked(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from vcpkg.json."""
    data = _load_json(path)
    locked: dict[str, str] = {}
    for dep in data.get("dependencies", []):
        if isinstance(dep, str):
            locked[dep] = ""  # vcpkg.json doesn't have versions
        elif isinstance(dep, dict) and dep.get("name"):
            locked[dep["name"]] = str(dep.get("version", ""))
    if isinstance(data.get("version"), str):
        locked[data.get("name", "root")] = data["version"]
    return locked


def _deno_locked(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from deno.lock."""
    data = _load_json(path)
    locked: dict[str, str] = {}
    for key, value in data.get("remote", {}).items():
        if isinstance(value, str) and (v := clean_version(value)):
            locked[key] = v
    for entry in data.get("packages", []):
        if isinstance(entry, dict):
            spec = entry.get("spec", "")
            if "@" in spec:
                name, _, version = spec.rpartition("@")
                # Strip npm: or other scheme prefixes
                if ":" in name:
                    name = name.rsplit(":", 1)[-1]
                if name and (v := clean_version(version)):
                    locked[name] = v
    return locked


def _bun_locked(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from bun.lock."""
    data = _load_json(path)
    locked: dict[str, str] = {}
    for name, meta in data.get("packages", {}).items():
        if isinstance(meta, dict) and (v := clean_version(str(meta.get("version", "")))):
            locked[name] = v
        elif isinstance(meta, str) and (v := clean_version(meta)):
            locked[name] = v
    return locked


def _podfile_locked(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from Podfile.lock."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    locked: dict[str, str] = {}
    for match in re.finditer(
        r"^\s+- ([A-Za-z0-9_.-]+)(/[A-Za-z0-9_.-]+)? \((\d+(?:\.\d+)+(?:[-.][A-Za-z0-9.-]+)?)\)",
        text,
        re.MULTILINE,
    ):
        name = match.group(1)
        version = match.group(3)
        if v := clean_version(version):
            locked[name] = v
    return locked


def _julia_manifest(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from Julia Project.toml or Manifest.toml."""
    data = _load_toml(path)
    locked: dict[str, str] = {}
    for name, version in data.get("deps", {}).items():
        if isinstance(version, str):
            if v := clean_version(version):
                locked[name] = v
            else:
                # UUID reference, no version
                locked[name] = ""
    # Manifest.toml has [deps] with UUIDs and [[deps.X]] with versions
    for key, value in data.items():
        if key.startswith("deps") and isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    name = entry.get("name", "")
                    version = entry.get("version", "")
                    if name and (v := clean_version(str(version))):
                        locked[name] = v
    return locked


def _shard_yml(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from Crystal shard.yml."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    locked: dict[str, str] = {}
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies:":
            in_deps = True
            continue
        if in_deps:
            if stripped and not line.startswith(" "):
                in_deps = False
                continue
            match = re.match(r"^\s+([A-Za-z0-9_.-]+):\s*$", line)
            if match:
                current = match.group(1)
                locked[current] = ""
            match = re.match(r"^\s+version:\s*['\"]?(\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?)['\"]?\s*$", line)
            if match and current:
                if v := clean_version(match.group(1)):
                    locked[current] = v
    return locked


def _shard_lock(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from shard.lock."""
    data = _load_json(path)
    locked: dict[str, str] = {}
    for entry in data.get("shards", []):
        if isinstance(entry, dict):
            name = entry.get("name", "")
            version = entry.get("version", "")
            if name and (v := clean_version(str(version))):
                locked[name] = v
    return locked


def _renv_locked(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from R renv.lock."""
    data = _load_json(path)
    locked: dict[str, str] = {}
    packages = data.get("Packages", {})
    for name, meta in packages.items():
        if isinstance(meta, dict) and (v := clean_version(str(meta.get("Version", "")))):
            locked[name] = v
    return locked


def _rebar_lock(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from rebar.lock."""
    data = _load_json(path)
    locked: dict[str, str] = {}
    for entry in data if isinstance(data, list) else []:
        if isinstance(entry, list) and len(entry) >= 2:
            name = str(entry[0])
            version = str(entry[1])
            if v := clean_version(version):
                locked[name] = v
    return locked


def _deps_edn(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from Clojure deps.edn."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    locked: dict[str, str] = {}
    # Simple EDN parsing for {:deps {name/version {:mvn/version "x.y.z"}}}
    for match in re.finditer(
        r"([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)\s*\{[^}]*:mvn/version\s+['\"](\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?)['\"]",
        text,
    ):
        name = match.group(1)
        version = match.group(2)
        if v := clean_version(version):
            locked[name] = v
    return locked


def _mix_locked(path: pathlib.Path) -> dict[str, str]:
    """Extract dependencies from Elixir mix.lock."""
    data = _load_text(path)
    locked: dict[str, str] = {}
    # mix.lock format: {"lib_name", [hex: ..., version: "x.y.z", ...]}
    for match in re.finditer(
        r'"([a-zA-Z0-9_.-]+)"\s*,\s*\{[^}]*:version\s*,\s*"(\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?)"',
        data,
    ):
        name = match.group(1)
        version = match.group(2)
        if v := clean_version(version):
            locked[name] = v
    return locked


def _load_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _python_requirement(value: str) -> tuple[str, str | None]:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*(.*)", value)
    if not match:
        return value.strip(), None
    requested = match.group(2).split(";", 1)[0].strip() or None
    return match.group(1), requested


def analyze_project(root: pathlib.Path, registry: dict[str, Any]) -> dict[str, Any]:
    root = root.expanduser().resolve()
    manifests, file_languages = _project_files(root)
    manifest_names = {path.name for path in manifests}
    languages = dict(file_languages)
    ecosystems: set[str] = set()
    for manifest in manifest_names:
        if manifest in MANIFEST_LANGUAGES:
            language, ecosystem = MANIFEST_LANGUAGES[manifest]
            component_languages = language.replace("#", "Sharp").split("/")
            if not any(component.replace("Sharp", "#") in languages for component in component_languages):
                languages.setdefault(language, 1)
            ecosystems.add(ecosystem)

    locked_by_eco: dict[str, dict[str, str]] = {
        "npm": {},
        "cargo": {},
        "pypi": {},
        "go": {},
        "maven": {},
        "nuget": {},
        "packagist": {},
        "rubygems": {},
        "swiftpm": {},
        "gradle": {},
        "sbt": {},
        "cmake": {},
        "vcpkg": {},
        "conan": {},
        "cocoapods": {},
        "carthage": {},
        "deno": {},
        "bun": {},
        "nix": {},
        "julia": {},
        "shards": {},
        "nimble": {},
        "dune": {},
        "opam": {},
        "esy": {},
        "cabal": {},
        "stack": {},
        "cran": {},
        "rebar3": {},
        "bazel": {},
        "buck": {},
        "clojure": {},
        "hex": {},
        "pub": {},
    }
    for path in manifests:
        if path.name == "package-lock.json":
            locked_by_eco["npm"].update(_npm_locked(path))
        elif path.name in {"Cargo.lock", "uv.lock", "poetry.lock"}:
            eco = "cargo" if path.name == "Cargo.lock" else "pypi"
            locked_by_eco[eco].update(_toml_locked(path))
        elif path.name == "go.mod":
            locked_by_eco["go"].update(_go_dependencies(path))
        elif path.name == "go.sum":
            locked_by_eco["go"].update(_go_dependencies(path))
        elif path.name == "pom.xml":
            locked_by_eco["maven"].update(_maven_dependencies(path))
        elif path.name == "packages.lock.json":
            locked_by_eco["nuget"].update(_nuget_locked(path))
        elif path.name == "composer.lock":
            locked_by_eco["packagist"].update(_composer_locked(path))
        elif path.name == "Gemfile.lock":
            locked_by_eco["rubygems"].update(_gem_locked(path))
        elif path.name == "Package.resolved":
            locked_by_eco["swiftpm"].update(_swift_locked(path))
        elif path.name in {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
            locked_by_eco["gradle"].update(_gradle_dependencies(path))
        elif path.name == "build.sbt":
            locked_by_eco["sbt"].update(_sbt_dependencies(path))
        elif path.name == "vcpkg.json":
            locked_by_eco["vcpkg"].update(_vcpkg_locked(path))
        elif path.name == "deno.lock":
            locked_by_eco["deno"].update(_deno_locked(path))
        elif path.name == "bun.lock":
            locked_by_eco["bun"].update(_bun_locked(path))
        elif path.name == "Podfile.lock":
            locked_by_eco["cocoapods"].update(_podfile_locked(path))
        elif path.name == "Project.toml":
            locked_by_eco["julia"].update(_julia_manifest(path))
        elif path.name == "Manifest.toml":
            locked_by_eco["julia"].update(_julia_manifest(path))
        elif path.name == "shard.yml":
            locked_by_eco["shards"].update(_shard_yml(path))
        elif path.name == "shard.lock":
            locked_by_eco["shards"].update(_shard_lock(path))
        elif path.name == "renv.lock":
            locked_by_eco["cran"].update(_renv_locked(path))
        elif path.name == "rebar.lock":
            locked_by_eco["rebar3"].update(_rebar_lock(path))
        elif path.name == "deps.edn":
            locked_by_eco["clojure"].update(_deps_edn(path))
        elif path.name == "mix.lock":
            locked_by_eco["hex"].update(_mix_locked(path))

    dependencies: dict[tuple[str, str], dict[str, Any]] = {}

    def add_dependency(ecosystem: str, name: str, requested: str | None, manifest: pathlib.Path) -> None:
        key = (ecosystem, normalize_package(name))
        exact = locked_by_eco.get(ecosystem, {}).get(name)
        if exact is None and ecosystem == "pypi":
            normalized = normalize_package(name)
            exact = next((value for package, value in locked_by_eco[ecosystem].items() if normalize_package(package) == normalized), None)
        item = dependencies.setdefault(
            key,
            {
                "ecosystem": ecosystem,
                "package": name,
                "requested": requested,
                "resolved": exact,
                "manifests": [],
            },
        )
        item["requested"] = item["requested"] or requested
        item["resolved"] = item["resolved"] or exact
        relative = str(manifest.relative_to(root))
        if relative not in item["manifests"]:
            item["manifests"].append(relative)

    for path in manifests:
        if path.name == "package.json":
            data = _load_json(path)
            for group in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for name, requested in data.get(group, {}).items():
                    add_dependency("npm", name, str(requested), path)
        elif path.name == "Cargo.toml":
            data = _load_toml(path)
            for group in ("dependencies", "dev-dependencies", "build-dependencies"):
                for name, requested in data.get(group, {}).items():
                    value = requested if isinstance(requested, str) else requested.get("version") if isinstance(requested, dict) else None
                    add_dependency("cargo", name, str(value) if value else None, path)
        elif path.name == "pyproject.toml":
            data = _load_toml(path)
            requirements = list(data.get("project", {}).get("dependencies", []))
            for group in data.get("project", {}).get("optional-dependencies", {}).values():
                if isinstance(group, list):
                    requirements.extend(group)
            for requirement in requirements:
                name, requested = _python_requirement(str(requirement))
                add_dependency("pypi", name, requested, path)
        elif path.name == "composer.json":
            data = _load_json(path)
            for group in ("require", "require-dev"):
                for name, requested in data.get(group, {}).items():
                    if name != "php":
                        add_dependency("packagist", name, str(requested), path)
        elif path.name == "go.mod":
            for name, version in _go_dependencies(path).items():
                add_dependency("go", name, version, path)
        elif path.name == "pom.xml":
            for name, version in _maven_dependencies(path).items():
                add_dependency("maven", name, version, path)
        elif path.name in {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
            for name, version in _gradle_dependencies(path).items():
                add_dependency("gradle", name, version, path)
        elif path.name == "build.sbt":
            for name, version in _sbt_dependencies(path).items():
                add_dependency("sbt", name, version, path)
        elif path.name == "vcpkg.json":
            for name, version in _vcpkg_locked(path).items():
                add_dependency("vcpkg", name, version or None, path)
        elif path.name == "deno.json":
            data = _load_json(path)
            for name, requested in data.get("imports", {}).items():
                add_dependency("deno", name, str(requested), path)
            for name, requested in data.get("scopes", {}).items():
                if isinstance(requested, dict):
                    for scoped_name, scoped_version in requested.items():
                        add_dependency("deno", scoped_name, str(scoped_version), path)
        elif path.name == "deno.lock":
            for name, version in _deno_locked(path).items():
                add_dependency("deno", name, version, path)
        elif path.name == "bun.lock":
            for name, version in _bun_locked(path).items():
                add_dependency("bun", name, version, path)
        elif path.name == "Podfile":
            try:
                text = path.read_text(encoding="utf-8")
                for match in re.finditer(r"pod\s+['\"]([A-Za-z0-9_.-]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?", text):
                    name = match.group(1)
                    version = match.group(2)
                    add_dependency("cocoapods", name, version, path)
            except Exception:
                pass
        elif path.name == "Podfile.lock":
            for name, version in _podfile_locked(path).items():
                add_dependency("cocoapods", name, version, path)
        elif path.name == "Cartfile":
            try:
                text = path.read_text(encoding="utf-8")
                for match in re.finditer(r"(?:github|git|binary)\s+['\"]([^'\"]+)['\"](?:\s+['\"]([^'\"]+)['\"])?", text):
                    name = match.group(1).split("/")[-1]
                    version = match.group(2)
                    add_dependency("carthage", name, version, path)
            except Exception:
                pass
        elif path.name == "Project.toml":
            for name, version in _julia_manifest(path).items():
                add_dependency("julia", name, version or None, path)
        elif path.name == "shard.yml":
            for name, version in _shard_yml(path).items():
                add_dependency("shards", name, version or None, path)
        elif path.name == "renv.lock":
            for name, version in _renv_locked(path).items():
                add_dependency("cran", name, version, path)
        elif path.name == "deps.edn":
            for name, version in _deps_edn(path).items():
                add_dependency("clojure", name, version, path)
        elif path.name == "mix.exs":
            try:
                text = path.read_text(encoding="utf-8")
                for match in re.finditer(r"\{:(\w+),\s*['\"](\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?)['\"]", text):
                    name, version = match.group(1), match.group(2)
                    add_dependency("hex", name, version, path)
            except Exception:
                pass
        elif path.name == "mix.lock":
            for name, version in _mix_locked(path).items():
                add_dependency("hex", name, version, path)
        elif path.name == "requirements.txt":
            try:
                text = path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        name, requested = _python_requirement(line)
                        if name:
                            add_dependency("pypi", name, requested, path)
            except Exception:
                pass
        elif path.name == "Pipfile":
            data = _load_toml(path) if path.suffix == ".toml" else {}
            if not data:
                try:
                    text = path.read_text(encoding="utf-8")
                    for section in ("packages", "dev-packages"):
                        in_section = False
                        for line in text.splitlines():
                            if f"[{section}]" in line:
                                in_section = True
                                continue
                            if in_section and line.startswith("["):
                                in_section = False
                                continue
                            if in_section:
                                match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)$", line)
                                if match:
                                    name = match.group(1)
                                    requested = match.group(2).strip().strip("\"'")
                                    add_dependency("pypi", name, requested, path)
                except Exception:
                    pass
            else:
                for section in ("packages", "dev-packages"):
                    for name, requested in data.get(section, {}).items():
                        add_dependency("pypi", name, str(requested), path)
        elif path.name == "pubspec.yaml":
            try:
                text = path.read_text(encoding="utf-8")
                in_deps = False
                for line in text.splitlines():
                    if line.strip() in ("dependencies:", "dev_dependencies:"):
                        in_deps = True
                        continue
                    if in_deps and line and not line.startswith(" "):
                        in_deps = False
                        continue
                    if in_deps:
                        match = re.match(r"^\s+([A-Za-z0-9_.-]+):\s*(.*)$", line)
                        if match:
                            name = match.group(1)
                            requested = match.group(2).strip()
                            if requested.startswith("^"):
                                requested = requested[1:]
                            add_dependency("pub", name, requested, path)
            except Exception:
                pass
        elif path.name == "Package.swift":
            try:
                text = path.read_text(encoding="utf-8")
                for match in re.finditer(r"\.package\s*\([^)]*url:\s*['\"]([^'\"]+)['\"][^)]*\)", text):
                    url = match.group(1)
                    name = url.rstrip("/").split("/")[-1].replace(".git", "")
                    add_dependency("swiftpm", name, None, path)
                for match in re.finditer(r"\.product\(\s*name:\s*['\"]([A-Za-z0-9_.-]+)['\"]", text):
                    name = match.group(1)
                    add_dependency("swiftpm", name, None, path)
            except Exception:
                pass

    registry_map: dict[tuple[str, str], str] = {}
    for lib, meta in registry.items():
        ecosystem = "cargo" if meta.get("eco") == "crates" else str(meta.get("eco", "gh"))
        package = str(meta.get("pkg") or meta.get("gh", "").split("/")[-1] or lib)
        registry_map[(ecosystem, normalize_package(package))] = lib
        # C++ libraries with eco "other" also match cmake/vcpkg/conan ecosystems
        if ecosystem == "other":
            for cpp_eco in ("cmake", "vcpkg", "conan", "bazel", "buck", "meson"):
                registry_map[(cpp_eco, normalize_package(package))] = lib
        # Maven libraries also match gradle and sbt ecosystems
        if ecosystem == "maven":
            for jvm_eco in ("gradle", "sbt", "bazel", "buck"):
                registry_map[(jvm_eco, normalize_package(package))] = lib
        # npm libraries also match deno and bun ecosystems
        if ecosystem == "npm":
            for js_eco in ("deno", "bun"):
                registry_map[(js_eco, normalize_package(package))] = lib
        # swiftpm libraries also match cocoapods and carthage ecosystems
        if ecosystem == "swiftpm":
            for swift_eco in ("cocoapods", "carthage"):
                registry_map[(swift_eco, normalize_package(package))] = lib
        # hex libraries also match rebar3 ecosystem
        if ecosystem == "hex":
            for erl_eco in ("rebar3",):
                registry_map[(erl_eco, normalize_package(package))] = lib

    libraries: list[dict[str, Any]] = []
    for (ecosystem, normalized), item in dependencies.items():
        if lib := registry_map.get((ecosystem, normalized)):
            libraries.append(
                {
                    "lib": lib,
                    "package": item["package"],
                    "ecosystem": ecosystem,
                    "requested": item["requested"],
                    "resolved": item["resolved"],
                    "manifests": sorted(item["manifests"]),
                }
            )

    return {
        "project": str(root),
        "languages": [
            {"language": language, "files": count}
            for language, count in sorted(languages.items(), key=lambda item: (-item[1], item[0]))
        ],
        "ecosystems": sorted(ecosystems),
        "manifests": sorted(str(path.relative_to(root)) for path in manifests),
        "dependencies": sorted(dependencies.values(), key=lambda item: (item["ecosystem"], normalize_package(item["package"]))),
        "libraries": sorted(libraries, key=lambda item: item["lib"]),
    }


def detected_versions(analysis: dict[str, Any]) -> dict[str, str]:
    return {
        item["lib"]: version
        for item in analysis.get("libraries", [])
        if (version := clean_version(item.get("resolved")))
    }
