# Contributing

Freshdocs is small by design. Every change should make agent context more current, smaller, easier to trust, or easier to integrate.

## Development

```sh
uv venv
uv pip install -e .
python -m unittest discover -s tests
freshdocs doctor
```

Run the full local gate before opening a pull request:

```sh
just ci
```

## Change Rules

- Keep dependencies at zero unless a dependency removes meaningful correctness risk.
- Prefer official docs sources: registry metadata, GitHub repos, release notes, changelogs, and `llms.txt`.
- Keep context packs compact and source-visible.
- Add tests for parsing, search, caching, or command behavior changes.
- Do not add hosted-service assumptions to the default path.

## Adding A Default Library

Add it to `src/freshdocs/default_registry.json` with:

- stable key name
- official GitHub `owner/repo`
- ecosystem: `npm`, `cargo`, `pypi`, or `gh`
- package name when it differs from the key
- `llms.txt` URL when the project publishes one

Then test:

```sh
freshdocs sync --lib <name>
freshdocs context "basic usage" --lib <name>
```
