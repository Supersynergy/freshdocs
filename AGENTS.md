# Freshdocs — Agent Guide

Freshdocs provides version-pinned, locally searchable documentation for coding agents. It prevents stale API facts by fetching real docs from library repos and indexing them in SQLite FTS5.

## Quick Commands

```sh
freshdocs context "how to use middleware" --lib hono --limit 4
freshdocs context "websocket state sharing" --lib axum --lib tokio
freshdocs search "cookie parser" --lib hono --limit 3
freshdocs sync --project .          # refresh stale docs
freshdocs sync --latest --project . # sync latest versions
freshdocs status                    # show all libs + freshness
freshdocs doctor                    # health check
freshdocs analyze --project .       # detect project libs
freshdocs deprecations --project .  # scan for deprecated APIs (version-filtered)
freshdocs drift --project .         # check for new major versions
freshdocs auto-registry --project . # auto-register unregistered deps
freshdocs backfill                  # update is_code for existing docs
freshdocs backfill --embeddings     # generate semantic embeddings (optional, slow)
freshdocs backfill --embeddings --lib hono  # embeddings for one lib only
```

## Features

- **Version-pinned**: docs fetched at exact version refs (not latest)
- **Smart budget**: dynamic limit based on query complexity (2-12 chunks)
- **Code extraction**: `is_code` flag boosts code blocks for "how do I" queries
- **Semantic search**: optional fastembed hybrid FTS5+embeddings (graceful fallback)
- **Cross-library links**: detects lib references in docs, includes related context with `[linked]` marker
- **Diff-aware sync**: `commit_sha` stored, same-SHA skips re-fetch
- **Version-aware deprecations**: filters `@deprecated since X.Y` against installed version
- **Auto-registry**: discovers unregistered deps from lockfiles, resolves to GitHub repos via npm/crates/pypi/go/hex/pub APIs
- **llms.txt**: prioritized when available (14 libs)

## MCP Tools

- `freshdocs_context` — full context pack for a task
- `freshdocs_search` — raw FTS5 search
- `freshdocs_sync` — trigger sync
- `freshdocs_detect` — detect project libs
- `freshdocs_analyze` — full project analysis
- `freshdocs_sources` — library source discovery
- `freshdocs_identity` — model identity probe
- `freshdocs_probe` — model capability probe
- `freshdocs_gap` — model gap analysis
- `freshdocs_deprecations` — scan for deprecated APIs
- `freshdocs_drift` — check for new major versions
- `freshdocs_auto_registry` — auto-register unregistered deps

## Integration

- **Claude Code**: `UserPromptSubmit` hook calls `freshdocs context` for API/docs prompts
- **Codex**: `routed_context` in `routing.py` handles auto-sync + context
- **Agent Token Saver**: `token-stack-prompt.py` includes freshdocs stage (fail-open)
- **MCP**: `freshdocs mcp` serves MCP tools to any MCP client

## Cache

- `~/.freshdocs/registry.json` — library registry (169 libs)
- `~/.freshdocs/state.json` — sync state per library/version
- `~/.freshdocs/freshdocs.db` — SQLite FTS5 index (45K chunks, ~200MB)
- `~/.freshdocs/freshdocs.db` → `doc_embeddings` — optional semantic embeddings

## Notes

- Embeddings backfill runs in background (~28% complete as of 2026-09-13). Use `backfill --embeddings` to continue.
- `is_code` detection: chunks where code covers >40% of content or starts with ``` are marked.
- Auto-registry: `@types/` prefix stripped, `DefinitelyTyped` blocked for non-type packages.
- Hook triggers: `how to`, `create`, `use`, `middleware`, `websocket`, `auth`, `jwt`, `oauth`, etc.
