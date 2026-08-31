# Spec — Share of Traffic on OpenRouter

**Tier:** T1 (public, reputation-bearing)
**Build mode:** staged
**Built through:** multi-agent-harness v0.3.0

## Intent

Enterprise AI platform teams choosing which models to route workloads to have no honest public reference for what developers actually run. Every available page republishes the same numbers, sourced from SEO aggregators that copied each other, with no methodology and no dates. A team trying to justify a routing decision to their architecture board has nothing citable.

This dashboard measures one thing precisely and says exactly what it is: **the share of traffic flowing through OpenRouter's gateway**, computed from OpenRouter's own CC BY 4.0 licensed Data API, refreshed daily, with every figure traceable to an API response committed in the repository.

It is deliberately *not* a market-share dashboard. Most enterprise inference goes direct to Anthropic, OpenAI or Vertex and never touches a gateway. Naming the artifact for what it actually measures is the point.

## Goals

- Three metrics over a trailing 90-day window: **token share**, **request share**, and **estimated routed spend** (derived, labelled).
- Segmentation by OpenRouter's real taxonomy — app categories, app subcategories, and task classifications — never by invented industry verticals.
- **Open-weight versus proprietary share**, computed by joining traffic volume against model licence data.
- A **routing advisor** that turns a workload mix into a suggested model split with cost estimates from live list pricing.
- A **Known Unknowns** panel naming what cannot be measured from this data and why.

## Non-goals

- Not a claim about total AI market share. Gateway traffic only.
- No industry-vertical segmentation. A gateway sees task type, never caller identity. Six of the originally requested use-cases (financial services, healthcare, legal, manufacturing, public sector, academic/sciences) are structurally unmeasurable and will be stated as such.
- No enterprise spend claims. The spend figure is derived from tokens × list prices and is labelled *estimated routed spend*.
- No benchmark or capability rankings. Adoption is not quality.
- The advisor does not make procurement decisions. It has no view of latency requirements, compliance posture, data residency, or negotiated rates.

## Audience

Primary: platform engineers and technical product leads choosing a model-routing strategy, who need something citable in an internal review.
Secondary: anyone who wants one honest number instead of five contradictory ones.

## Data sources — live APIs only

| Feed | Endpoint | Cadence |
|---|---|---|
| Token volume by model | `/api/v1/datasets/rankings-daily` (90d) | Daily |
| Task classification shares | `/api/v1/classifications/task` (7d window) | Daily |
| App rankings by category | `/api/v1/datasets/app-rankings` | Daily |
| Model registry — pricing, provenance | `/api/v1/models` | Daily |
| Model licences | HuggingFace Hub API | Daily |

All OpenRouter data is CC BY 4.0 and carries the citation line with `meta.as_of`.

**No aggregator sources. No hand-entered figures. No numbers carried from any prior document** — the market-analysis document that prompted this project sourced its key figures to SEO aggregators and its numbers were already wrong against live data. Everything here is computed from scratch.

## Binding constraints

1. **Every rendered figure traces to an API response committed under `data/`.** No hand-entered numbers anywhere.
2. **Unattributed models are excluded from all share denominators.** Models published under an anonymous or stealth provider cannot have vendor or licence established. Excluded volume is reported separately, with its magnitude visible, so readers can judge the effect.
3. **Two caveats render above the fold:** that this is gateway traffic and not the market, and that token counts from different providers use different tokenizers and are not directly comparable.
4. **Derived figures are labelled derived** and show their arithmetic.
5. **What cannot be measured is stated, not estimated.**
6. **The API key never enters the client bundle, the repository, or git history.**

## Stack

Static HTML dashboard on Vercel reading JSON committed by scheduled GitHub Actions. Optional Gemini API narrative layer via a serverless function, server-side key only. No build step; the page works with the narrative API unavailable.
