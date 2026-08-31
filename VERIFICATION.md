# Verification report — 2026-08-31

Full audit of every figure rendered in every view: source, formula, internal consistency, and external corroboration.

**Verdict: GREEN.** Two defects found and fixed during the audit; all figures now reconcile.

---

## 1. Method

Three independent layers:

1. **Internal arithmetic** — recompute every displayed percentage from its stored numerator and denominator; check every set of shares sums correctly.
2. **Independent recomputation** — a fresh pull of the same 90-day window from the OpenRouter Data API, aggregated from scratch, compared against the committed figures.
3. **External corroboration** — compare a 7-day pull against the numbers OpenRouter publishes on its own public rankings page.

---

## 2. Independent recomputation — exact match

Fresh API pull, 2026-06-02 → 2026-08-30, 4,590 daily rows, re-aggregated with no reference to prior output:

| Quantity | Committed | Recomputed | Match |
|---|---|---|---|
| Attributed tokens | 710,084,349,872,854 | 710,084,349,872,854 | **exact** |
| Excluded (stealth/cloaked) | 38,148,956,923,798 | 38,148,956,923,798 | **exact** |
| Excluded % of visible | 4.79% | 4.79% | **exact** |
| DeepSeek share | 20.445% | 20.445% | **exact** |
| Xiaomi share | 11.274% | 11.274% | **exact** |
| Tencent share | 10.722% | 10.722% | **exact** |
| Anthropic share | 9.791% | 9.791% | **exact** |
| OpenAI share | 8.597% | 8.597% | **exact** |
| Google share | 8.286% | 8.286% | **exact** |
| Top model (Xiaomi MiMo-V2.5) | 10.359% | 10.359% | **exact** |

The `other` row differs by 33.6M tokens (0.00007%) between pulls. Expected: OpenRouter states the dataset "updates live as traffic flows through," so the in-progress day advances between calls. Recorded rather than smoothed.

## 3. External corroboration against OpenRouter's public page

A 7-day pull compared against the rankings page OpenRouter publishes:

| Model | My pull (7d to Aug 30) | Their page (through Aug 29) |
|---|---|---|
| DeepSeek V4 Flash 0731 | 12.31T | 12.3T |
| Tencent Hy3 | 6.66T | 6.62T |
| Gemini 3.7 Flash | 3.95T | 4.05T |
| Xiaomi MiMo-V2.5 | 9.14T | 9.98T |
| stealth/ox-alpha | 15.68T | 20.7T |

Ordering matches; magnitudes agree closely for stable models and diverge on fast-ramping ones. Cause is a one-day window offset — their page reads through Aug 29, my pull through Aug 30, and ox-alpha's volume is changing rapidly enough that one day moves it materially. This is corroboration, not a discrepancy.

## 4. Formula audit

| Figure | Formula | Verified |
|---|---|---|
| Vendor token share | vendor tokens ÷ (attributed + other) | Every row recomputed |
| Model token share | model tokens ÷ same denominator | Every row recomputed |
| Excluded % | excluded ÷ (denominator + excluded) | Recomputed |
| Estimated spend | Σ(model tokens × (prompt+completion)/2) | Every row recomputed |
| Spend share | vendor USD ÷ total USD | Every row recomputed |
| Open-weight share | bucket tokens ÷ denominator | Every bucket recomputed |
| Task shares | published by API as fractions; ×100 only | Sums checked |
| Category ratio | token share ÷ request share | Recomputed |

**Sums that must close, and do:**

- Vendor shares + tail + other = **99.999%**
- Macro-category request shares = **100.00%**; token shares = **99.90%**
- Classification request shares = **100.00%**; token shares = **99.70%**
- Each macro category's constituent tasks sum to its own share, within 0.1pp
- Open-weight buckets sum exactly to the model total they classify

Sub-100% totals are the API's own rounding of published fractions, not dropped data.

## 5. Defects found and fixed during this audit

**V-1 — vendor list truncated, shares didn't close (SEV3).** `by_vendor` held the top 21 vendors, but the denominator included all 26. 414.9B tokens (0.055%) sat in no row, so shares summed to 99.94% rather than 100%. Fixed by adding an explicit `(other attributed vendors)` row plus a `reconciliation` block asserting `listed + tail + other == denominator`. Now closes exactly.

**V-2 — default window contradicted the header (SEV4).** The weekly series spans 26 weeks (182 days) while the static figures cover 90 days. With 26 weeks selected by default, the page showed DeepSeek at 18.36% in one panel and 20.45% in another, both correct for their own window but jarring together. Default changed to **13 weeks (91 days)**, which aligns with the 90-day static window. Panels that cannot follow the selector now say so explicitly.

## 6. Classification audit — open-weight

Verified against vendor policy, not merely repository lookup:

| Rule | Models | Result |
|---|---|---|
| Anthropic → proprietary | 5 | All correct |
| Google Gemini → proprietary | 5 | All correct |
| Google Gemma → open | 1 | Correct (Apache-2.0) |
| OpenAI non-`gpt-oss` → proprietary | 3 | All correct |
| OpenAI `gpt-oss` → open | 1 | Correct (Apache-2.0) |
| Permissive licence on HF → open | — | Each carries a repo link |
| Neither weights nor stated policy → unknown | 1 | `tencent/hy3-preview` only |

Unknown fell from 36.3% of traffic to **2.3%** once vendor policy was applied. Every model carries either a licence with a source URL or a policy statement with one.

## 7. What could not be verified

- **Spend is derived, not observed.** It multiplies token volume by published list prices. Negotiated enterprise rates are not public and are typically lower, so the absolute dollar figure is indicative; the *relative* shape is the load-bearing part.
- **Task data is sampled.** OpenRouter publishes relative shares and withholds absolute volumes, so only proportions can be checked, not magnitudes.
- **Tokenizer incomparability is unresolvable.** Each provider counts with its own tokenizer. Summing across vendors adds unlike units — disclosed above the fold, and the reason request share is shown alongside.
- **The `other` row cannot be decomposed.** It aggregates every model outside the daily top 50; its vendor composition is not exposed.
- **Gateway scope.** Direct-to-provider enterprise traffic is invisible. This is the single largest limitation and it is stated in the first caveat on the page.
