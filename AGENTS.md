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
freshdocs deprecations --project .  # scan for deprecated APIs
freshdocs drift --project .         # check for new major versions
freshdocs auto-registry --project . # auto-register unregistered deps
freshdocs backfill --embeddings     # generate semantic embeddings (optional)
```

## Features

- **Version-pinned**: docs fetched at exact version refs (not latest)
- **Smart budget**: dynamic limit based on query complexity (2-12 chunks)
- **Code extraction**: `is_code` flag boosts code blocks for "how do I" queries
- **Semantic search**: optional fastembed hybrid FTS5+embeddings (graceful fallback)
- **Cross-library links**: detects lib references in docs, includes related context
- **Diff-aware sync**: commit_sha stored, same-SHA skips re-fetch
- **Version-aware deprecations**: filters `@deprecated since X.Y` against installed version
- **Auto-registry**: discovers unregistered deps from lockfiles, resolves to GitHub repos
- **llms.txt**: prioritized when available (13 libs)

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

## Integration

- **Claude Code**: `UserPromptSubmit` hook calls `freshdocs context` for API/docs prompts
- **Codex**: `routed_context` in `routing.py` handles auto-sync + context
- **Agent Token Saver**: `token-stack-prompt.py` includes freshdocs stage (fail-open)
- **MCP**: `freshdocs mcp` serves MCP tools to any MCP client

## Cache

- `~/.freshdocs/registry.json` — library registry (166 libs)
- `~/.freshdocs/state.json` — sync state per library/version
- `~/.freshdocs/freshdocs.db` — SQLite FTS5 index (43K chunks, 194MB)
- `~/.freshdocs/freshdocs.db` → `doc_embeddings` — optional semantic embeddings
