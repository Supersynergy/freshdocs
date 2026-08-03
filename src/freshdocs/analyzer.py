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
    ".zig": "Zig",
    ".nix": "Nix",
}

MANIFEST_LANGUAGES = {
    "package.json": ("JavaScript/TypeScript", "npm"),
    "Cargo.toml": ("Rust", "cargo"),
    "pyproject.toml": ("Python", "pypi"),
    "go.mod": ("Go", "go"),
    "pom.xml": ("Java/Kotlin", "maven"),
    "packages.lock.json": ("C#/F#", "nuget"),
    "composer.json": ("PHP", "packagist"),
    "Gemfile": ("Ruby", "rubygems"),
    "Package.swift": ("Swift", "swiftpm"),
    "pubspec.yaml": ("Dart", "pub"),
    "mix.exs": ("Elixir/Erlang", "hex"),
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
    }
    for path in manifests:
        if path.name == "package-lock.json":
            locked_by_eco["npm"].update(_npm_locked(path))
        elif path.name in {"Cargo.lock", "uv.lock", "poetry.lock"}:
            eco = "cargo" if path.name == "Cargo.lock" else "pypi"
            locked_by_eco[eco].update(_toml_locked(path))
        elif path.name == "go.mod":
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

    registry_map: dict[tuple[str, str], str] = {}
    for lib, meta in registry.items():
        ecosystem = "cargo" if meta.get("eco") == "crates" else str(meta.get("eco", "gh"))
        package = str(meta.get("pkg") or meta.get("gh", "").split("/")[-1] or lib)
        registry_map[(ecosystem, normalize_package(package))] = lib

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
