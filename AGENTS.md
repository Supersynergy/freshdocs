# Freshdocs Agent Contract

Freshdocs exists to keep coding agents from using stale API facts with confidence.

Use it when a task mentions current APIs, package versions, framework behavior, migrations, deprecations, or generated code that depends on third-party libraries.

Use `freshdocs sources` when the task is discovery-oriented: finding current language ecosystems, tools, repos, awesome lists, package registries, or GitStars/ghmax harvest commands.

## Before Code Changes

Run:

```sh
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

If a relevant library has no cached docs or was checked more than 14 days ago, sync it before relying on the answer:

```sh
freshdocs sync --lib <name>
```

Network calls belong in sync. Prompt-time context should usually come from the local cache.

## Done Rule

An agent may claim a docs-grounded implementation only when:

- the relevant docs pack was generated for the task
- snippets include library version and checked date
- generated code passes the repo's real tests
- missing docs are stated instead of guessed

## Do Not

- Do not use Freshdocs as an infinite context dump.
- Do not treat README snippets as stronger than local tests.
- Do not hide stale or missing docs.
- Do not add new default libraries without official source URLs.
