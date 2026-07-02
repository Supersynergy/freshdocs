# Sources

Freshdocs has two source layers:

1. Documentation sources for `freshdocs sync`.
2. Discovery sources for `freshdocs sources`.

## Top-300 Language Coverage

Run:

```sh
freshdocs sources --top-languages 300 --live --format markdown
```

The command builds a language ecosystem harvest plan:

- language universe: GitHub Linguist
- activity ranking: GitHut stars, pushes, pull requests, issues
- fresh repo velocity: GitHub activity and optional local command hints
- repo/code discovery: GitHub topic pages plus optional GitHub-scale search tools
- curated lists: awesome-list search, compatible with local awesome-indexer data
- registry links: PyPI, npm, crates.io, Maven Central, NuGet, Packagist, RubyGems, Hex, Hackage, CRAN, Julia General, LuaRocks, CPAN, opam, Nimble, and others

Default offline mode uses an embedded 300-language seed. Live mode refreshes the rank/universe inputs before rendering.

You do not need `ghmax` or any private search tool to use Freshdocs. Some generated command recipes mention optional local tools when available; treat those as accelerators. The portable value is the source plan: language, registries, GitHub topics, curated lists, and exact search questions.

## Why This Is Better For Agents

Agents need a repeatable source contract, not one giant stale list.

For each language, Freshdocs emits:

- top-star repo command
- recently updated repo command
- repo velocity command or query
- awesome-list command
- GitHub topic URL
- registry URLs where known
- tool queries for compiler/runtime, package manager, language server, formatter, linter, test runner, build tool, docs generator, web framework, and agent tooling

That lets an agent gather fresh evidence for any language without guessing where to look.

## Example Without Extra Tools

```sh
freshdocs sources --top-languages 5
```

Then use the generated source plan for a language:

```sh
# Open the GitHub topic URL from the Freshdocs output.
open "https://github.com/topics/rust"

# Check the official registry.
open "https://crates.io"

# Search GitHub for current curated lists and tools.
open "https://github.com/search?q=awesome+rust&type=repositories"
open "https://github.com/search?q=rust+language+server&type=repositories"
```

## Optional Local Accelerators

If you have a GitHub-scale local search tool, Freshdocs also prints command hints such as:

```sh
ghmax --repos --lang "Rust" --sort stars --order desc --stars-min 100 -n 50 --format json
ghmax --gitstars 100 --gitstars-window 7d,30d --gitstars-lang "Rust" --gitstars-gems --gitstars-no-lake
ghmax --repos "awesome Rust" --topic awesome-list --sort stars --order desc -n 25 --format json
```
