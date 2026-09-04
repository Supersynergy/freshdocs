#!/usr/bin/env python3
"""Run the knowledge-cutoff probe against OpenRouter models and record the results.

Usage:
    OPENROUTER_API_KEY=... python tools/cutoff_bench.py [--free] [--models a,b,c] [--out FILE]

Only ``:free`` models are used unless ``--models`` names others explicitly, so the
default run costs nothing. Results are appended to a JSON database that
``freshdocs models --import`` reads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import random
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import freshdocs.bench as bench  # noqa: E402
import freshdocs.core as core  # noqa: E402

OR_BASE = "https://openrouter.ai/api/v1"


def keys() -> list[str]:
    raw = os.environ.get("OPENROUTER_API_KEYS") or os.environ.get("OPENROUTER_API_KEY", "")
    found = [k.strip() for k in raw.split(",") if k.strip()]
    if not found:
        sys.exit("set OPENROUTER_API_KEY (comma-separate several to rotate)")
    return found


def free_models(key: str) -> list[str]:
    req = urllib.request.Request(f"{OR_BASE}/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)["data"]
    return sorted(m["id"] for m in data if m["id"].endswith(":free"))


def ask_factory(keyring: list[str]):
    def ask(model: str, prompt: str) -> str:
        last = ""
        for attempt in range(5):
            key = random.choice(keyring)
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                # Reasoning models spend their budget thinking before they answer; a
                # tight cap leaves content empty and looks like a refusal.
                "max_tokens": 4000,
                "temperature": 0,
                # The probe wants recall, not deliberation. A model that reasons for
                # thousands of tokens about whether 18.2.3 exists never answers.
                "reasoning": {"effort": "low", "exclude": True},
            }).encode()
            req = urllib.request.Request(
                f"{OR_BASE}/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/Supersynergy/freshdocs",
                    "X-Title": "freshdocs cutoff bench",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    raw = r.read().decode(errors="replace")
                i = raw.find("{")
                d = json.loads(raw[i:])
                if "choices" in d:
                    msg = d["choices"][0]["message"]
                    content = msg.get("content")
                    if content:
                        return content
                    # Some providers leave content empty and put the answer in the
                    # reasoning trace; a JSON object in there is still an answer.
                    reasoning = msg.get("reasoning") or ""
                    if "{" in reasoning and "}" in reasoning:
                        return reasoning
                    last = f"empty content (finish={d['choices'][0].get('finish_reason')})"
                    continue
                last = str(d.get("error", d))[:160]
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code in (429, 502, 503):
                    time.sleep(3 + attempt * 4 + random.random() * 3)
                    continue
                break
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {e}"
                time.sleep(2 + attempt * 2)
        raise RuntimeError(last or "no response")

    return ask


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--free", action="store_true", help="probe every :free model")
    ap.add_argument("--models", help="comma-separated model ids")
    ap.add_argument("--out", default="data/model_cutoffs.json")
    args = ap.parse_args()

    keyring = keys()
    targets = [m.strip() for m in (args.models or "").split(",") if m.strip()]
    if args.free or not targets:
        targets = sorted(set(targets) | set(free_models(keyring[0])))

    reg = core.ensure_registry()["libs"]
    dates = {lib: core.cached_release_dates(lib, reg[lib]) for lib in bench.PROBE_PANEL}
    missing = [lib for lib, d in dates.items() if not d]
    if missing:
        print(f"warning: no release dates for {missing}; they will count as unverifiable", file=sys.stderr)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    db = json.loads(out.read_text()) if out.exists() else {"probed": {}, "panel": list(bench.PROBE_PANEL)}
    ask = ask_factory(keyring)

    for model in targets:
        print(f"== {model}", flush=True)
        try:
            est = bench.run_probe(model, ask, dates)
        except Exception as e:  # noqa: BLE001
            print(f"   failed: {e}", flush=True)
            db["probed"][model] = {"model": model, "cutoff": None, "error": str(e)[:200], "probed_at": dt.date.today().isoformat()}
            out.write_text(json.dumps(db, indent=1))
            continue
        rec = est.as_dict()
        rec["probed_at"] = dt.date.today().isoformat()
        db["probed"][model] = rec
        out.write_text(json.dumps(db, indent=1))
        print(f"   cutoff {est.cutoff or 'undetermined'}  verified {est.verified}  hallucinated {est.hallucinated}", flush=True)
        time.sleep(1.5)
    print("BENCH DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
