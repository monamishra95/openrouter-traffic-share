# Findings — first real data pull, 2026-08-30

Window: **2 June – 30 August 2026** (90 days, 4,590 daily rows, 122 models, 25 vendors).
Source: OpenRouter Data API, CC BY 4.0. `meta.as_of` 2026-08-31T03:39:14Z.

---

## 1. The barbell, computed rather than asserted

| Vendor | Token share | Estimated spend share |
|---|---|---|
| DeepSeek | **20.45%** | 5.70% |
| Xiaomi | 11.27% | 1.20% |
| Tencent | 10.72% | 1.83% |
| **Anthropic** | 9.79% | **54.15%** |
| OpenAI | 8.60% | 14.13% |
| Google | 8.29% | 6.23% |
| Z-AI | 6.01% | 5.45% |
| MiniMax | 5.53% | 1.80% |
| NVIDIA | 4.67% | 2.26% |

**Anthropic moves 9.8% of tokens and captures 54.2% of estimated routed spend.** DeepSeek is the mirror image: 20.5% of tokens, 5.7% of spend. That is a 5.5× spend-to-token ratio at one end and 0.28× at the other — a ~20× spread in realised value per token across the two ends of the market.

Price data covers **98.9%** of attributed token volume, so this isn't a thin-sample artifact.

## 2. Task classification — richer than expected, and it corrects my own prediction

Twenty-nine live classifications across four macro-categories. I predicted from the documentation that customer support, finance and research would be unmeasurable. **All three exist as first-class tags.** That prediction was wrong and the plan has been corrected.

| Macro-category | Share of requests | Share of tokens |
|---|---|---|
| General | 53.8% | 22.1% |
| Data | 19.2% | 5.3% |
| Agent | 14.3% | **34.9%** |
| Code | 12.7% | **37.6%** |

**Code and Agent are 27% of requests but 72.5% of tokens.** That single line is the strongest argument in the dataset for why request-share and token-share must both be shown — a dashboard reporting only tokens would suggest the market is dominated by coding, when by request volume it's dominated by classification, extraction and chat.

The most extreme individual case: **Workflow Execution — 9.0% of requests, 23.6% of tokens.** Agentic loops consume roughly 2.6× their request share in tokens.

Measurable use-cases from your original fourteen: coding (five separate code tags), agent workflows (four agent tags), document processing (Data Extraction 13.8%, Data Transformation 5.4%), consumer (Roleplay & Fiction 10.3%), marketing & creative (Content Writing 4.7%), **customer support (1.8%)**, **research (Research & Reports 0.6%)**, and **finance (Finance & Trading 0.5%)**.

Still unmeasurable: healthcare, legal, manufacturing, public sector, academic/sciences — no corresponding tag exists.

## 3. Open-weight share

Of the thirty highest-volume models: **35.5% open** (MIT, Apache-2.0), **6.0% open-restricted** (bespoke licences), **36.3% unknown** — no public HuggingFace repo matched.

Unknown is deliberately not collapsed into proprietary. Most of that bucket is Anthropic, OpenAI and Google models that genuinely have no open weights, but stating that requires evidence the API doesn't provide, so it stays unknown until the full-registry pass fills it in.

Notable: **OpenAI's gpt-oss-120b is Apache-2.0** and carries real volume — the open/closed split doesn't run along vendor lines as cleanly as the narrative suggests.

## 4. Excluded traffic

**38.1T tokens — 4.79% of visible traffic — excluded** as unattributed: `stealth/ox-alpha` plus cloaked models under OpenRouter's own namespace (`openrouter/owl-alpha`). Vendor, licence and origin are all undisclosed, so they are excluded from every share rather than credited to anyone. The magnitude is reported on the page.

Note this figure is much lower than the single-week snapshot suggested. Ox Alpha was #1 by weekly tokens in late August (20.7T in one week), but over the full 90 days it is 27.2T — it appeared recently and ramped fast.

## 5. Defects found against live data

Three, all now fixed with regression tests:

**The price join was broken.** `rankings-daily` returns dated permaslugs (`deepseek/deepseek-v4-flash-20260423`); `/api/v1/models` keys on undated ids. Joining on `id` matched **14 of 122 models** and produced a spend picture showing Google leading at $12.4M. The correct key is `canonical_slug`, which every registry entry carries. Coverage went from 11% to 98.9%, and the answer inverted completely — Anthropic leads, not Google.

**Licence lookup guessed repository names.** The registry provides `hugging_face_id` directly; guessing from the model id produced 401s on gated repos.

**Rounding inside the computation layer** zeroed every per-model spend value below half a cent. Rounding is a presentation concern.

## 6. What this says about the source document

Every figure in the original market-analysis document is wrong, and the sourcing explains why. It cited `200oksolutions.com` and `pro.stockalarm.io` — aggregators — for numbers now measurable directly:

| Document claim | Measured here |
|---|---|
| DeepSeek 17.6% of token volume | 20.45% |
| Google 12.5% | 8.29% |
| OpenAI 8.4% | 8.60% |
| Anthropic 40% of enterprise spend | 54.15% of estimated routed spend (different metric, different scope) |
| "Tencent Hy3 led with 33M daily tool calls" | Hy3 is 10.7% of tokens; no tool-call metric of that form exists in the API |

The document's directional thesis — a barbell market with Chinese open-weight models dominating volume and Anthropic dominating value — holds up. Its numbers do not.
