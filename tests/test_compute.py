#!/usr/bin/env python3
"""Golden tests for the computation layer (AC-2, AC-4, AC-6, AC-12).

These run against a fixed synthetic fixture, not live data, so they verify the
arithmetic rather than the state of the world. The fixture deliberately includes
a stealth-provider model large enough to move every percentage, which is the
case most likely to be got wrong.

Run:  python tests/test_compute.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

failures = []


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except AssertionError as e:
        failures.append(name)
        print(f"FAIL {name}: {e}")
    except Exception as e:
        failures.append(name)
        print(f"ERROR {name}: {type(e).__name__}: {e}")


# ── fixture ──────────────────────────────────────────────────────────────────
# Two days. Round numbers so expected shares are checkable by hand.
#   attributed:   anthropic 200, google 300, deepseek 500  = 1000
#   other:                                                    200
#   denominator = 1200
#   stealth (excluded):                                       800
#   total visible = 2000  ->  stealth is 40% of visible traffic
FIXTURE_ROWS = []
for d in ("2026-08-01", "2026-08-02"):
    FIXTURE_ROWS += [
        {"date": d, "model_permaslug": "anthropic/claude-x", "total_tokens": "100"},
        {"date": d, "model_permaslug": "google/gemini-x", "total_tokens": "150"},
        {"date": d, "model_permaslug": "deepseek/ds-x", "total_tokens": "250"},
        {"date": d, "model_permaslug": "stealth/ox-alpha", "total_tokens": "400"},
        {"date": d, "model_permaslug": "other", "total_tokens": "100"},
    ]

TOKENS_DOC = {
    "_provenance": {"content_hash": "test", "as_of": "2026-08-03T00:00:00Z"},
    "raw": {"data": FIXTURE_ROWS, "meta": {"as_of": "2026-08-03T00:00:00Z"}},
}

# Mirrors the real /api/v1/models shape: `id` is the undated public slug,
# `canonical_slug` is the dated permaslug that rankings-daily actually returns,
# and `hugging_face_id` gives the licence repo. An earlier version of this
# fixture omitted canonical_slug, which let a join bug reach live data before
# anyone noticed — the fixture has to model the API, not a simplification of it.
REGISTRY_DOC = {
    "_provenance": {"content_hash": "test"},
    "raw": {"data": [
        {"id": "anthropic/claude-x", "canonical_slug": "anthropic/claude-x",
         "hugging_face_id": None,
         "pricing": {"prompt": "0.000010", "completion": "0.000030"}},
        {"id": "google/gemini-x", "canonical_slug": "google/gemini-x",
         "hugging_face_id": "google/gemini-x",
         "pricing": {"prompt": "0.000001", "completion": "0.000003"}},
        {"id": "deepseek/ds-x", "canonical_slug": "deepseek/ds-x",
         "hugging_face_id": "deepseek/ds-x",
         "pricing": {"prompt": "0.0000001", "completion": "0.0000003"}},
        # A dated permaslug whose public id differs — the exact case the join bug hit.
        {"id": "vendor/model-latest", "canonical_slug": "vendor/model-20260101",
         "hugging_face_id": None,
         "pricing": {"prompt": "0.000002", "completion": "0.000002"}},
        # A :batch variant of an existing slug must not displace the plain entry.
        {"id": "deepseek/ds-x:batch", "canonical_slug": "deepseek/ds-x",
         "hugging_face_id": "deepseek/ds-x",
         "pricing": {"prompt": "0.00000005", "completion": "0.00000015"}},
    ]},
}

LICENCES_DOC = {
    "_provenance": {"content_hash": "test"},
    "raw": {"data": {
        "deepseek/ds-x": {"hf_repo": "deepseek/ds-x", "license": "mit",
                          "source": "https://huggingface.co/deepseek/ds-x"},
        "google/gemini-x": {"hf_repo": "google/gemini-x", "license": "gemma",
                            "source": "https://huggingface.co/google/gemini-x"},
        # anthropic deliberately absent -> must classify as unknown, not proprietary
    }, "unmatched": ["anthropic/claude-x"]},
}


def with_fixture(fn):
    """Run fn with the fixture written into a temp data dir."""
    import compute
    tmp = Path(tempfile.mkdtemp())
    orig = compute.DATA
    compute.DATA = tmp
    try:
        (tmp / "tokens-daily.json").write_text(json.dumps(TOKENS_DOC))
        (tmp / "model-registry.json").write_text(json.dumps(REGISTRY_DOC))
        (tmp / "open-weights.json").write_text(json.dumps(LICENCES_DOC))
        return fn(compute)
    finally:
        compute.DATA = orig
        shutil.rmtree(tmp, ignore_errors=True)


# ── AC-4: unattributed exclusion ─────────────────────────────────────────────

def test_stealth_excluded_from_denominator():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        t = s["totals"]
        assert t["attributed_tokens"] == 1000, t["attributed_tokens"]
        assert t["other_tokens"] == 200, t["other_tokens"]
        assert t["unattributed_tokens"] == 800, t["unattributed_tokens"]
        assert t["denominator"] == 1200, t["denominator"]
    with_fixture(run)


def test_stealth_magnitude_reported():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        # 800 / 2000 = 40% of visible traffic — must be surfaced, not hidden
        assert s["totals"]["unattributed_pct_of_visible"] == 40.0, \
            s["totals"]["unattributed_pct_of_visible"]
    with_fixture(run)


def test_no_vendor_row_for_stealth():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        vendors = {v["key"] for v in s["by_vendor"]}
        assert "stealth" not in vendors, vendors
        assert vendors == {"anthropic", "google", "deepseek"}, vendors
    with_fixture(run)


# ── AC-2: share arithmetic ───────────────────────────────────────────────────

def test_vendor_shares_exact():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        got = {v["key"]: v["share_pct"] for v in s["by_vendor"]}
        # over denominator 1200: deepseek 500, google 300, anthropic 200
        assert abs(got["deepseek"] - 41.667) < 0.01, got
        assert abs(got["google"] - 25.0) < 0.01, got
        assert abs(got["anthropic"] - 16.667) < 0.01, got
    with_fixture(run)


def test_shares_plus_other_sum_to_100():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        vendor_sum = sum(v["share_pct"] for v in s["by_vendor"])
        other_share = compute.pct(s["totals"]["other_tokens"], s["totals"]["denominator"])
        assert abs(vendor_sum + other_share - 100.0) < 0.05, (vendor_sum, other_share)
    with_fixture(run)


# ── AC-12: open-weight classification ────────────────────────────────────────

def test_open_weight_classification_rules():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        ow = compute.open_weight_share(s, LICENCES_DOC, REGISTRY_DOC)
        by_model = {m["model"]: m["classification"] for m in ow["models"]}
        assert by_model["deepseek/ds-x"] == "open", by_model
        assert by_model["google/gemini-x"] == "open-restricted", by_model
        assert by_model["anthropic/claude-x"] == "unknown", by_model
    with_fixture(run)


def test_unknown_never_becomes_proprietary():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        ow = compute.open_weight_share(s, LICENCES_DOC, REGISTRY_DOC)
        classes = {b["classification"] for b in ow["buckets"]}
        assert "proprietary" not in classes, classes
        unknown = next(m for m in ow["models"] if m["model"] == "anthropic/claude-x")
        assert "not assumed proprietary" in unknown["evidence"]["note"]
    with_fixture(run)


# ── AC-6: derived spend ──────────────────────────────────────────────────────

def test_spend_is_derived_and_labelled():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        sp = compute.estimated_spend(s, REGISTRY_DOC)
        assert "derived" in sp["label"].lower(), sp["label"]
        joined = " ".join(sp["assumptions"]).lower()
        assert "not enterprise spend" in joined, sp["assumptions"]
    with_fixture(run)


def test_spend_arithmetic():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        sp = compute.estimated_spend(s, REGISTRY_DOC)
        got = {r["model"]: r["estimated_usd"] for r in sp["by_model"]}
        # anthropic: 200 tokens x blended (1e-5 + 3e-5)/2 = 2e-5 -> 0.004
        assert abs(got["anthropic/claude-x"] - 0.004) < 1e-6, got
        # deepseek: 500 x blended 2e-7 -> 0.0001
        assert abs(got["deepseek/ds-x"] - 0.0001) < 1e-9, got
    with_fixture(run)


def test_spend_inverts_token_ranking():
    """The barbell: deepseek leads on tokens, anthropic on spend. If this ever
    fails, either the fixture or the pricing join has broken."""
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        sp = compute.estimated_spend(s, REGISTRY_DOC)
        assert s["by_vendor"][0]["key"] == "deepseek", s["by_vendor"][0]
        assert sp["by_vendor"][0]["vendor"] == "anthropic", sp["by_vendor"][0]
    with_fixture(run)


# ── AC-5: known unknowns ─────────────────────────────────────────────────────

def test_price_join_uses_canonical_slug_not_id():
    """rankings-daily returns dated permaslugs; /api/v1/models keys on id but
    carries canonical_slug. Joining on id silently drops most models — it matched
    14 of 122 against live data. This guards the join."""
    def run(compute):
        rows = [{"date": "2026-08-01", "model_permaslug": "vendor/model-20260101",
                 "total_tokens": "1000"}]
        doc = {"_provenance": {}, "raw": {"data": rows}}
        s = compute.token_shares(doc)
        sp = compute.estimated_spend(s, REGISTRY_DOC)
        assert sp["models_without_pricing"] == [], sp["models_without_pricing"]
        assert abs(sp["by_model"][0]["estimated_usd"] - 0.002) < 1e-9, sp["by_model"]
    with_fixture(run)


def test_batch_variant_does_not_displace_plain_pricing():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        sp = compute.estimated_spend(s, REGISTRY_DOC)
        ds = next(r for r in sp["by_model"] if r["model"] == "deepseek/ds-x")
        assert abs(ds["blended_price_per_token"] - 2e-7) < 1e-12, ds
    with_fixture(run)


def test_openrouter_cloaked_models_excluded():
    """Cloaked models under openrouter/* (ox-alpha, owl-alpha) have a vendor
    string but an undisclosed author, so they belong with stealth traffic."""
    def run(compute):
        assert compute.is_unattributed("openrouter/owl-alpha")
        assert compute.is_unattributed("openrouter/ox-alpha")
        assert compute.is_unattributed("stealth/ox-alpha")
        assert not compute.is_unattributed("openai/gpt-oss-120b")
        assert not compute.is_unattributed("google/gemini-3.7-flash-20260813")
    with_fixture(run)


def test_known_unknowns_cover_industry_verticals():
    import compute
    text = json.dumps(compute.KNOWN_UNKNOWNS).lower()
    for term in ["healthcare", "legal", "financial services", "public sector",
                 "manufacturing", "academic"]:
        assert term in text, f"{term} missing from known unknowns"


def test_known_unknowns_explain_tokenizer_incomparability():
    import compute
    text = json.dumps(compute.KNOWN_UNKNOWNS).lower()
    assert "tokenizer" in text and "comparable" in text, "tokenizer caveat missing"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print()
    if failures:
        print(f"RESULT: FAIL — {len(failures)} test(s): {', '.join(failures)}")
        sys.exit(1)
    print("RESULT: PASS — all golden tests green")
