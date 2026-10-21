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


def test_write_handles_every_real_response_shape():
    """The fetch layer meets four different response shapes. `data` is a list on
    rankings-daily and models, a dict on classifications. Calling .get() on the
    list raised AttributeError and killed the models feed on every scheduled run
    — the failure only surfaced in CI because the script had never been executed."""
    import tempfile
    from pathlib import Path as _P
    sys.path.insert(0, str(ROOT / "scripts"))
    import fetch_all as F
    tmp = _P(tempfile.mkdtemp())
    orig = F.DATA_DIR
    F.DATA_DIR = tmp
    try:
        shapes = {
            "rankings": {"data": [{"date": "2026-08-01"}], "meta": {"as_of": "X"}},
            "models":   {"data": [{"id": "a/b"}]},                       # list, no meta
            "classif":  {"data": {"as_of": "2026-08-30", "window_days": 7}},
            "apps":     {"categories": {}, "meta": {"as_of": "Y"}},
        }
        for label, payload in shapes.items():
            F.write("t.json", payload, "https://openrouter.ai/x", "daily")
            doc = json.loads((tmp / "t.json").read_text())
            assert doc["_provenance"]["as_of"], f"{label} produced no as_of"
    finally:
        F.DATA_DIR = orig
        shutil.rmtree(tmp, ignore_errors=True)


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


# --- Regression: DEF-2026-09-21-001, rendering-layer field contract ---------
#
# index.html read `req_pct` / `tok_pct` from each per-task top_models entry.
# compute.py has never emitted those names; it emits `tag_usage_share` /
# `tag_token_share`. Every category card threw on its first model row and the
# page's single catch block reported "No data yet — run fetch_all.py", so a
# correct, fully-populated dataset presented as an empty one.
#
# Every test above this line checks compute.py against itself. None of them
# could see this, because the defect lived in the seam BETWEEN compute.py and
# index.html — the one place nothing was asserting. These two tests hold that
# seam from both sides.

def _index_html_text():
    return (Path(__file__).resolve().parent.parent / "index.html").read_text(encoding="utf-8")


def test_normalises_both_upstream_model_field_spellings():
    """The rename that caused the defect must now pass through unnoticed."""
    import compute
    old = [{"id": "a/b", "req_pct": 9.2, "tok_pct": 3.7}]              # pre-rename
    new = [{"id": "a/b", "tag_usage_share": 0.092, "tag_token_share": 0.037}]  # post-rename
    assert compute._normalise_top_models(old) == [{"id": "a/b", "req_pct": 9.2, "tok_pct": 3.7}]
    assert compute._normalise_top_models(new) == [{"id": "a/b", "req_pct": 9.2, "tok_pct": 3.7}]


def test_normalised_entries_never_carry_a_key_without_a_value():
    """Half-populated rows are dropped, not emitted for the page to trip over."""
    import compute
    assert compute._normalise_top_models([{"id": "a/b", "req_pct": 9.2}]) == []
    assert compute._normalise_top_models([{"req_pct": 1, "tok_pct": 2}]) == []
    assert compute._normalise_top_models([{"id": "a/b", "req_pct": None, "tok_pct": 2}]) == []
    assert compute._normalise_top_models(None) == []


def test_a_further_upstream_rename_fails_loudly_instead_of_emptying_the_page():
    """The normaliser must not silently absorb a spelling it does not know.

    Dropping an unreadable entry is right per-entry and wrong in aggregate: a
    third rename would drop all of them, render empty cards, and leave the daily
    refresh green. That is the defect again, one level up.
    """
    import compute
    doc = {"raw": {"data": {
        "as_of": "2026-01-01", "window_days": 7, "macro_categories": [],
        "classifications": [{
            "tag": "t", "display_name": "T", "macro_category": "general",
            "usage_share": 0.5, "token_share": 0.5,
            "models": [{"id": "a/b", "some_future_name": 0.5, "another": 0.5}],
        }],
    }}}
    try:
        compute.task_segmentation(doc)
    except compute.UpstreamContractChanged as e:
        assert "renamed" in str(e) and "a/b" not in str(e).split("Keys actually present")[0]
        assert "some_future_name" in str(e), "the error must name the keys actually present"
        return
    raise AssertionError(
        "task_segmentation accepted a payload whose per-model fields it could not "
        "read; a future rename would blank the cards with a green build"
    )


