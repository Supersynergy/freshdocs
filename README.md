# freshdocs

Stop AI coding agents from using stale docs.

Freshdocs helps Claude Code, Codex, Cursor, OpenCode, and other coding agents stop guessing outdated APIs. It syncs official docs into a local SQLite cache, pins the resolved package version, and prints compact context packs that fit directly above a coding task.

![Freshdocs local docs-to-agent pipeline](https://raw.githubusercontent.com/Supersynergy/freshdocs/main/assets/freshdocs-hero.png)

```sh
uv tool install git+https://github.com/Supersynergy/freshdocs
freshdocs init
freshdocs sync --lib hono
freshdocs context "middleware auth cookies" --lib hono --limit 3
```

You get a small, source-visible block:

```text
FRESHDOCS CONTEXT
query: middleware auth cookies
libraries: hono

[1] hono 4.12.27 checked 2026-07-02 - Features
...
```

## Why This Exists

Agents are fast until they confidently use an API that no longer exists.

The failure is expensive because the code looks plausible. The human only discovers the stale context later, inside build errors, review comments, production bugs, or embarrassing rework.

Freshdocs attacks that exact failure:

- current version facts
- official README, changelog, `llms.txt`, and registry sources
- local cache after sync
- visible checked date
- compact prompt-ready output
- CLI and Model Context Protocol (MCP) interface
- optional source map for language, tool, and repo discovery

## What You See

| Signal | Why it matters |
|---|---|
| Version pin | The agent sees the exact library version Freshdocs resolved. |
| Checked date | Reviewers can tell whether the context is fresh or old. |
| Source label | Snippets point back to docs, changelog, `llms.txt`, or registry data. |
| Explicit miss | Empty cache and stale docs are visible instead of silently guessed. |

## Two-Minute Proof

Run this in any repo:

```sh
freshdocs detect --project .
freshdocs context "what I am about to implement" --project . --sync-stale
```

If Freshdocs detects relevant registered libraries, it can refresh stale docs and return only matching local snippets. If nothing is cached, it says so instead of inventing facts.

That is the trust contract: **missing docs are visible; stale docs are visible; versions are visible.**

## Terms In Plain English

| Term | Meaning |
|---|---|
| MCP | Model Context Protocol: a standard way for AI tools to call local tools. |
| `llms.txt` | A docs file some projects publish specifically for AI tools. |
| SQLite FTS | A local database with full-text search. No hosted service required. |
| Source map | A checklist of where an agent should look before claiming it knows a library or language. |

## Who It Is For

**Developers** use Freshdocs before asking an agent to write code against a framework, SDK, CLI, runtime, or library.

**Tech leads** use it to make agent output easier to review because every snippet carries library, version, and checked date.

**Teams with private docs** use it because the default path is local files and SQLite, not a hosted service.

**Agent builders** use it as a tiny source tool: shell output when the client has no MCP, MCP tools when it does.

## Commands

```sh
freshdocs init
freshdocs add hono --gh honojs/hono --eco npm --pkg hono
freshdocs sync --lib hono
freshdocs status
freshdocs detect --project .
freshdocs context "middleware auth cookies" --project . --sync-stale
freshdocs search "rate limit middleware" --lib hono
freshdocs sources --top-languages 300 --format jsonl
freshdocs mcp
freshdocs doctor
```

## MCP Tools

Run:

```sh
freshdocs mcp
```

Tools:

- `freshdocs_context`: compact docs pack for an agent prompt
- `freshdocs_search`: search cached docs
- `freshdocs_sync`: refresh one registered library
- `freshdocs_detect`: detect registered libraries in a project
- `freshdocs_sources`: generate language/tool/repo source plans

Example config:

```json
{
  "mcpServers": {
    "freshdocs": {
      "command": "freshdocs",
      "args": ["mcp"]
    }
  }
}
```

## Advanced: Source Map

Most users can skip this. It is for people building agents or researching many languages/tools.

Freshdocs can generate a broad source map for agent research:

```sh
freshdocs sources --top-languages 300 --live --format markdown > freshdocs-sources.md
freshdocs sources --top-languages 300 --format jsonl > freshdocs-sources.jsonl
```

This emits a repeatable harvest plan:

```text
language -> registries -> top repos -> recent repos -> curated lists -> tool queries
```

Sources include GitHub Linguist, GitHut, GitHub topics, awesome-list discovery, optional GitHub-scale search command hints, and package registries such as PyPI, npm, crates.io, Maven Central, NuGet, Packagist, RubyGems, Hex, Hackage, CRAN, Julia General, LuaRocks, CPAN, opam, and Nimble.

Use it when the question is not "what does this API do?" but "where should an agent look for the best current tools and repos?"

## How It Works

![Freshdocs flow: official docs to version pin to local cache to agent context](https://raw.githubusercontent.com/Supersynergy/freshdocs/main/assets/freshdocs-flow.svg)

1. `freshdocs sync` resolves the current package version from npm, crates.io, PyPI, or GitHub.
2. It fetches official docs from `llms.txt`, `README.md`, and `CHANGELOG.md` sources.
3. It chunks and indexes snippets in local SQLite FTS.
4. `freshdocs context` searches the local cache and prints a compact context block.
5. The agent receives current docs without a network call at answer time.

Default data location:

```text
~/.freshdocs/
```

Override with:

```sh
FRESHDOCS_HOME=/path/to/cache
FRESHDOCS_REGISTRY=/path/to/registry.json
FRESHDOCS_STATE=/path/to/state.json
FRESHDOCS_DB=/path/to/freshdocs.db
```

## Freshdocs And Hosted Docs Tools

Hosted docs tools such as Context7 are useful when you want instantly available public docs through CLI or MCP.

Freshdocs is useful when you want local control:

| Need | Context7 | freshdocs |
|---|---:|---:|
| Fresh public docs | yes | yes |
| CLI and MCP access | yes | yes |
| Local offline cache after sync | client/service dependent | yes |
| Private/internal docs path | enterprise/cloud path | local-first |
| Repo dependency detection | client dependent | built in |
| Changelog-aware local search | varies | built in |
| No account or hosted dependency at answer time | no | yes after sync |
| Source planner for language/tool/repo discovery | no | yes |

Freshdocs is not trying to replace every docs service. It is a small local trust layer for agents.

## Supported Documentation Sources

- npm packages
- crates.io crates
- PyPI packages
- GitHub releases and tags
- GitHub raw `README.md`
- GitHub raw `CHANGELOG.md`
- `llms.txt`
- monorepo subdirectories via `--path`

## Trust Boundaries

Freshdocs does not promise that every README is complete or correct.

It does promise:

- HTTPS-only fetches
- local SQLite storage
- visible package version
- visible checked date
- explicit misses instead of hidden guesses
- zero runtime dependencies
- no hosted Freshdocs service required

Before shipping code, still run the repo's real tests.

## Development

```sh
git clone https://github.com/Supersynergy/freshdocs
cd freshdocs
uv venv
uv pip install -e .
just ci
```

Release smoke:

```sh
freshdocs init
freshdocs sync --lib hono
freshdocs context "middleware auth" --lib hono
freshdocs sources --top-languages 300 --format jsonl | wc -l
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' | freshdocs mcp
```

## Design Contract

Freshdocs should not optimize for more context. It optimizes for less wrong context.

Done means:

- the current version is visible
- the checked date is visible
- sources are official or user-registered
- stale and missing docs are obvious
- the context block is small enough to inspect
- the agent can continue without guessing
