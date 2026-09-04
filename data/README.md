# Measured model cutoffs

`model_cutoffs.json` is the database behind `freshdocs models --import`. Every entry is
the result of the same probe: ask the model, from memory, for the newest released
version it knows of each of 20 libraries, then check every answer against the package
registry. The cutoff is the median publication date of the verified answers.

Nothing in this file is copied from a vendor page.

## Results, 2026-09-04

| Model | Measured cutoff | Verified | Hallucinated | Notes |
|---|---|---|---|---|
| claude-fable-5-1 | 2025-06-11 | 20/20 | 0 | self-probe, main session |
| claude-fable-5-1 (subagent, recall prompt) | 2025-05-16 | 20/20 | 0 | fresh context |
| claude-fable-5-1 (subagent, strict prompt) | 2024-05-02 | 20/20 | 0 | same model, see below |
| minimax/minimax-m3 | 2024-11-27 | 20/20 | 0 | |
| dots-studio/dots-3-note-preview | 2024-09-09 | 19/20 | 1 | |
| inclusionai/ling-3.0-flash-fin | 2024-07-01 | 18/20 | 2 | |
| google/gemma-4-31b-it | 2024-06-29 | 20/20 | 0 | |
| nvidia/nemotron-3.5-lightning | 2024-05-30 | 19/20 | 1 | |
| nvidia/nemotron-3-ultra-550b-a55b | 2024-05-06 | 20/20 | 0 | |
| nvidia/nemotron-3-super-120b-a12b | 2024-04-11 | 17/20 | 3 | |
| liquid/lfm-2.5-2.6b | 2024-03-16 | 16/20 | 4 | weakest recall |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning | 2024-02-20 | 18/20 | 2 | |
| poolside/laguna-s-2.1 | 2023-12-19 | 20/20 | 0 | |
| google/gemma-4-26b-a4b-it | 2023-12-17 | 20/20 | 0 | |
| poolside/laguna-xs-2.1 | 2023-11-21 | 20/20 | 0 | |
| claude-haiku-4-5-20251001 | 2023-10-07 | 20/20 | 0 | subagent, strict prompt |

Not measurable: `cohere/north-mini-code` and `minimax/minimax-m2.7` reason for the full
token budget without answering; `thinkingmachines/inkling*` is gated (HTTP 403);
`z-ai/glm-5.2` and `google/gemma-4-26b` hit provider rate limits on the second pass.

## What the numbers mean

**Every measured cutoff is well behind the model's release date.** Models shipped in
mid-2026 recall library versions from late 2023 to mid-2025. For a coding agent that is
the number that matters: a library released in 2026 is a training gap for all of them,
and `freshdocs context --model` loads its documentation while skipping libraries the
model demonstrably knows.

**The median is deliberately conservative.** Per-library dates for the same model span
up to eighteen months (claude-fable-5-1: ratatui 2024-10-21, biome 2025-06-27). The
median keeps one lucky late answer from suppressing documentation; the per-library dates
are stored and used wherever they exist, so a well-known library is not penalised for a
poorly-known one.

**Prompt wording moved the same model by a year.** The first probe said "a version you
are unsure about is worse than an older one you are sure of". The second asked for best
recollection and forbade invention. Same model, same registry check:

| Model | Strict prompt | Recall prompt | Hallucinations |
|---|---|---|---|
| claude-fable-5-1 (subagent) | 2024-05-02 | 2025-05-16 | 0 → 0 |
| minimax/minimax-m3 | 2024-03-08 | 2024-11-27 | 0 → 0 |
| dots-3-note-preview | 2024-05-30 | 2024-09-09 | 1 → 1 |
| nemotron-3-ultra | 2024-07-31 | 2024-05-06 | 1 → 0 |

The strict prompt made models discard real knowledge without making them more accurate.
The recall prompt is now the default; the registry check, not the wording, catches
invention.

**Context changes recall.** The same model id answered 2025-06-11 in a long working
session and 2025-05-16 as a fresh subagent. A measured cutoff describes a model in a
context, which is one more reason to keep the safety margin and let `--cutoff` override.

## Reproduce

```sh
OPENROUTER_API_KEY=... python tools/cutoff_bench.py --free      # all :free models, $0
freshdocs models --import data/model_cutoffs.json
freshdocs models --probe                                          # measure yourself
```
