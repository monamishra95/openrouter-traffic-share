#!/usr/bin/env python3
"""Fetch every data feed for the Share of Traffic dashboard.

Writes one JSON file per feed under data/, each wrapping the raw API response
alongside the metadata needed to cite it. Raw responses are stored verbatim so
that every rendered figure can be traced back to what the API actually returned
— the computation layer never mutates source data in place.

Usage:
    export OPENROUTER_API_KEY=sk-or-v1-...
    python scripts/fetch_all.py                 # all feeds, 90-day window
    python scripts/fetch_all.py --days 30       # narrower window
    python scripts/fetch_all.py --only tokens   # a single feed

Requires: requests. No other dependencies.

All OpenRouter data is licensed CC BY 4.0. Each output file carries the
citation string the API specifies, built from meta.as_of.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests is required:  pip install requests")

BASE = "https://openrouter.ai/api/v1"
HF_BASE = "https://huggingface.co/api"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Confirmed live from openrouter.ai/apps on 2026-08-30.
APP_CATEGORIES = ["coding", "productivity", "creative", "entertainment"]

CITATION = "Source: OpenRouter (openrouter.ai/rankings), as of {as_of}. Licensed under CC BY 4.0."


def key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        sys.exit(
            "OPENROUTER_API_KEY is not set.\n"
            "  Windows:  set OPENROUTER_API_KEY=sk-or-v1-...\n"
            "  bash:     export OPENROUTER_API_KEY=sk-or-v1-...\n"
            "Never commit the key. It belongs in GitHub Actions secrets and Vercel env only."
        )
    return k


def get(path: str, params: dict | None = None, base: str = BASE, auth: bool = True) -> dict:
    """GET with retry. Rate limits are 30/min and 500/day, so we stay well under."""
    headers = {"Authorization": f"Bearer {key()}"} if auth else {}
    url = f"{base}{path}"
    for attempt in range(4):
        r = requests.get(url, headers=headers, params=params, timeout=45)
        if r.status_code == 429:
            wait = 2 ** attempt * 5
            print(f"    rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 401:
            sys.exit("401 Unauthorized — the API key was rejected. Check it is current and not rotated.")
        r.raise_for_status()
        return r.json()
    sys.exit(f"Gave up after repeated rate limits on {path}")


def write(name: str, payload: dict, source_url: str, cadence: str, notes: str = "") -> None:
    """Write a feed file with provenance attached to the raw response."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = payload
    # `data` is a list on some endpoints (models, rankings-daily) and a dict on
    # others (classifications). Calling .get() on the list raised AttributeError
    # and killed the models feed on every run. Check the type rather than
    # relying on `or` short-circuiting, which only masked it where meta existed.
    meta = raw.get("meta")
    data = raw.get("data")
    as_of = ""
    if isinstance(meta, dict):
        as_of = meta.get("as_of") or ""
    if not as_of and isinstance(data, dict):
        as_of = data.get("as_of") or ""
    if not as_of:
        as_of = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = json.dumps(raw, sort_keys=True)
    doc = {
        "_provenance": {
            "source_url": source_url,
            "citation": CITATION.format(as_of=as_of) if "openrouter" in source_url else f"Source: {source_url}",
            "as_of": as_of,
            "cadence": cadence,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "content_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
            "notes": notes,
        },
        "raw": raw,
    }
    path = DATA_DIR / name
    # Preserve the previous hash so the workflow can tell a genuine change from a
    # re-fetch of identical data — fetched_at always differs, content_hash doesn't.
    prev_hash = None
    if path.exists():
        try:
            prev_hash = json.loads(path.read_text())["_provenance"]["content_hash"]
        except Exception:
            pass
    path.write_text(json.dumps(doc, indent=2))
    changed = prev_hash != doc["_provenance"]["content_hash"]
    print(f"  wrote {name}  hash={doc['_provenance']['content_hash']}  {'CHANGED' if changed else 'unchanged'}")


def fetch_tokens(days: int) -> None:
    end = date.today() - timedelta(days=1)          # most recent complete UTC day
    start = end - timedelta(days=days - 1)
    print(f"  window {start} .. {end}")
    payload = get("/datasets/rankings-daily", {"start_date": str(start), "end_date": str(end)})
    rows = payload.get("data", [])
    print(f"  {len(rows)} rows")
    write("tokens-daily.json", payload, "https://openrouter.ai/rankings", "daily",
          f"Top 50 models per day plus aggregated 'other' row. Window {start}..{end}.")