def test_upstream_sending_no_models_is_not_an_error():
    """Absent is legitimate; unreadable is not. Don't conflate them."""
    import compute
    doc = {"raw": {"data": {
        "as_of": "2026-01-01", "window_days": 7, "macro_categories": [],
        "classifications": [{
            "tag": "t", "display_name": "T", "macro_category": "general",
            "usage_share": 0.5, "token_share": 0.5, "models": [],
        }],
    }}}
    out = compute.task_segmentation(doc)
    assert out["classifications"][0]["top_models"] == []


def test_committed_output_matches_the_owned_contract():
    """Whatever is committed must be readable by the page as shipped."""
    live = Path(__file__).resolve().parent.parent / "data" / "computed.json"
    if not live.exists():
        return                       # clean checkout before a fetch; nothing to check
    seg = json.loads(live.read_text(encoding="utf-8")).get("task_segmentation", {})
    cls = seg.get("classifications", [])
    if not cls:
        return                       # no task feed in this snapshot
    assert any(c.get("top_models") for c in cls), (
        "classifications are present but every top_models list is empty — upstream "
        "has probably renamed the per-model fields again (DEF-2026-09-21-001)"
    )
    entries = [x for c in cls for x in c.get("top_models", [])]
    for x in entries:
        readable = ({"id", "req_pct", "tok_pct"} <= set(x)
                    or {"id", "tag_usage_share", "tag_token_share"} <= set(x))
        assert readable, f"top_models entry {sorted(x)} is readable by neither spelling"


def test_page_reads_model_shares_through_the_tolerant_accessor():
    """index.html must not index these fields directly again."""
    html = _index_html_text()
    assert "modelPct(" in html, "the tolerant accessor is gone from index.html"
    for direct in ("x.req_pct.toFixed", "x.tok_pct.toFixed",
                   "x.tag_usage_share.toFixed", "x.tag_token_share.toFixed"):
        assert direct not in html, (
            f"index.html dereferences `{direct}` directly; an upstream rename or a "
            "missing value blanks the page again (DEF-2026-09-21-001)"
        )


def test_render_failure_is_not_reported_as_missing_data():
    """The catch block must distinguish a failed load from a failed render."""
    html = _index_html_text()
    assert "Data loaded, but rendering failed" in html, (
        "the fetch/render catch block collapses both failure modes into "
        "'No data yet', which is what hid DEF-2026-09-21-001"
    )


# --- Weekly series (P0) ------------------------------------------------------
#
# index.html has read DATA.series since the trend tab was built; compute.py never
# produced it, so the selector and trend tab did nothing. These tests hold the
# producer to the same rules as the 90-day aggregate.
#
# Fixture: 2026-08-01 (Sat) .. 2026-08-18 (Tue), 18 days.
#   complete Sunday-start weeks: 08-02..08-08, 08-09..08-15  -> 2 weeks
#   dropped: 08-01 leading (1 day), 08-16..08-18 trailing (3 days)
# Day k (0-based) carries k-dependent volumes so a bucketing error shows up in
# the sums, a cloaked openrouter/* model, and a vendor present only on some days.
from datetime import date as _date, timedelta as _td

