from __future__ import annotations

import datetime as dt
import http.client
import json
import os
import pathlib
import re
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
from dataclasses import dataclass
from importlib import resources  # nosemgrep: python.lang.compatibility.python37.python37-compatibility-importlib2 - requires-python >=3.11
from typing import Any

APP_DIR = pathlib.Path(os.environ.get("FRESHDOCS_HOME", pathlib.Path.home() / ".freshdocs"))
REGISTRY_PATH = pathlib.Path(os.environ.get("FRESHDOCS_REGISTRY", APP_DIR / "registry.json"))
STATE_PATH = pathlib.Path(os.environ.get("FRESHDOCS_STATE", APP_DIR / "state.json"))
DB_PATH = pathlib.Path(os.environ.get("FRESHDOCS_DB", APP_DIR / "freshdocs.db"))
SOURCE = "freshdocs"
CHUNK_SIZE = 1800
MAX_DOC_CHARS = 120_000
USER_AGENT = "freshdocs/0.1"


class TransientHTTPError(RuntimeError):
    pass


@dataclass(frozen=True)
class LibDoc:
    lib: str
    version: str
    checked: str
    source_name: str
    text: str


def today() -> str:
    return dt.date.today().isoformat()


def load_json(path: pathlib.Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_registry() -> dict[str, Any]:
    with resources.files("freshdocs").joinpath("default_registry.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_registry() -> dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        write_json(REGISTRY_PATH, default_registry())
    return load_json(REGISTRY_PATH, {"libs": {}})


def gh_token() -> str | None:
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    return proc.stdout.strip() or None


def validate_https_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"refusing non-https URL: {url}")
    return parsed


def https_get(url: str, headers: dict[str, str], timeout: int, redirects: int = 3) -> str:
    parsed = validate_https_url(url)
    path = urllib.parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    # nosemgrep: python.lang.security.audit.httpsconnection-detected - Python >=3.11 verifies HTTPS certificates by default.
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout, context=ssl.create_default_context())
    try:
        conn.request("GET", path, headers=headers)
        res = conn.getresponse()
        body = res.read()
    finally:
        conn.close()
    if res.status in {301, 302, 303, 307, 308} and redirects > 0:
        location = res.getheader("Location")
        if not location:
            raise RuntimeError(f"GET {url} redirected without Location header")
        return https_get(urllib.parse.urljoin(url, location), headers, timeout, redirects - 1)
    if res.status in {429, 500, 502, 503}:
        raise TransientHTTPError(f"GET {url} failed: HTTP {res.status}")
    if not 200 <= res.status < 300:
        raise RuntimeError(f"GET {url} failed: HTTP {res.status}")
    return body.decode("utf-8", "replace")


def fetch_url(url: str, timeout: int = 12, retries: int = 3) -> str:
    headers = {"User-Agent": USER_AGENT}
    token = gh_token()
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return https_get(url, headers, timeout)
        except TransientHTTPError as e:
            last = e
            import time

            time.sleep(1.5 * (attempt + 1))
            continue
        except Exception as e:
            last = e
    if last:
        raise last
    raise RuntimeError(f"fetch failed: {url}")


def github_latest(repo: str) -> str:
    for endpoint in (f"https://api.github.com/repos/{repo}/releases/latest", f"https://api.github.com/repos/{repo}/tags"):
        try:
            data = json.loads(fetch_url(endpoint, timeout=8))
            if isinstance(data, dict):
                return data.get("tag_name") or "?"
            if isinstance(data, list) and data:
                return data[0].get("name") or "?"
        except Exception:
            continue
    return "?"


def latest_version(meta: dict[str, Any]) -> str:
    eco = meta.get("eco", "gh")
    repo = meta["gh"]
    pkg = meta.get("pkg") or repo.split("/")[-1]
    try:
        if eco == "npm":
            encoded = urllib.parse.quote(pkg, safe="")
            return json.loads(fetch_url(f"https://registry.npmjs.org/{encoded}/latest")).get("version") or github_latest(repo)
        if eco in {"cargo", "crates"}:
            data = json.loads(fetch_url(f"https://crates.io/api/v1/crates/{pkg}"))["crate"]
            return data.get("max_stable_version") or data.get("newest_version") or github_latest(repo)
        if eco == "pypi":
            return json.loads(fetch_url(f"https://pypi.org/pypi/{pkg}/json"))["info"]["version"]
    except Exception:
        pass
    return github_latest(repo)


def fetch_library(name: str, meta: dict[str, Any], version: str | None = None) -> tuple[str | None, str | None]:
    repo = meta["gh"]
    branch = meta.get("branch", "main")
    version = version or latest_version(meta)
    parts: list[tuple[str, str]] = []
    if meta.get("llms"):
        try:
            parts.append(("llms.txt", fetch_url(meta["llms"])))
        except Exception:
            pass
    prefixes = [""]
    if meta.get("path"):
        prefixes.insert(0, meta["path"].rstrip("/") + "/")
    for filename in ("README.md", "CHANGELOG.md"):
        got = False
        for prefix in prefixes:
            for br in (branch, "main", "master"):
                try:
                    url = f"https://raw.githubusercontent.com/{repo}/{br}/{prefix}{filename}"
                    text = fetch_url(url)
                    if len(text.strip()) < 200:
                        continue
                    if filename == "CHANGELOG.md" and len(text) > 14_000:
                        text = text[:14_000] + "\n...(older entries trimmed)"
                    parts.append((prefix + filename, text))
                    got = True
                    break
                except Exception:
                    continue
            if got:
                break
    if not parts:
        return None, None
    combined = "\n\n".join(f"<!-- {source} -->\n{text}" for source, text in parts)
    return version, combined[:MAX_DOC_CHARS]