def fetch_classifications() -> None:
    payload = get("/classifications/task", {"window": "7d"})
    d = payload.get("data", {})
    print(f"  {len(d.get('classifications', []))} classifications, "
          f"{len(d.get('macro_categories', []))} macro-categories")
    write("tasks.json", payload, "https://openrouter.ai/rankings", "daily (7-day trailing window)",
          "Sampled data: relative shares only, absolute volumes not exposed.")


def fetch_apps(days: int) -> None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    out = {"categories": {}, "meta": None}
    for cat in APP_CATEGORIES:
        payload = get("/datasets/app-rankings", {
            "sort": "popular", "category": cat, "limit": 50,
            "start_date": str(start), "end_date": str(end),
        })
        out["categories"][cat] = payload.get("data", [])
        out["meta"] = payload.get("meta")
        print(f"  {cat}: {len(payload.get('data', []))} apps")
        time.sleep(2.5)   # stay comfortably inside 30/min
    write("apps.json", out, "https://openrouter.ai/apps", "daily",
          f"Top 50 apps per category, window {start}..{end}. Categories confirmed live 2026-08-30.")


def fetch_models() -> None:
    payload = get("/models")
    models = payload.get("data", [])
    print(f"  {len(models)} models in registry")
    write("model-registry.json", payload, "https://openrouter.ai/models", "daily",
          "Model metadata and list pricing. Basis for provenance and the derived spend estimate.")


def fetch_hf_licences() -> None:
    """Licence metadata for open-weight classification.

    Only models whose permaslug plausibly maps to a HuggingFace repo are looked
    up. Misses are recorded rather than guessed — an unknown licence must stay
    unknown, never default to proprietary.
    """
    reg_path = DATA_DIR / "model-registry.json"
    if not reg_path.exists():
        print("  model-registry.json not found — run the models feed first. Skipping.")
        return
    models = json.loads(reg_path.read_text())["raw"].get("data", [])
    results, misses = {}, []
    for m in models:
        # Key on canonical_slug — that is what rankings-daily returns. And take
        # the HuggingFace repo from hugging_face_id rather than guessing it from
        # the model id; guessing produces 401s on repos whose names don't match
        # the OpenRouter slug. Both learned from live data, 2026-08-30.
        mid = m.get("canonical_slug") or m.get("id", "")
        slug = m.get("hugging_face_id")
        if not mid or not slug:
            if mid:
                misses.append(mid)
            continue
        try:
            r = requests.get(f"{HF_BASE}/models/{slug}", timeout=20)
            if r.status_code == 200:
                info = r.json()
                tags = info.get("tags", [])
                lic = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
                results[mid] = {
                    "hf_repo": slug,
                    "license": lic,
                    "downloads": info.get("downloads"),
                    "likes": info.get("likes"),
                    "source": f"https://huggingface.co/{slug}",
                }
            else:
                misses.append(mid)
        except requests.RequestException:
            misses.append(mid)
        time.sleep(0.15)
    print(f"  matched {len(results)} models on HuggingFace, {len(misses)} without a public repo")
    write("open-weights.json",
          {"data": results, "unmatched": misses, "meta": {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}},
          "https://huggingface.co", "daily",
          "Licence and download metadata. Models without a public HF repo are listed as unmatched, not assumed proprietary.")


FEEDS = {
    "tokens": lambda a: fetch_tokens(a.days),
    "tasks": lambda a: fetch_classifications(),
    "apps": lambda a: fetch_apps(a.days),
    "models": lambda a: fetch_models(),
    "licences": lambda a: fetch_hf_licences(),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Share of Traffic data feeds.")
    ap.add_argument("--days", type=int, default=90, help="trailing window in days (default 90)")
    ap.add_argument("--only", choices=list(FEEDS), help="fetch a single feed")
    args = ap.parse_args()

    names = [args.only] if args.only else list(FEEDS)
    # models before licences: the licence lookup reads the registry.
    names.sort(key=lambda n: 0 if n == "models" else 1 if n != "licences" else 2)

    # The licence feed makes ~400 HuggingFace requests and is the most likely to
    # rate-limit or time out. A failure there must not discard the core feeds that
    # already succeeded, so it degrades to a warning; everything else is fatal.
    OPTIONAL = {"licences"}
    failed = []
    for name in names:
        print(f"\n[{name}]")
        try:
            FEEDS[name](args)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            if name in OPTIONAL:
                print("  (optional feed — continuing; open-weight view will be incomplete)")
                failed.append(name)
            else:
                return 1
    if failed:
        print(f"\nDone with warnings. Optional feed(s) failed: {', '.join(failed)}")
        return 0
    print("\nDone. Data written to data/ — review before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