WEEKLY_ROWS = []
for k in range(18):
    d = (_date(2026, 8, 1) + _td(days=k)).isoformat()
    WEEKLY_ROWS += [
        {"date": d, "model_permaslug": "anthropic/claude-x", "total_tokens": str(100 + k)},
        {"date": d, "model_permaslug": "google/gemini-x", "total_tokens": str(150 + 2 * k)},
        {"date": d, "model_permaslug": "deepseek/ds-x", "total_tokens": "250"},
        {"date": d, "model_permaslug": "stealth/ox-alpha", "total_tokens": "400"},
        {"date": d, "model_permaslug": "openrouter/owl-alpha", "total_tokens": "30"},
        {"date": d, "model_permaslug": "other", "total_tokens": str(100 + k)},
    ]
    if k % 3 == 0:     # drops in and out of the top 50
        WEEKLY_ROWS.append({"date": d, "model_permaslug": "mistralai/m-x", "total_tokens": "70"})
WEEKLY_DOC = {"_provenance": {}, "raw": {"data": WEEKLY_ROWS}}


def _weekly():
    import compute
    return compute, compute.weekly_series(WEEKLY_DOC)


def test_weekly_drops_partial_weeks_at_both_ends():
    compute, s = _weekly()
    assert s["weeks"] == ["2026-08-02", "2026-08-09"], s["weeks"]
    assert s["days_dropped"] == {"leading": 1, "trailing": 3, "total": 4}, s["days_dropped"]
    assert s["covered"] == {"start": "2026-08-02", "end": "2026-08-15", "days": 14}, s["covered"]
    for k, v in s["vendors"].items():
        assert len(v) == len(s["weeks"]), (k, v)
    # week 1 = days k=1..7: anthropic 100+k -> 7*100 + (1+..+7) = 728
    assert s["vendors"]["anthropic"] == [728, 777], s["vendors"]["anthropic"]
    # mistral appears on k in {3,6} in week 1 and {9,12} in week 2; zero-filled otherwise
    assert s["vendors"]["mistralai"] == [140, 140], s["vendors"]["mistralai"]


def test_weekly_shares_close_to_100_in_every_week():
    compute, s = _weekly()
    names = [k for k in s["vendors"] if not k.startswith("_")]
    for i, wk in enumerate(s["weeks"]):
        listed = sum(s["vendors"][k][i] for k in names)
        assert listed + s["vendors"]["_other"][i] == s["denominator"][i], wk
        share_sum = sum(compute.pct(s["vendors"][k][i], s["denominator"][i]) for k in names) \
            + compute.pct(s["vendors"]["_other"][i], s["denominator"][i])
        assert abs(share_sum - 100.0) < 0.05, (wk, share_sum)
    assert s["reconciliation"] == {"weeks_checked": 2, "sums_exactly": True}


def test_weekly_excludes_unattributed_on_the_aggregate_rule():
    compute, s = _weekly()
    names = {k for k in s["vendors"] if not k.startswith("_")}
    assert names == {"anthropic", "google", "deepseek", "mistralai"}, names
    assert "stealth" not in names and "openrouter" not in names
    # stealth 400 + cloaked openrouter/owl-alpha 30, every day, 7 days a week
    assert s["vendors"]["_unattributed"] == [3010, 3010], s["vendors"]["_unattributed"]
    for i in range(len(s["weeks"])):
        assert s["denominator"][i] == sum(s["vendors"][k][i] for k in names) + s["vendors"]["_other"][i]


def test_weekly_series_uses_the_same_rules_as_the_headline():
    """Summed over its covered days, the series must equal token_shares() run on
    exactly those days. Any divergence in vendor derivation or exclusion fails."""
    import compute
    s = compute.weekly_series(WEEKLY_DOC)
    lo, hi = s["covered"]["start"], s["covered"]["end"]
    covered = {"_provenance": {}, "raw": {"data": [r for r in WEEKLY_ROWS if lo <= r["date"] <= hi]}}
    agg = compute.token_shares(covered)
    for v in agg["by_vendor"]:
        assert sum(s["vendors"][v["key"]]) == v["tokens"], v
    assert sum(s["vendors"]["_other"]) == agg["totals"]["other_tokens"]
    assert sum(s["vendors"]["_unattributed"]) == agg["totals"]["unattributed_tokens"]
    assert sum(s["denominator"]) == agg["totals"]["denominator"]


