# Freshdocs Launch Lens

Public positioning plan for the first Freshdocs launch.

## Core Finding

The strongest wedge is not "more context". Developers want fewer wrong AI edits, less review pain, and a fast first win.

Freshdocs should say:

```text
Stop AI coding agents from using stale docs.
```

## Goal

In 72 hours, get 10 qualified developers to run:

```sh
freshdocs context "what I am about to implement" --project . --sync-stale
```

Success means at least 3 public signals: star, issue, reply, fork, install proof, or demo mention from someone outside the project.

## Buyers And Users

| Role | Wants | Fear | Proof needed |
|---|---|---|---|
| Developer | Correct API names, fast copy-paste setup | Looking slow because the agent wrote fake code | 2-minute demo in a real repo |
| Tech lead | Reviewable AI output | Hidden stale context entering production | Version/date/source visible in output |
| Agent builder | Small local tool surface | Hosted dependency, privacy risk, fragile integration | CLI plus MCP, no runtime dependencies |

## What People Will Not Understand First

- `ghmax`: most users do not have it; frame it as optional.
- Top-300 languages: impressive but too abstract for the first viewport.
- `SQLite FTS`: explain as local full-text search.
- `MCP`: define once as Model Context Protocol.
- Context7 comparison: useful for informed buyers, not the core story.

## What Not To Build Yet

- hosted Freshdocs cloud
- user accounts
- broad dashboards
- notification loops
- more agent memory features before install proof
- viral badges before real external usage

## Viral Angle

The shareable story is a before/after:

1. Agent writes code against an old API.
2. Freshdocs injects version-pinned docs with checked date.
3. The same prompt now uses the current API.

Ship that as:

- one animated terminal GIF
- one "Show HN" post
- one Reddit post in a project-sharing subreddit
- one short post for agent-builder communities

Source prompts used for this launch lens:

- https://github.com/readme-SVG/repo-promotion-guide
- https://sderosiaux.github.io/developer-marketing-guides/guide-02-hacker-news-product-hunt.html

## 72h-Test

Post one real stale-docs demo with a tiny install command.

Measure:

- 10 installs or context runs
- 3 external public signals
- 1 issue or comment naming a missing library/source

## Kill Rule

If the demo gets views but no installs or replies, the problem is unclear positioning.

Pivot from "local docs context" to:

```text
A pre-flight check that stops AI agents from coding against old docs.
```
