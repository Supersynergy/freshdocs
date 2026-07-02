from __future__ import annotations

import collections
import datetime as dt
import json
import re
import urllib.parse
from importlib import resources  # nosemgrep: python.lang.compatibility.python37.python37-compatibility-importlib2 - requires-python >=3.11
from typing import Any

from .core import fetch_url

GITHUT_METRICS = {
    "stars": "https://raw.githubusercontent.com/madnight/githut/master/src/data/gh-star-event.json",
    "pushes": "https://raw.githubusercontent.com/madnight/githut/master/src/data/gh-push-event.json",
    "pull_requests": "https://raw.githubusercontent.com/madnight/githut/master/src/data/gh-pull-request.json",
    "issues": "https://raw.githubusercontent.com/madnight/githut/master/src/data/gh-issue-event.json",
}
LINGUIST_URL = "https://raw.githubusercontent.com/github/linguist/master/lib/linguist/languages.yml"


def source_catalog() -> dict[str, Any]:
    with resources.files("freshdocs").joinpath("source_catalog.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def slugify_language(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "language"


def parse_linguist_languages(text: str) -> list[str]:
    langs: list[str] = []
    current: str | None = None
    current_type: str | None = None
    for line in text.splitlines():
        if line and not line.startswith(" ") and line.endswith(":") and not line.startswith("#"):
            if current and current_type == "programming":
                langs.append(current)
            current = line[:-1]
            current_type = None
        elif current and line.startswith("  type:"):
            current_type = line.split(":", 1)[1].strip()
    if current and current_type == "programming":
        langs.append(current)
    return langs


def fetch_linguist_languages() -> list[str]:
    return parse_linguist_languages(fetch_url(LINGUIST_URL))


def fetch_githut_languages() -> list[str]:
    scores: collections.defaultdict[str, float] = collections.defaultdict(float)
    for url in GITHUT_METRICS.values():
        rows = json.loads(fetch_url(url))
        latest = max((int(row["year"]), int(row["quarter"])) for row in rows)
        latest_rows = [row for row in rows if (int(row["year"]), int(row["quarter"])) == latest]
        latest_rows.sort(key=lambda row: int(row["count"]), reverse=True)
        for rank, row in enumerate(latest_rows, 1):
            scores[row["name"]] += 1 / rank
    return [name for name, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def language_seed(limit: int = 300, live: bool = False) -> list[str]:
    catalog = source_catalog()
    names: list[str] = []
    if live:
        for fetcher in (fetch_githut_languages, fetch_linguist_languages):
            try:
                names.extend(fetcher())
            except Exception:
                continue
    names.extend(catalog["default_language_seed"])
    seen: set[str] = set()
    unique = []
    for name in names:
        if name not in seen:
            unique.append(name)
            seen.add(name)
        if len(unique) >= limit:
            break
    return unique


def language_source_entry(language: str, rank: int, catalog: dict[str, Any]) -> dict[str, Any]:
    slug = slugify_language(language)
    quoted = language.replace('"', '\\"')
    registry_sources = catalog.get("registry_sources", {}).get(language, [])
    return {
        "rank": rank,
        "language": language,
        "slug": slug,
        "registries": registry_sources,
        "repo_sources": [
            {
                "id": "ghmax_top_repos",
                "command": f'ghmax --repos --lang "{quoted}" --sort stars --order desc --stars-min 100 -n 50 --format json',
                "why": "High-star repo baseline for the language.",
            },
            {
                "id": "ghmax_recent_repos",
                "command": f'ghmax --repos --lang "{quoted}" --sort updated --order desc --pushed ">2026-01-01" -n 50 --format json',
                "why": "Freshly maintained repo baseline.",
            },
            {
                "id": "gitstars_velocity",
                "command": f'ghmax --gitstars 100 --gitstars-window 7d,30d --gitstars-lang "{quoted}" --gitstars-gems --gitstars-no-lake',
                "why": "Recent star velocity and maintained non-fork gems.",
            },
            {
                "id": "awesome_lists",
                "command": f'ghmax --repos "awesome {quoted}" --topic awesome-list --sort stars --order desc -n 25 --format json',
                "why": "Curated ecosystem and tool lists.",
            },
            {
                "id": "github_topic",
                "url": f"https://github.com/topics/{slug}",
                "why": "GitHub topic page for ecosystem browsing.",
            },
        ],
        "tool_queries": [
            f'{language} compiler runtime',
            f'{language} package manager registry',
            f'{language} language server LSP',
            f'{language} formatter linter',
            f'{language} test framework',
            f'{language} build tool',
            f'{language} documentation generator',
            f'{language} web framework',
            f'{language} agent coding tool',
        ],
    }


def build_source_plan(limit: int = 300, live: bool = False) -> dict[str, Any]:
    catalog = source_catalog()
    languages = language_seed(limit, live=live)
    return {
        "generated": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "limit": limit,
        "live": live,
        "rank_basis": catalog["rank_basis"],
        "global_sources": catalog["sources"],
        "tool_roles": catalog["tool_roles"],
        "languages": [language_source_entry(language, i, catalog) for i, language in enumerate(languages, 1)],
    }


def render_source_plan(plan: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if fmt == "jsonl":
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in plan["languages"]) + "\n"
    lines = [
        "# Freshdocs Source Plan",
        "",
        f"Generated: {plan['generated']}",
        f"Languages: {len(plan['languages'])}",
        f"Live refresh: {plan['live']}",
        "",
        "## Ranking Basis",
        "",
        plan["rank_basis"],
        "",
        "## Global Sources",
        "",
        "| id | kind | why |",
        "|---|---|---|",
    ]
    for source in plan["global_sources"]:
        lines.append(f"| {source['id']} | {source['kind']} | {source['why']} |")
    lines.extend(["", "## Language Harvest Map", ""])
    for row in plan["languages"]:
        registries = ", ".join(row["registries"]) if row["registries"] else "-"
        lines.extend(
            [
                f"### {row['rank']}. {row['language']}",
                "",
                f"- registries: {registries}",
                f"- GitHub topic: https://github.com/topics/{row['slug']}",
                f"- top repos: `{row['repo_sources'][0]['command']}`",
                f"- recent repos: `{row['repo_sources'][1]['command']}`",
                f"- GitStars velocity: `{row['repo_sources'][2]['command']}`",
                f"- awesome lists: `{row['repo_sources'][3]['command']}`",
                f"- tool queries: {', '.join(row['tool_queries'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