def test_weekly_series_absent_when_no_complete_week():
    """Two days (Sat, Sun) contain no full week. Absent, not an empty shell."""
    import compute
    assert compute.weekly_series(TOKENS_DOC) is None


def test_weekly_gap_inside_a_complete_week_fails_loudly():
    import compute
    rows = [r for r in WEEKLY_ROWS if r["date"] != "2026-08-05"]
    try:
        compute.weekly_series({"_provenance": {}, "raw": {"data": rows}})
    except compute.ReconciliationError as e:
        assert "2026-08-05" in str(e), e
        return
    raise AssertionError("a 6-day bucket was emitted as a complete week")


def test_weekly_note_and_known_unknowns_disclose_top50_churn():
    import compute
    _, s = _weekly()
    for text in (s["note"].lower(), json.dumps(compute.KNOWN_UNKNOWNS).lower()):
        assert "top 50" in text and "churn" in text and "demand" in text, text[:200]


def test_90_day_reconciliation_is_emitted_for_the_page():
    """index.html's Reconciliation panel reads token_share.reconciliation. With
    nothing emitting it, the panel printed 'FAILS' over data that closes."""
    import compute
    rows = [r for r in WEEKLY_ROWS]
    s = compute.token_shares({"_provenance": {}, "raw": {"data": rows}})
    r = s["reconciliation"]
    assert r["sums_exactly"] is True
    assert r["listed_vendors"] + r["tail_vendors"] + s["totals"]["other_tokens"] \
        == s["totals"]["denominator"], r
    html = _index_html_text()
    for k in ("listed_vendors", "tail_vendors", "sums_exactly"):
        assert f"r.{k}" in html, f"index.html no longer reads reconciliation.{k}"


def test_page_reads_only_series_fields_the_producer_emits():
    """DEF-2026-09-21-001 seam, held for the series: every series field the page
    dereferences must be one compute.weekly_series() emits, and the page must
    gate the trend tab on a validity check rather than a bare truthiness test."""
    import re
    _, s = _weekly()
    html = _index_html_text()
    # The page names the series `ser` everywhere it reads it.
    read = set(re.findall(r"\bser\.(\w+)", html))
    assert read, "index.html no longer reads the series through `ser`"
    unknown = read - set(s)
    assert not unknown, f"index.html reads series fields compute.py does not emit: {unknown}"
    for outer, inner in set(re.findall(r"\bser\.(\w+)\.(\w+)", html)):
        if isinstance(s[outer], dict):       # e.g. ser.days_dropped.total
            assert inner in s[outer], f"index.html reads ser.{outer}.{inner}; not emitted"
    for k in ("_other", "_unattributed"):
        assert k in s["vendors"] and k in html, k
    assert "seriesOK(" in html, "the series validity gate is gone from index.html"
    assert "if (d.series)" not in html, "trend view gated on bare truthiness again"


def test_committed_output_carries_a_usable_series():
    """Ship order: computed.json is committed alongside the page that reads it."""
    live = ROOT / "data" / "computed.json"
    if not live.exists() or not (ROOT / "data" / "tokens-daily.json").exists():
        return
    d = json.loads(live.read_text(encoding="utf-8"))
    s = d.get("series")
    assert s, "computed.json has no series; the trend tab will be hidden"
    n = len(s["weeks"])
    assert n >= 4, n
    for k, v in s["vendors"].items():
        assert len(v) == n, k
    assert s["covered"]["days"] == 7 * n
    assert s["covered"]["days"] + s["days_dropped"]["total"] == d["token_share"]["window"]["days"]


# --- P1: per-task intensity, open-weight closure ----------------------------

def _task_doc(classifications):
    return {"raw": {"data": {"as_of": "2026-01-01", "window_days": 7,
                             "macro_categories": [], "classifications": classifications}}}