def chunk_markdown(text: str, size: int = CHUNK_SIZE) -> list[str]:
    blocks: list[str] = []
    cur: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{1,2}\s+", line) and cur:
            blocks.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    chunks: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        while len(block) > size:
            cut = block.rfind("\n", 0, size)
            if cut < size // 2:
                cut = size
            chunks.append(block[:cut].strip())
            block = block[cut:].strip()
        if block:
            chunks.append(block)
    return chunks


def db() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, lib TEXT, version TEXT, checked TEXT, title TEXT, source TEXT, text TEXT, UNIQUE(lib, version, title, text))"
    )
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(lib, version, title, text, content='docs', content_rowid='id')"
    )
    return con


def index_docs(name: str, version: str, markdown: str, checked: str) -> int:
    chunks = chunk_markdown(markdown)
    con = db()
    inserted = 0
    with con:
        for i, chunk in enumerate(chunks):
            first = next((line for line in chunk.splitlines() if line.strip() and not line.startswith("<!--")), "")
            title = re.sub(r"^#+\s*", "", first).strip()[:80] or f"chunk {i}"
            cur = con.execute(
                "INSERT OR IGNORE INTO docs(lib, version, checked, title, source, text) VALUES (?, ?, ?, ?, ?, ?)",
                (name, version, checked, title, SOURCE, f"[{name} {version} checked {checked}]\n{chunk}"),
            )
            if cur.rowcount:
                rowid = cur.lastrowid
                con.execute(
                    "INSERT INTO docs_fts(rowid, lib, version, title, text) VALUES (?, ?, ?, ?, ?)",
                    (rowid, name, version, title, chunk),
                )
                inserted += 1
    con.close()
    return inserted


def has_indexed_docs(name: str, version: str) -> bool:
    con = db()
    try:
        row = con.execute("SELECT 1 FROM docs WHERE lib = ? AND version = ? LIMIT 1", (name, version)).fetchone()
        return row is not None
    finally:
        con.close()


def sync_library(name: str, force: bool = False) -> dict[str, Any]:
    reg = ensure_registry()["libs"]
    if name not in reg:
        raise KeyError(f"unknown library: {name}")
    state = load_json(STATE_PATH, {})
    checked = today()
    meta = reg[name]
    version = latest_version(meta)
    if not force and state.get(name, {}).get("version") == version and version != "?" and has_indexed_docs(name, version):
        state[name]["checked"] = checked
        write_json(STATE_PATH, state)
        return {"lib": name, "version": version, "checked": checked, "inserted": 0, "status": "unchanged"}
    resolved, markdown = fetch_library(name, meta, version)
    if not markdown or not resolved:
        return {"lib": name, "version": version, "checked": checked, "inserted": 0, "status": "failed"}
    inserted = index_docs(name, resolved, markdown, checked)
    state[name] = {"version": resolved, "checked": checked, "fetched": checked, "chunks": len(chunk_markdown(markdown))}
    write_json(STATE_PATH, state)
    return {"lib": name, "version": resolved, "checked": checked, "inserted": inserted, "status": "indexed"}


def status_rows() -> list[dict[str, Any]]:
    reg = ensure_registry()["libs"]
    state = load_json(STATE_PATH, {})
    rows = []
    now = dt.date.today()
    for name in sorted(reg):
        item = state.get(name, {})
        checked = item.get("checked") or item.get("fetched")
        age = None
        if checked:
            age = (now - dt.date.fromisoformat(checked)).days
        rows.append({"lib": name, **item, "age": age})
    return rows


def fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]{3,}", query)
    if not terms:
        terms = re.findall(r"[A-Za-z0-9_]+", query)
    return " OR ".join(dict.fromkeys(terms)) or '""'


def search(query: str, libs: list[str] | None = None, limit: int = 6) -> list[dict[str, Any]]:
    con = db()
    terms = fts_query(query)
    try:
        if libs:
            con.execute("CREATE TEMP TABLE IF NOT EXISTS selected_libs(name TEXT PRIMARY KEY)")
            con.execute("DELETE FROM selected_libs")
            con.executemany("INSERT OR IGNORE INTO selected_libs(name) VALUES (?)", [(lib,) for lib in libs])
            rows = con.execute(
                """
                SELECT docs.lib, docs.version, docs.checked, docs.title, docs.text, bm25(docs_fts) AS rank
                FROM docs_fts JOIN docs ON docs_fts.rowid = docs.id
                WHERE docs_fts MATCH ?
                  AND EXISTS (SELECT 1 FROM selected_libs WHERE selected_libs.name = docs.lib)
                ORDER BY rank
                LIMIT ?
                """,
                [terms, limit],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT docs.lib, docs.version, docs.checked, docs.title, docs.text, bm25(docs_fts) AS rank
                FROM docs_fts JOIN docs ON docs_fts.rowid = docs.id
                WHERE docs_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                [terms, limit],
            ).fetchall()
    finally:
        con.close()
    return [
        {"lib": lib, "version": version, "checked": checked, "title": title, "text": text, "rank": rank}
        for lib, version, checked, title, text, rank in rows
    ]


