# Changelog

## Unreleased

- Added release-grade social preview and README demo GIF.
- Changed README structure to lead with proof, badges, safety contract, quick start, and demo.
- Changed package description to the user-facing stale-docs prevention claim.

## 0.2.0 - 2026-07-09

- Added recursive project analysis for languages, ecosystems, monorepo manifests, dependencies, and lockfile versions.
- Changed automatic context routing to prefer the exact version installed by the project instead of the latest registry version.
- Added version-tag lookup with an explicit `branch-fallback` label when a matching source tag cannot be found.
- Split version-check time from document-fetch time and added adaptive freshness windows.
- Added source URLs, refs, content hashes, and per-version cache state.
- Added local-only Codex and Claude Code prompt hooks plus the `freshdocs analyze` command.
- Added one-time migration of the legacy Freshdocs registry from `~/.claude/freshdocs`.

## 0.1.0 - 2026-07-02

- Initial release-ready package.
- Local SQLite FTS docs cache.
- Version resolution via npm, crates.io, PyPI, and GitHub fallback.
- README/CHANGELOG/llms.txt fetcher.
- Repo dependency detection for `package.json`, `Cargo.toml`, and `pyproject.toml`.
- Agent context packs via `freshdocs context`.
- MCP stdio server with context/search/sync/detect tools.
- Top-language source planner with GitHut, GitHub Linguist, optional GitHub-scale command hints, awesome-list, and registry source routes.
- Optional local export hook for private memory workflows.
- GitHub Actions CI for Linux and macOS.
