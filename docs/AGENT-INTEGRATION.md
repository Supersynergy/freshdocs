# Agent Integration

Agents do not need more memory by default. They need the right current fact at the point of action.

Freshdocs gives agents a small, local, version-visible docs block. This fits Claude Code, Codex, Cursor, OpenCode, ggcoder, and any client that can run shell commands or MCP tools.

## Shell Pattern

```sh
freshdocs context "$USER_TASK" --project . --sync-stale
```

Use this before editing when the task depends on third-party APIs.

## MCP Pattern

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

Use `freshdocs_context` for task context, `freshdocs_search` for narrow lookup, `freshdocs_sync` for refresh, and `freshdocs_detect` for repo dependency detection.

## Prompt Injection Pattern

Place the Freshdocs block above the implementation request:

```text
<freshdocs>
FRESHDOCS CONTEXT
...
</freshdocs>

Task:
Implement ...
```

Tell the agent to prefer the Freshdocs block for API shapes, names, and version-specific behavior.

## Why This Works

People want agents that feel fast without making them feel exposed.

Freshdocs supports that will:

- certainty: current checked date is visible
- control: all docs are local after sync
- speed: no manual docs search
- privacy: private registries can stay local
- trust: missing docs become explicit instead of guessed
