<p align="center">
  <img src="https://raw.githubusercontent.com/Supersynergy/freshdocs/main/docs/assets/social-preview.jpg" alt="freshdocs — stop AI coding agents from using stale docs" width="100%">
</p>

# freshdocs

> Local docs pre-flight check for coding agents — exact project versions, visible source refs, explicit misses, and no hosted service required at answer time.

[![Release](https://img.shields.io/github/v/release/Supersynergy/freshdocs)](https://github.com/Supersynergy/freshdocs/releases)
[![License](https://img.shields.io/github/license/Supersynergy/freshdocs)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/Supersynergy/freshdocs/ci.yml)](https://github.com/Supersynergy/freshdocs/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](pyproject.toml)

[Demo](#demo) · [Agent integration](docs/AGENT-INTEGRATION.md) · [Sources](docs/SOURCES.md) · [Releases](https://github.com/Supersynergy/freshdocs/releases) · [Issues](https://github.com/Supersynergy/freshdocs/issues)

> **Local-first by default:** `context`, `search`, `detect`, `status`, and `doctor` never edit your project. `sync` writes only to the Freshdocs cache. If docs are missing or stale, Freshdocs says so instead of hiding the uncertainty.

## Demo

```sh
uv tool install git+https://github.com/Supersynergy/freshdocs
freshdocs init
freshdocs analyze --project .
freshdocs sync --lib hono
freshdocs context "middleware auth cookies" --lib hono --limit 3
```

![freshdocs demo](https://raw.githubusercontent.com/Supersynergy/freshdocs/main/docs/assets/demo.gif)

You get a small, source-visible block:

```text
FRESHDOCS CONTEXT
query: middleware auth cookies
libraries: hono

[1] hono 4.12.27 fetched 2026-07-02 exact-ref - Features
source: https://raw.githubusercontent.com/honojs/hono/v4.12.27/README.md
...
```

## Why This Exists

Agents are fast until they confidently use an API that no longer exists.

The failure is expensive because the code looks plausible. The human only discovers the stale context later, inside build errors, review comments, production bugs, or embarrassing rework.

Freshdocs attacks that exact failure:

- exact versions from project lockfiles
- prose from the repository's `docs/` tree, not just the README
- `llms.txt` resolved into the pages it links to, instead of stored as a link list
- navigation-heavy chunks ranked below real prose, so a query returns answers rather than a table of contents
- local cache after sync
- visible content-fetch date, source URL, and Git ref
- compact prompt-ready output
- CLI and Model Context Protocol (MCP) interface
- optional source map for language, tool, and repo discovery

### Answers, Not Tables Of Contents

A README says what a library is; the `docs/` tree says how to use it. Indexing only the README is why a question about auth middleware can come back with a feature list. Freshdocs fetches the documentation tree, follows `llms.txt` links to their source pages, and ranks any chunk that is mostly links below real prose.

Libraries whose prose lives in a separate website repository declare it once:

```sh
freshdocs add hono --gh honojs/hono --eco npm --docs-gh honojs/website
```

### Your Version, Not The Newest One

`status` reports the newest version Freshdocs has checked. `context` reports the version
your project actually installs, and serves documentation fetched at that release tag.

So a project pinned to `ruff 0.14.14` gets `0.14.14` docs even while the cache also holds
`0.16.6`. That difference is the point: an agent writing against your lockfile needs the
API you have, not the API upstream shipped last week.

### Load Only What The Model Cannot Know

A model that was trained on `hono 4.13.5` does not need its documentation pasted back.
The expensive case is the opposite one, and there are two of them.

Tell Freshdocs which model is reading, and it compares each installed version's
publication date against that model's training cutoff:

```sh
freshdocs gap --project . --model claude-sonnet-4-5
```

```text
model: claude-sonnet-4-5 (matched claude-sonnet-4, cutoff 2025-01-01)
  LOAD  hono               4.13.5   training gap (released 2026-08-26, after cutoff 2025-01-01)
  skip  zod                3.22.4   covered by training (released 2023-08-01, cutoff 2025-01-01)
```

| Verdict | Meaning | Action |
|---|---|---|
| `ahead` | Released after the cutoff. The model cannot know it. | full context |
| `behind` | The project pins an older release than the model most likely learned, so it may write an API that exists upstream but not here. | full context |
| `covered` | The model's knowledge and the project agree. | one pointer: header and source URL, no prose |
| `unknown` | Any input is missing. | full context, with the reason |

Pass `--model` to `context` and the pack carries the same reasoning, spends its budget
on the gaps, and `--sync-stale` refetches only those libraries instead of all of them:

```sh
freshdocs context "bearer auth" --project . --model claude-sonnet-4-5 --sync-stale
export FRESHDOCS_MODEL=claude-sonnet-4-5   # or set it once
```

Measured on a four-library project with a probed model (`claude-fable-5-1`, see below):

| Situation | Hits | Approx. tokens |
|---|---|---|
| no `--model` | 8 | 2430 |
| one library is a gap, three are covered | 5 full + pointers | 1700 |
| every library is covered | 1 pointer | 240 |

The budget is split per library by verdict, so a library the model has never seen is
guaranteed its share and is listed first; a library that merely scores higher on the
query words cannot crowd it out.

#### Measure the cutoff instead of guessing it

A vendor's published cutoff is one month for the whole model. What matters is narrower
and measurable: for each library, which release is the newest the model can name
correctly? Freshdocs asks, checks every answer against the package registry, and
records the result.

```sh
freshdocs models --probe                 # prints the question; answer it from memory
freshdocs models --record <model-id> '<the JSON you produced>'
```

```text
model: claude-fable-5-1
cutoff: 2025-06-11  (median release date of 20 verified answers)
verified 20  hallucinated 0  unanswered 0
  ok  hono           4.7.11 released 2025-05-31, 452d behind 4.13.5
  ok  ratatui        0.29.0 released 2024-10-21, 606d behind 0.30.2
  ...
recorded: claude-fable-5-1 -> 2025-06-11 (20 libraries measured)
```

Two things make this better than a date from a web page. The cutoff is the **median**,
so one lucky late answer cannot pull it forward and suppress documentation the model
needs. And the **per-library dates are kept**: coverage is uneven, and a model that
knows polars to June may know ratatui only to the previous October. Gap detection uses
the per-library date wherever one was measured.

Precedence is `--cutoff` (your word) > measured probe > `models --set` > shipped table.
Measured beats manual because it is evidence about this model, not a number copied
from a vendor page. An MCP client does the same in two calls to `freshdocs_probe`.

`tools/cutoff_bench.py` runs the probe across OpenRouter models and writes a database
that `freshdocs models --import` reads. The shipped table remains as a last resort:

```sh
freshdocs models                              # measured, overrides, defaults
freshdocs models --set my-local-model 2025-06-01
```

**Every unknown fails safe.** An unrecognised model, an unpublished version, or an
offline registry all resolve to `unknown`, which loads the full pack and says why.
Nothing is ever skipped on a guess. `freshdocs doctor` re-proves that on every run.

### Keeping The Cache Honest

`freshdocs doctor` reports cached versions that an older indexer produced. Drop them:

```sh
freshdocs prune            # --dry-run to preview
```

Dropping is instant and safe: a pruned version is re-fetched with the current pipeline
as soon as a project pins to it. Use `freshdocs sync --outdated` instead when you want
those versions re-indexed up front.

### When Freshdocs Has Nothing

A miss is reported as a cache gap with the command that closes it, and it tells the agent not to retry reworded queries against a cache that cannot answer them:

```text
RESULT: no matching documentation in the local cache.
CAUSE: no cached chunk for hono matched this question.
This is a cache gap, not a bad query. Do not retry reworded queries.
FIX:
  1. freshdocs context "cookie auth" --project . --sync-stale
  2. if it still misses, the docs do not cover this API: say so instead of guessing
Until then, state that the API could not be verified against current docs.
```

## Quick Start

```sh
uv tool install git+https://github.com/Supersynergy/freshdocs
freshdocs init
freshdocs add hono --gh honojs/hono --eco npm --pkg hono
freshdocs analyze --project .
freshdocs context "middleware auth cookies" --project . --sync-stale --limit 3
```

Expected result: a compact `FRESHDOCS CONTEXT` block with library, exact project version, fetch date, source URL, Git ref status, title, and matching snippets.

## What You See

| Signal | Why it matters |
|---|---|
| Project version | Freshdocs reads the lockfile before deciding which version belongs in the prompt. |
| Fetch date | Reviewers see when the document content—not only the registry version—was fetched. |
| Ref status | `exact-ref` is the library's own version tag; `docs-commit <sha>` is a docs repository read at a fixed commit; `branch-fallback` and `live-unversioned` are explicit warnings. |
| Source label | Snippets point back to docs, changelog, `llms.txt`, or registry data. |
| Explicit miss | Empty cache and stale docs are visible instead of silently guessed. |

## Two-Minute Proof

Run this in any repo:

```sh
freshdocs detect --project .
freshdocs context "what I am about to implement" --project . --sync-stale
```

If Freshdocs detects relevant registered libraries, it can refresh stale docs and return only matching local snippets. If nothing is cached, it says so instead of inventing facts.

That is the trust contract: **missing docs are visible; stale docs are visible; exact and fallback sources are visibly different.**

## Terms In Plain English

| Term | Meaning |
|---|---|
| MCP | Model Context Protocol: a standard way for AI tools to call local tools. |
| `llms.txt` | A docs file some projects publish specifically for AI tools. |
| SQLite FTS | A local database with full-text search. No hosted service required. |
| Source map | A checklist of where an agent should look before claiming it knows a library or language. |

## Who It Is For

**Developers** use Freshdocs before asking an agent to write code against a framework, SDK, CLI, runtime, or library.

**Tech leads** use it to make agent output easier to review because every snippet carries library, version, fetch date, source URL, and ref status.

**Teams with private docs** use it because the default path is local files and SQLite, not a hosted service.

**Agent builders** use it as a tiny source tool: shell output when the client has no MCP, MCP tools when it does.

## Commands

```sh
freshdocs init
freshdocs add hono --gh honojs/hono --eco npm --pkg hono
freshdocs sync --lib hono
freshdocs sync --project .
freshdocs status
freshdocs detect --project .
freshdocs analyze --project .
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
- `freshdocs_analyze`: inspect languages, manifests, dependencies, and exact lockfile versions
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

1. `freshdocs analyze` detects languages, monorepo manifests, registered libraries, and exact lockfile versions.
2. `freshdocs sync --project .` prefers those installed versions. Latest registry versions are used only when no project version was requested.
3. Freshdocs tries the matching Git tag before any default-branch fallback and records the result honestly.
4. It fetches official docs from `llms.txt`, `README.md`, and `CHANGELOG.md` sources.
5. It chunks and indexes snippets in local SQLite FTS.
6. `freshdocs context` searches only the relevant cached version and prints a compact context block.
7. The agent receives current docs without a network call at answer time.

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

Freshdocs does not promise that every README is complete or correct, and it never treats retrieved text as agent instructions.

It does promise:

- HTTPS-only fetches
- local SQLite storage
- visible project/package version
- visible content-fetch date, source URL, and Git ref status
- exact-version filtering when a project lockfile resolves the dependency
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

- the project version is visible
- the content-fetch date and source URL are visible
- an unpinned branch fallback is labeled instead of presented as exact
- sources are official or user-registered
- stale and missing docs are obvious
- the context block is small enough to inspect
- the agent can continue without guessing