def test_task_token_to_request_ratio():
    import compute
    out = compute.task_segmentation(_task_doc([
        {"tag": "code", "display_name": "Code", "macro_category": "code",
         "usage_share": 0.112, "token_share": 0.356, "models": []},
        {"tag": "cls", "display_name": "Classification", "macro_category": "general",
         "usage_share": 0.302, "token_share": 0.072, "models": []},
    ]))
    r = {c["tag"]: c["token_to_request_ratio"] for c in out["classifications"]}
    # from the unrounded fractions: 0.356 / 0.112 and 0.072 / 0.302
    assert abs(r["code"] - 3.178571) < 1e-6, r
    assert abs(r["cls"] - 0.238411) < 1e-6, r


def test_task_ratio_never_infinite():
    """Zero or missing request share yields None (rendered as a dash), not Infinity."""
    import compute
    assert compute.token_to_request_ratio(0.05, 0) is None
    assert compute.token_to_request_ratio(0.05, 0.0) is None
    assert compute.token_to_request_ratio(0.05, None) is None
    assert compute.token_to_request_ratio(None, 0.1) is None
    assert compute.token_to_request_ratio(True, 0.1) is None
    assert compute.token_to_request_ratio(0, 0.1) == 0
    out = compute.task_segmentation(_task_doc([
        {"tag": "z", "display_name": "Z", "macro_category": "general",
         "usage_share": 0, "token_share": 0.01, "models": []}]))
    assert out["classifications"][0]["token_to_request_ratio"] is None
    json.dumps(out, allow_nan=False)      # no Infinity / NaN can reach computed.json


def test_open_weight_buckets_close_to_100():
    """Regression for DEF-2026-10-20-003: classified buckets + the unclassified
    remainder == denominator. The bar used to sum to ~88% with no explanation."""
    import compute
    # 60 attributed models: only the top 50 are classified; plus an 'other' row.
    rows = [{"date": "2026-08-01", "model_permaslug": f"v{i % 3}/m{i}", "total_tokens": str(1000 - i)}
            for i in range(60)]
    rows.append({"date": "2026-08-01", "model_permaslug": "other", "total_tokens": "5000"})
    s = compute.token_shares({"_provenance": {}, "raw": {"data": rows}})
    ow = compute.open_weight_share(s, LICENCES_DOC, REGISTRY_DOC)
    u = ow["unclassified"]
    classified = sum(b["tokens"] for b in ow["buckets"])
    assert classified + u["tokens"] == s["totals"]["denominator"], (classified, u)
    assert u["other_row_tokens"] == 5000, u
    assert u["beyond_top_models_tokens"] == sum(1000 - i for i in range(50, 60)), u
    share_sum = sum(b["share_pct"] for b in ow["buckets"]) + u["share_pct"]
    assert abs(share_sum - 100.0) < 0.05, share_sum
    assert "unknown" in {b["classification"] for b in ow["buckets"]}
    assert "unclassified" not in {b["classification"] for b in ow["buckets"]}, \
        "'not classified' must stay distinct from 'unknown'"


def test_open_weight_unclassified_with_fixture():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        ow = compute.open_weight_share(s, LICENCES_DOC, REGISTRY_DOC)
        # all 3 models classified; only the 200-token 'other' row remains
        assert ow["unclassified"]["tokens"] == 200, ow["unclassified"]
        assert ow["unclassified"]["beyond_top_models_tokens"] == 0
    with_fixture(run)


def test_page_reads_new_p1_fields_defensively():
    html = _index_html_text()
    assert "token_to_request_ratio" in html, "per-task ratio not rendered"
    assert "fmtRatio(" in html, "ratio must go through the dash-on-invalid formatter"
    assert "ow.unclassified" in html, "open-weight remainder not rendered"
    assert "t.token_to_request_ratio.toFixed" not in html


