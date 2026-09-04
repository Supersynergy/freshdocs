# Changelog

## 0.3.1 - 2026-09-04

- Changed separate documentation repositories to be read at a resolved commit instead of a moving branch, so their source URLs stay immutable and are labelled `docs-commit <sha>` rather than `live-unversioned`.
- Added `freshdocs prune` to drop cached versions built by an older indexer; each is re-fetched with the current pipeline the moment a project pins to it, which is instant where re-indexing every historical version took hours.
- Added `freshdocs sync --outdated` to eagerly re-index those versions instead, for callers who want them warm.
- Added a warning when a documentation branch cannot be resolved to a commit.

## 0.3.0 - 2026-09-03

- Added documentation-tree fetching so prose from `docs/` is indexed instead of the README alone.
- Added `--docs-gh` and `--docs-branch` for libraries whose prose lives in a separate website repository, and registered them for hono, astro, tailwindcss, biome, and drizzle-orm.
- Changed `llms.txt` handling to follow its links and index the referenced pages; the bare link index is only stored when no page can be fetched.
- Added a link-density score per chunk and ranked navigation chunks below prose, so a query returns an answer instead of a table of contents.
- Changed search to require every query term before falling back to a partial match.
- Changed a miss to name its cause, give the command that fixes it, and tell the agent not to retry reworded queries.
- Fixed the GitHub tree request being rejected with HTTP 403 because it sent no User-Agent.
- Fixed registry merging so libraries registered earlier still receive fields added to the shipped registry later.
- Added HTML and boilerplate rejection so licence, conduct, and rendered pages never occupy a documentation slot.
- Added an index-format marker so versions cached by an older indexer refresh on the next sync instead of serving thin pre-upgrade chunks forever; `doctor` now reports how many are affected.
- Fixed release-tag detection for projects tagging as `<name>-v<version>`, which had forced bun onto `branch-fallback`.
- Changed the per-library cache bound to 500k characters so a full documentation site fits.
- Fixed the User-Agent still reporting version 0.1.
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
