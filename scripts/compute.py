#!/usr/bin/env python3
"""Turn raw API responses into the figures the dashboard renders.

Every number on the page comes from this module. It is deliberately separate
from the fetch layer and from the rendering layer, so the golden tests can
recompute shares from a fixed input and catch the case where the chart and the
arithmetic disagree.

Three rules are enforced here rather than left to the UI:

  1. Unattributed models are excluded from every denominator. Their volume is
     reported separately so a reader can see how much was set aside.
  2. Open-weight classification is rule-based and every model carries the
     evidence for its classification. Unknown stays unknown.
  3. The spend figure is derived, and carries its own assumptions with it.

Usage:
    python scripts/compute.py            # writes data/computed.json
    python scripts/compute.py --print    # also prints a summary
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# Providers that publish under an anonymous or stealth identity. Vendor and
# licence cannot be established, so their traffic is excluded from shares.
# Today this is dominated by "stealth" (Ox Alpha, ~20.7T weekly tokens as of
# 2026-08-29) — a fifth of visible traffic, which is precisely why it cannot be
# silently folded into a vendor total.
UNATTRIBUTED_PREFIXES = ("stealth/", "anonymous/", "cloaked/")
# OpenRouter also hosts cloaked models under its own namespace with alpha-animal
# codenames (ox-alpha, owl-alpha). The vendor string says "openrouter", but the
# actual model author is undisclosed, so these belong with the stealth traffic
# rather than credited to OpenRouter. Found on live data, 2026-08-30.
UNATTRIBUTED_PATTERNS = (
    re.compile(r"^openrouter/(ox|owl|otter|orca)-"),
)

# Licence identifiers treated as open-weight. Deliberately explicit: "open
# weights under a restrictive licence" is a real category and is classified
# separately rather than being quietly counted as open.
OPEN_LICENSES = {
    "apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause",
    "cc-by-4.0", "cc-by-sa-4.0", "gpl-3.0", "agpl-3.0", "lgpl-3.0",
    "mpl-2.0", "openrail", "bigscience-openrail-m",
}
RESTRICTED_OPEN_LICENSES = {
    "llama2", "llama3", "llama3.1", "llama3.2", "llama3.3", "llama4",
    "gemma", "deepseek", "qwen", "other",
}


def load(name):
    p = DATA / name
    if not p.exists():
        return None
    return json.loads(p.read_text())


def is_unattributed(permaslug: str) -> bool:
    s = permaslug.lower()
    return s.startswith(UNATTRIBUTED_PREFIXES) or any(p.match(s) for p in UNATTRIBUTED_PATTERNS)


def vendor_of(permaslug: str) -> str:
    return permaslug.split("/", 1)[0] if "/" in permaslug else permaslug


# ── token share ──────────────────────────────────────────────────────────────

def token_shares(tokens_doc):
    """Aggregate the daily rankings into vendor and model share over the window.

    The 'other' row is the API's aggregate of everything outside the daily top
    50. It is kept in the total (dropping it would inflate every share) but is
    never attributed to a vendor.
    """
    rows = tokens_doc["raw"]["data"]
    by_model = defaultdict(int)
    by_vendor = defaultdict(int)
    unattributed = 0
    other = 0
    dates = set()

    for r in rows:
        slug = r["model_permaslug"]
        n = int(r["total_tokens"])
        dates.add(r["date"])
        if slug == "other":
            other += n
            continue
        if is_unattributed(slug):
            unattributed += n
            continue
        by_model[slug] += n
        by_vendor[vendor_of(slug)] += n

    attributed = sum(by_model.values())
    denominator = attributed + other      # shares are over attributed + long tail
    total_incl_unattributed = denominator + unattributed

    return {
        "window": {"days": len(dates), "start": min(dates) if dates else None,
                   "end": max(dates) if dates else None},
        "totals": {
            "attributed_tokens": attributed,
            "other_tokens": other,
            "unattributed_tokens": unattributed,
            "denominator": denominator,
            "total_including_unattributed": total_incl_unattributed,
            "unattributed_pct_of_visible": pct(unattributed, total_incl_unattributed),
        },
        "by_vendor": ranked(by_vendor, denominator),
        "by_model": ranked(by_model, denominator)[:50],
        "exclusion_rule": (
            "Models published under an anonymous or stealth provider are excluded from all "
            "share denominators because vendor and licence cannot be established. Their volume "
            "is reported above so the effect is visible."
        ),
    }


def pct(part, whole):
    return round(100.0 * part / whole, 3) if whole else 0.0


def ranked(counter: dict, denominator: int):
    return [
        {"key": k, "tokens": v, "share_pct": pct(v, denominator)}
        for k, v in sorted(counter.items(), key=lambda kv: -kv[1])
    ]


# ── open-weight classification ───────────────────────────────────────────────

def classify_open_weight(model_id: str, licences_doc, registry_doc):
    """Return (classification, evidence). Unknown is a valid answer."""
    lic_data = (licences_doc or {}).get("raw", {}).get("data", {})
    entry = lic_data.get(model_id)
    if entry and entry.get("license"):
        lic = entry["license"].lower()
        if lic in OPEN_LICENSES:
            return "open", {"license": lic, "source": entry["source"]}
        if lic in RESTRICTED_OPEN_LICENSES:
            return "open-restricted", {"license": lic, "source": entry["source"]}
        return "unknown", {"license": lic, "source": entry["source"],
                           "note": "licence present but not in the classification table"}
    return "unknown", {"note": "no public HuggingFace repo matched; not assumed proprietary"}


def open_weight_share(shares, licences_doc, registry_doc):
    buckets = defaultdict(int)
    detail = []
    denom = shares["totals"]["denominator"]
    for row in shares["by_model"]:
        cls, evidence = classify_open_weight(row["key"], licences_doc, registry_doc)
        buckets[cls] += row["tokens"]
        detail.append({"model": row["key"], "tokens": row["tokens"],
                       "classification": cls, "evidence": evidence})
    return {
        "buckets": [{"classification": k, "tokens": v, "share_pct": pct(v, denom)}
                    for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])],
        "models": detail,
        "method": (
            "Licence taken from each model's HuggingFace repository. 'open' means a standard "
            "permissive or copyleft licence; 'open-restricted' means weights are published under "
            "a bespoke licence with use restrictions; 'unknown' means no public repo matched. "
            "Unknown is never collapsed into proprietary."
        ),
    }


# ── derived spend ────────────────────────────────────────────────────────────

def estimated_spend(shares, registry_doc):
    """Tokens x list price. Derived, and labelled as such everywhere it appears."""
    # Index on canonical_slug, NOT id. rankings-daily returns dated permaslugs
    # ("deepseek/deepseek-v4-flash-20260423") while /api/v1/models uses undated
    # ids ("deepseek/deepseek-v4-flash") — but every model carries a
    # canonical_slug that matches the permaslug exactly. Joining on id matched
    # 14 of 122 models and produced a completely wrong spend picture; joining on
    # canonical_slug covers 98.9% of token volume. Found on live data 2026-08-30.
    prices = {}
    for m in (registry_doc or {}).get("raw", {}).get("data", []):
        slug = m.get("canonical_slug")
        if not slug:
            continue
        p = m.get("pricing") or {}
        try:
            prompt = float(p.get("prompt", 0) or 0)
            completion = float(p.get("completion", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not (prompt or completion):
            continue
        entry = {"prompt": prompt, "completion": completion, "blended": (prompt + completion) / 2}
        # Prefer the plain entry over :batch / :free variants of the same slug.
        if slug not in prices or ":" not in m.get("id", ""):
            prices[slug] = entry

    rows, missing = [], []
    for r in shares["by_model"]:
        pr = prices.get(r["key"]) or prices.get(r["key"].split(":")[0])
        if not pr:
            missing.append(r["key"])
            continue
        # No rounding here. Rounding is a presentation concern, and rounding to
        # cents at computation time silently zeroes any figure below half a cent —
        # which is every per-model value at small volumes. The UI formats; this
        # layer keeps full precision. (Caught by tests/test_compute.py.)
        rows.append({"model": r["key"], "tokens": r["tokens"],
                     "blended_price_per_token": pr["blended"],
                     "estimated_usd": r["tokens"] * pr["blended"]})
    total = sum(x["estimated_usd"] for x in rows)
    for x in rows:
        x["share_pct"] = pct(x["estimated_usd"], total)
    rows.sort(key=lambda x: -x["estimated_usd"])

    by_vendor = defaultdict(float)
    for x in rows:
        by_vendor[vendor_of(x["model"])] += x["estimated_usd"]

    return {
        "label": "Estimated routed spend (derived)",
        "total_usd": total,
        "by_model": rows[:30],
        "by_vendor": [{"vendor": k, "estimated_usd": v, "share_pct": pct(v, total)}
                      for k, v in sorted(by_vendor.items(), key=lambda kv: -kv[1])],
        "models_without_pricing": missing,
        "assumptions": [
            "Tokens multiplied by published list prices from /api/v1/models.",
            "Prompt and completion prices are blended 50/50; the true split is not exposed per model.",
            "List rates only — negotiated enterprise pricing is not public and is typically lower.",
            "Covers OpenRouter-routed traffic only, which is a fraction of each vendor's total volume.",
            "This is NOT enterprise spend. It is an estimate of spend on gateway-routed traffic.",
        ],
    }


# ── task segmentation ────────────────────────────────────────────────────────

# Upstream renamed the per-model fields inside each classification's `models`
# list — `req_pct`/`tok_pct` (percent) became `tag_usage_share`/`tag_token_share`
# (0–1 fractions) — and this function used to pass that list through untouched.
# The rendering layer was therefore reading names owned by OpenRouter, so a
# rename on their side silently blanked every category card on the dashboard.
#
# Everything else in this file already normalises before it leaves: the
# classification shares two lines below are converted from fractions to
# percentages here rather than in the page. The nested model list was the one
# place that didn't, and it is the one place that broke.
#
# Normalise to a contract this project owns: {id, req_pct, tok_pct}, both in
# percent. Accept either upstream spelling so old committed data and new pulls
# both render, and drop entries we cannot interpret rather than emitting a key
# with no value behind it.

_MODEL_FIELD_ALIASES = {
    "req_pct": [("req_pct", 1), ("tag_usage_share", 100), ("usage_share", 100)],
    "tok_pct": [("tok_pct", 1), ("tag_token_share", 100), ("token_share", 100)],
}


def _normalise_top_models(models):
    out = []
    for m in models or []:
        mid = m.get("id") or m.get("model") or m.get("slug")
        if not mid:
            continue
        entry = {"id": mid}
        ok = True
        for target, candidates in _MODEL_FIELD_ALIASES.items():
            for name, scale in candidates:
                v = m.get(name)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    entry[target] = round(v * scale, 2)
                    break
            else:
                ok = False
        if ok:
            out.append(entry)
    return out


class UpstreamContractChanged(RuntimeError):
    """Raised when a feed still parses but no longer means what we read it as."""


def task_segmentation(tasks_doc):
    if not tasks_doc:
        return None
    d = tasks_doc["raw"]["data"]
    raw_cls = d.get("classifications", [])
    classifications = [
        {"tag": c["tag"], "display_name": c["display_name"],
         "macro_category": c["macro_category"],
         "usage_share_pct": round(c["usage_share"] * 100, 2),
         "token_share_pct": round(c["token_share"] * 100, 2),
         "top_models": _normalise_top_models(c.get("models", []))[:5]}
        for c in raw_cls
    ]

    # _normalise_top_models drops entries it cannot interpret, which is correct
    # per-entry but hides a total failure: if OpenRouter renames these fields a
    # THIRD time, every entry is dropped, the cards render empty, the refresh
    # workflow stays green, and nobody is told. That is the same silent-failure
    # mode as the defect this normaliser was written to fix. So distinguish
    # "upstream sent no models" from "upstream sent models we could not read",
    # and fail the build on the latter — loudly, at the earliest point, where
    # the daily workflow will surface it as a red run rather than a blank page.
    offered = sum(len(c.get("models") or []) for c in raw_cls)
    kept = sum(len(c["top_models"]) for c in classifications)
    if offered and not kept:
        sample = next((m for c in raw_cls for m in (c.get("models") or [])), {})
        raise UpstreamContractChanged(
            f"{offered} per-model entries received from the task feed and none were "
            f"readable. Known field spellings: "
            f"{[n for v in _MODEL_FIELD_ALIASES.values() for n, _ in v]}. "
            f"Keys actually present: {sorted(sample)}. "
            "Upstream has likely renamed these fields again — extend "
            "_MODEL_FIELD_ALIASES in compute.py (see DEF-2026-09-21-001)."
        )

    return {
        "as_of": d.get("as_of"),
        "window_days": d.get("window_days"),
        "macro_categories": d.get("macro_categories", []),
        "classifications": classifications,
        "note": ("Shares are of classified traffic; the unclassified bucket is excluded from the "
                 "denominator. Data is sampled, so absolute volumes are not available."),
    }


# ── known unknowns ───────────────────────────────────────────────────────────

KNOWN_UNKNOWNS = [
    {"question": "Market share across all AI inference",
     "why": "This measures traffic through one gateway. Most enterprise inference goes direct to "
            "provider APIs and is invisible here."},
    {"question": "Share by industry — financial services, healthcare, legal, manufacturing, "
                 "public sector, academic and sciences",
     "why": "A routing gateway observes task type, never caller identity. No usage API exposes "
            "industry segmentation. Any source publishing these numbers has estimated them."},
    {"question": "Enterprise API spend by vendor",
     "why": "No public endpoint exists. The spend figure here is derived from tokens and list "
            "prices, covers gateway traffic only, and is not a substitute."},
    {"question": "Customer support as a use-case",
     "why": "No corresponding tag exists in OpenRouter's app categories or task classifications."},
    {"question": "Whether token counts are comparable between vendors",
     "why": "They are not. Each provider's own tokenizer produces the counts, so summing across "
            "vendors adds unlike units. Request share is offered as the more comparable measure."},
]


def build(print_summary=False):
    tokens_doc = load("tokens-daily.json")
    if not tokens_doc:
        sys.exit("data/tokens-daily.json not found — run scripts/fetch_all.py first.")
    registry_doc = load("model-registry.json")
    licences_doc = load("open-weights.json")
    tasks_doc = load("tasks.json")

    shares = token_shares(tokens_doc)
    out = {
        "generated_from": {
            "tokens-daily.json": tokens_doc["_provenance"],
            "model-registry.json": (registry_doc or {}).get("_provenance"),
            "open-weights.json": (licences_doc or {}).get("_provenance"),
            "tasks.json": (tasks_doc or {}).get("_provenance"),
        },
        "token_share": shares,
        "open_weight": open_weight_share(shares, licences_doc, registry_doc) if licences_doc else None,
        "estimated_spend": estimated_spend(shares, registry_doc) if registry_doc else None,
        "task_segmentation": task_segmentation(tasks_doc),
        "known_unknowns": KNOWN_UNKNOWNS,
    }
    (DATA / "computed.json").write_text(json.dumps(out, indent=2))
    print(f"wrote data/computed.json")

    if print_summary:
        t = shares["totals"]
        print(f"\nwindow: {shares['window']['start']} .. {shares['window']['end']} "
              f"({shares['window']['days']} days)")
        print(f"unattributed excluded: {t['unattributed_tokens']:,} tokens "
              f"({t['unattributed_pct_of_visible']}% of visible traffic)")
        print("\ntop vendors by token share:")
        for v in shares["by_vendor"][:10]:
            print(f"  {v['key']:<20} {v['share_pct']:6.2f}%  {v['tokens']:>18,}")
        if out["open_weight"]:
            print("\nopen-weight split:")
            for b in out["open_weight"]["buckets"]:
                print(f"  {b['classification']:<18} {b['share_pct']:6.2f}%")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="show")
    a = ap.parse_args()
    sys.exit(build(a.show))