def detect_project_libs(root: pathlib.Path) -> list[str]:
    reg = ensure_registry()["libs"]
    wanted: set[str] = set()
    package_json = root / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            pkg_to_lib = {meta.get("pkg") or meta["gh"].split("/")[-1]: name for name, meta in reg.items()}
            for dep in deps:
                if dep in pkg_to_lib:
                    wanted.add(pkg_to_lib[dep])
                if dep == "@tanstack/react-query":
                    wanted.add("tanstack-query")
        except Exception:
            pass
    cargo = root / "Cargo.toml"
    if cargo.exists():
        try:
            data = tomllib.loads(cargo.read_text(encoding="utf-8"))
            deps = {}
            for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                deps.update(data.get(key, {}))
            for name, meta in reg.items():
                if meta.get("eco") == "cargo" and (meta.get("pkg") or name) in deps:
                    wanted.add(name)
        except Exception:
            pass
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            deps = list(data.get("project", {}).get("dependencies", []))
            optional = data.get("project", {}).get("optional-dependencies", {})
            for group in optional.values():
                if isinstance(group, list):
                    deps.extend(group)
            dep_text = "\n".join(deps).lower()
            for name, meta in reg.items():
                if meta.get("eco") == "pypi" and (meta.get("pkg") or name).lower() in dep_text:
                    wanted.add(name)
        except Exception:
            pass
    return sorted(wanted)


def context_pack(query: str, root: pathlib.Path, libs: list[str] | None = None, limit: int = 6, sync_stale: bool = False) -> str:
    selected = libs or detect_project_libs(root)
    if sync_stale:
        state = load_json(STATE_PATH, {})
        for lib in selected:
            checked = state.get(lib, {}).get("checked") or "2000-01-01"
            age = (dt.date.today() - dt.date.fromisoformat(checked)).days
            if age > 14:
                sync_library(lib)
    hits = search(query, selected or None, limit=limit)
    lines = [
        "FRESHDOCS CONTEXT",
        f"query: {query}",
        f"project: {root}",
        f"libraries: {', '.join(selected) if selected else 'auto: none detected, searched all cached docs'}",
        "",
    ]
    for i, hit in enumerate(hits, 1):
        excerpt = re.sub(r"\n{3,}", "\n\n", hit["text"].strip())
        if len(excerpt) > 1400:
            excerpt = excerpt[:1400].rstrip() + "\n..."
        lines.extend(
            [
                f"[{i}] {hit['lib']} {hit['version']} checked {hit['checked']} - {hit['title']}",
                excerpt,
                "",
            ]
        )
    if not hits:
        lines.append("No local docs matched. Run `freshdocs sync --lib <name>` or `freshdocs add ...`.")
    return "\n".join(lines).rstrip() + "\n"


def add_library(name: str, gh: str, eco: str, branch: str = "main", pkg: str | None = None, path_value: str | None = None, llms: str | None = None) -> None:
    reg = ensure_registry()
    entry: dict[str, Any] = {"gh": gh, "branch": branch, "eco": eco}
    if pkg:
        entry["pkg"] = pkg
    if path_value:
        entry["path"] = path_value
    if llms:
        entry["llms"] = llms
    reg.setdefault("libs", {})[name] = entry
    write_json(REGISTRY_PATH, reg)


def doctor() -> tuple[int, list[str]]:
    messages = []
    ensure_registry()
    con = db()
    try:
        con.execute("SELECT count(*) FROM docs").fetchone()
        con.execute("SELECT count(*) FROM docs_fts").fetchone()
    finally:
        con.close()
    messages.append(f"registry: {REGISTRY_PATH}")
    messages.append(f"state:    {STATE_PATH}")
    messages.append(f"db:       {DB_PATH}")
    messages.append("sqlite fts5: ok")
    return 0, messages


def export_synapse() -> int:
    con = db()
    rows = con.execute("SELECT lib, version, checked, title, text FROM docs ORDER BY lib, version, id").fetchall()
    con.close()
    if not rows:
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        for lib, version, checked, title, text in rows:
            tmp.write(json.dumps({"title": f"doc:{lib}: {title}", "source": "docs-cache", "text": text}, ensure_ascii=False) + "\n")
        temp_path = tmp.name
    try:
        proc = subprocess.run(["synx", "import", temp_path], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stdout + proc.stderr).strip())
        return len(rows)
    finally:
        pathlib.Path(temp_path).unlink(missing_ok=True)