def test_spend_price_coverage():
    """Coverage is computed, not typed: priced tokens over the top models and
    over all attributed traffic."""
    import compute
    rows = list(FIXTURE_ROWS) + [
        {"date": "2026-08-01", "model_permaslug": "nopricevendor/m", "total_tokens": "300"}]
    s = compute.token_shares({"_provenance": {}, "raw": {"data": rows}})
    c = compute.estimated_spend(s, REGISTRY_DOC)["price_coverage"]
    # priced: anthropic 200 + google 300 + deepseek 500 = 1000 of 1300 attributed
    assert c["priced_tokens"] == 1000 and c["top_models_tokens"] == 1300, c
    assert c["attributed_tokens"] == 1300 and c["top_models_count"] == 4, c
    assert abs(c["pct_of_top_models"] - 76.923) < 0.001, c
    assert c["pct_of_attributed"] == c["pct_of_top_models"]


def test_parity_ratio_is_spend_share_over_token_share():
    """P2 task 3. anthropic: spend 0.004 of 0.0047 over tokens 200 of 1200
    = 0.851064 / 0.166667 = 5.10638; deepseek: 0.0001/0.0047 over 500/1200."""
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        sp = compute.estimated_spend(s, REGISTRY_DOC)
        r = {v["vendor"]: v for v in sp["by_vendor"]}
        assert abs(r["anthropic"]["parity_ratio"] - 5.106383) < 1e-6, r["anthropic"]
        assert abs(r["deepseek"]["parity_ratio"] - 0.051064) < 1e-6, r["deepseek"]
        assert abs(r["anthropic"]["token_share_pct"] - 16.667) < 0.001
        # same quantity the scatter plots: y / x on the rounded shares, to rounding
        a = r["anthropic"]
        assert abs(a["share_pct"] / a["token_share_pct"] - a["parity_ratio"]) < 1e-3
        json.dumps(sp, allow_nan=False)
    with_fixture(run)


def test_parity_ratio_none_without_tokens():
    import compute
    s = {"by_vendor": [], "totals": {"denominator": 0, "attributed_tokens": 0}, "by_model": [
        {"key": "anthropic/claude-x", "tokens": 0, "share_pct": 0.0}]}
    sp = compute.estimated_spend(s, REGISTRY_DOC)
    assert all(v["parity_ratio"] is None for v in sp["by_vendor"]), sp["by_vendor"]


# --- Verification fixes (2026-10-21, checked against openrouter.ai) ----------

def test_customer_support_unknown_only_while_true():
    """Regression for DEF-2026-10-21-001: the page asserted 'no customer support
    tag exists' after OpenRouter added one. Emitted only while it is true."""
    import compute
    q = lambda ku: [u for u in ku if "customer support" in u["question"].lower()]
    with_tag = {"classifications": [{"tag": "customer_support", "display_name": "Customer Support"}]}
    without = {"classifications": [{"tag": "code", "display_name": "Code Generation"}]}
    assert q(compute.known_unknowns(with_tag)) == [], "claims no tag while one exists"
    assert len(q(compute.known_unknowns(without))) == 1
    assert len(q(compute.known_unknowns(None))) == 1
    assert not q(compute.KNOWN_UNKNOWNS), "the unconditional list must not carry the claim"


def test_committed_known_unknowns_agree_with_the_task_feed():
    live = ROOT / "data" / "computed.json"
    if not live.exists():
        return
    d = json.loads(live.read_text(encoding="utf-8"))
    cls = (d.get("task_segmentation") or {}).get("classifications") or []
    has_tag = any("support" in (c["tag"] + c["display_name"]).lower() for c in cls)
    claims_none = any("customer support" in u["question"].lower() for u in d["known_unknowns"])
    assert not (has_tag and claims_none), "computed.json says no support tag while the feed has one"


def test_public_traffic_only_is_disclosed():
    """OpenRouter's Data API excludes private and zero-data-retention traffic."""
    import compute
    text = json.dumps(compute.KNOWN_UNKNOWNS).lower()
    assert "public traffic only" in text and "zero-data-retention" in text
    assert "public traffic only" in _index_html_text()


