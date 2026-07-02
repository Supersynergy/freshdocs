# freshdocs

Local, version-pinned documentation context for coding agents.

Freshdocs gives agents the thing developers actually want: **current API facts at the moment of use, with low friction and no cloud dependency**.

It fetches official docs from GitHub, npm, crates.io, PyPI, `llms.txt`, README, and changelog sources, pins the resolved package version, indexes the content locally, and returns compact context packs for Claude Code, Codex, Cursor, OpenCode, ggcoder, or any MCP client.

## Why Not Just Context7?

Context7 is useful: it pulls fresh, version-specific docs into prompts via CLI or MCP. Freshdocs is built for a different pain point:

| Need | Context7 | freshdocs |
|---|---|---|
| Fresh public docs | yes | yes |
| Version pin from real package registry | yes | yes |
| Local offline cache after sync | limited by service/client | yes |
| Private/internal docs | enterprise/cloud path | local-first by default |
| Repo dependency detection | agent/client dependent | built in |
| Changelog-aware context | varies by library | first-class |
| No account, no network at answer time | no | yes after sync |
| Agent-agnostic CLI + MCP | yes | yes |
| Synapse/export path | no | optional |

The product thesis: agents fail when they confidently use stale APIs. Humans do not want another docs search box. They want to feel safe shipping code because the agent is grounded in the current toolchain.

## First Win

```sh
uv tool install git+https://github.com/Supersynergy/freshdocs
freshdocs init
freshdocs sync --lib axum --lib tokio
freshdocs context "websocket server with shared state" --lib axum --lib tokio
```

Output is an agent-ready context block:

```text
FRESHDOCS CONTEXT
query: websocket server with shared state
libraries: axum, tokio

[1] axum 0.8.9 checked 2026-07-02 - ...
...
```

## What People Want From Agents

People do not want agents to "know everything." They want:

- less uncertainty: "Is this API still real?"
- more control: local cache, visible versions, explicit sources
- faster progress: no tab-switching across docs
- protected self-image: fewer embarrassing build breaks from hallucinated APIs
- memory: the agent remembers the stack and the exact versions in the repo
- reversibility: docs are local files and SQLite, exportable, inspectable

Freshdocs is designed around that. It is not an infinite context firehose. It gives the agent the smallest useful documentation pack for the current job.

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
freshdocs export-synapse
freshdocs doctor
```

## Agent Integration

### Codex / Claude Code / Shell

Use before code generation when the prompt includes `latest`, `current`, `API`, `deprecated`, `Rust`, `JS`, `npm`, `cargo`, or framework names:

```sh
freshdocs context "$USER_TASK" --project . --sync-stale
```

Paste or inject the returned block above the coding task.

### MCP

Run:

```sh
freshdocs mcp
```

Tools exposed:

- `freshdocs_context`
- `freshdocs_search`
- `freshdocs_sync`
- `freshdocs_detect`
- `freshdocs_sources`

Example MCP server config:

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

## Better-Than-Context7 Bet

Freshdocs can be better for serious agent work because it is:

1. **Local-first:** once synced, answers do not depend on a hosted service.
2. **Repo-aware:** it detects `package.json`, `Cargo.toml`, and `pyproject.toml`.
3. **Changelog-aware:** recent breaking changes are indexed beside README docs.
4. **Version-visible:** every snippet carries library, version, and check date.
5. **Agent-neutral:** CLI output works anywhere; MCP works where native tools exist.
6. **Private by default:** internal registries and private repos can be added without sending code to a public docs service.
7. **Composable:** export to Synapse, pipe into prompts, or serve over MCP.

## Language Sources

Freshdocs also ships a source planner for broad agent research:

```sh
freshdocs sources --top-languages 300 --live --format markdown > freshdocs-sources.md
freshdocs sources --top-languages 300 --format jsonl > freshdocs-sources.jsonl
```

It combines GitHub Linguist, GitHut, GitStars via `ghmax`, Awesome-list discovery, registry URLs, and GitHub topic/search commands. The output is not a static "best tools" opinion list. It is a repeatable harvest map: language -> registries -> top repos -> recent repos -> GitStars velocity -> awesome lists -> tool queries.

## Supported Sources

- npm packages
- crates.io crates
- PyPI packages
- GitHub releases/tags
- GitHub raw `README.md` and `CHANGELOG.md`
- `llms.txt`
- monorepo subdirectories via `--path`

## Development

```sh
git clone https://github.com/Supersynergy/freshdocs
cd freshdocs
uv venv
uv pip install -e .
python -m unittest discover -s tests
freshdocs doctor
```

Release check:

```sh
just ci
```

## Design Contract

Freshdocs should not optimize for "more context." It optimizes for **less wrong context**.

Done means:

- current version is visible
- source is official or user-registered
- stale state is visible
- context block is compact enough to read
- agent can continue without guessing
