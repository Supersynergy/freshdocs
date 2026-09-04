# Freshdocs Agent Contract

Freshdocs exists to keep coding agents from using stale API facts with confidence.

Use it when a task mentions current APIs, package versions, framework behavior, migrations, deprecations, or generated code that depends on third-party libraries.

Use `freshdocs sources` when the task is discovery-oriented: finding current language ecosystems, tools, repos, awesome lists, package registries, or GitStars/ghmax harvest commands.

## Before Code Changes

Run:

```sh
freshdocs analyze --project .
freshdocs context "$USER_TASK" --project . --sync-stale
```

Use the returned block as narrow context. Do not paste broad docs when the task only needs one library or one API family.

## Exact-Library Routing

When the user names libraries directly, pass them explicitly:

```sh
freshdocs context "cookie middleware in hono" --lib hono --limit 4
freshdocs context "axum websocket shared state" --lib axum --lib tokio --limit 6
freshdocs sources --top-languages 300 --format jsonl
```

## Staleness Rule

If a relevant library has no cached docs or Freshdocs marks its content stale, sync the exact project version before relying on the answer:

```sh
freshdocs sync --project .
```

Freshness is adaptive: preview versions refresh daily, npm/GitHub sources every 3 days, and stable Python/Rust packages every 7 days unless the registry overrides the window. Network calls belong in sync. Prompt-time context comes from the local cache.

## Done Rule

An agent may claim a docs-grounded implementation only when:

- the relevant docs pack was generated for the task
- snippets include project version, content-fetch date, source URL, and ref status
- `branch-fallback` is not presented as an exact version tag
- `docs-commit <sha>` is presented as current documentation prose, not as the library's own version tag
- generated code passes the repo's real tests
- missing docs are stated instead of guessed

## Gap Rule

Freshdocs detects your model from hook/MCP metadata, provider model environment, or a
known agent's `--model` argument. Do not repeat a model id on every call:

```sh
freshdocs models --probe                  # answer once, honestly, from memory
freshdocs models --record '<your JSON answer>'
freshdocs context "$USER_TASK" --project . --sync-stale
```

For MCP, call `freshdocs_identity` first. If the host exposed the model and a measured
profile exists, proceed without a model argument. If an older host omitted identity,
include your exact model id on one `freshdocs_probe` or `freshdocs_context` call; the
server retains it for the session.

Answer the probe with your best recollection. Do not deflate it to seem safe: an answer
that is a year too conservative wastes context on every later prompt, while an invented
version is rejected by the registry. If identity or a trustworthy profile is missing,
Freshdocs loads every relevant library in full. This is intentionally safe, not cheap.

The pack then states a verdict per library. Read it as an instruction:

- `training gap` and `pinned behind training`: you do not reliably know this API. Use the snippets, not your memory.
- `covered by training`: your memory and the project agree. The short confirmation is deliberate; do not ask for more.
- `unverified`: coverage could not be established, so the full pack was loaded. Treat it as a gap.

Never infer that a missing verdict means a library is safe to answer from memory.

## Miss Rule

When a context pack starts with `RESULT: no matching documentation`, the local cache cannot answer the question. Rewording the query cannot change that.

Run the `FIX` command shown in the block once. If the miss repeats, state that the API could not be verified against current docs and continue without inventing one.

## Do Not

- Do not use Freshdocs as an infinite context dump.
- Do not treat README snippets as stronger than local tests.
- Do not hide stale or missing docs.
- Do not add new default libraries without official source URLs.
- Do not retry reworded queries after a reported miss; close the cache gap instead.
- Do not present a `live-unversioned` or `docs-commit` page as if it were pinned to the project version.