def test_spend_assumptions_disclose_price_snapshot_and_caching():
    def run(compute):
        s = compute.token_shares(TOKENS_DOC)
        a = " ".join(compute.estimated_spend(s, REGISTRY_DOC)["assumptions"]).lower()
        assert "snapshot" in a and "promotion" in a, a
        assert "caching" in a, a
    with_fixture(run)


def test_page_distinguishes_token_share_from_request_share():
    html = _index_html_text()
    assert "Token share vs request share" in html


def test_page_prose_carries_no_hardcoded_figures():
    """Figures in the page's prose drift from the data on every refresh (the
    task paragraph claimed 27% / 72.5% while the data said 22.4% / 63.1%).
    Static markup and the FORMULAS / DEFINITIONS text may not carry measured
    percentages, multipliers or dates; they are rendered from computed.json."""
    import re
    html = _index_html_text()
    markup = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", html, flags=re.S)
    m = re.search(r"const FORMULAS = \[(.*?)\];\s*const DEFINITIONS = \[(.*?)\];", html, re.S)
    assert m, "FORMULAS / DEFINITIONS blocks not found"
    prose = markup + m.group(1) + m.group(2)
    # Illustrative arithmetic, not measurements: shares close to 100%, and the
    # movers example "a move from 2% to 4% is +2pp, not +100%".
    allowed = {"100%", "2%", "4%", "+100%", "1.0×"}
    figs = {f for f in re.findall(r"\+?\d+(?:\.\d+)?\s?[%×]", prose) if f.replace(" ", "") not in allowed}
    assert not figs, f"hardcoded figures in page prose: {sorted(figs)}"
    dates = [d for d in re.findall(r"(?<!DEF-)\b20\d\d-\d\d-\d\d\b", prose)]
    assert not dates, f"hardcoded dates in page prose: {dates}"
    assert not re.search(r"\b\d+-day\b", prose), "hardcoded window length in page prose"


def test_page_p2_seams():
    """Ratio read through parityOf (never a bare y/x), sort keeps aggregate
    rows last, filters built only from vendor and licence — no pricing tier."""
    import re
    html = _index_html_text()
    assert "parityOf(" in html and "parity_ratio" in html
    assert "c.raw.y/c.raw.x" not in html, "scatter tooltip divides rounded shares again"
    assert "classList.contains('agg')" in html, "sort must keep aggregate rows out of the sort"
    for hid in ("t-models", "t-open"):
        assert f"filterableTable('{hid}'" in html, hid
    dims = set(re.findall(r"pills\('(\w+)'", html))
    assert dims == {"vendor", "licence"}, f"filter dimensions must come from model fields only: {dims}"
    # the page's vendorOf must be compute.vendor_of's rule
    import compute
    for k in ("deepseek/deepseek-v4-flash-20260731", "openai/gpt-oss-120b:free", "other"):
        js = k.split("/")[0] if "/" in k else k
        assert compute.vendor_of(k) == js, k
    assert "const vendorOf = k => k.includes('/') ? k.split('/')[0] : k;" in html


def test_every_chart_has_an_exportable_table():
    html = _index_html_text()
    for cid in ("c-scatter", "c-paired", "c-trend", "c-tasks", "c-spend", "c-open"):
        assert f"exportTable('{cid}'" in html or f"vendorShareTable('{cid}'" in html, \
            f"{cid} has no data table / export"
        assert f'id="x-{cid}"' in html, f"{cid} has no table container in the DOM"
    for fn in ("tableToCSV(", "tableToMarkdown("):
        assert fn in html, fn


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print()
    if failures:
        print(f"RESULT: FAIL — {len(failures)} test(s): {', '.join(failures)}")
        sys.exit(1)
    print("RESULT: PASS — all golden tests green")
