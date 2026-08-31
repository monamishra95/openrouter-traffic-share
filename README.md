# Share of Traffic on OpenRouter

What models developers actually run — measured from OpenRouter's CC BY 4.0 Data API, refreshed daily, with every figure traceable to an API response committed in this repository.

**This is gateway traffic, not market share.** Most enterprise inference goes directly to Anthropic, OpenAI or Google Cloud and never touches a routing gateway.

## Run it

```bash
pip install requests
export OPENROUTER_API_KEY=sk-or-v1-...      # Windows: set OPENROUTER_API_KEY=...
python scripts/fetch_all.py --days 90
python scripts/compute.py --print
```

Then open `index.html` — no build step, no server. It reads `data/computed.json`.

Before there's any data, the page tells you to run the fetch rather than rendering empty charts.

## What it measures

| View | Metric | Source |
|---|---|---|
| Token share | Tokens processed per model and vendor, 90-day window | `/api/v1/datasets/rankings-daily` |
| Request share by task | Share of requests and tokens per task classification | `/api/v1/classifications/task` |
| Estimated spend | **Derived**: tokens × published list price | `rankings-daily` × `/api/v1/models` |
| Open-weight share | Traffic split by model licence | OpenRouter × HuggingFace Hub |
| By app category | Leading apps in coding, productivity, creative, entertainment | `/api/v1/datasets/app-rankings` |
| Routing advisor | Suggested model split and cost for a workload mix | computed from the above |

## Three rules this project is built on

**Unattributed models are excluded from every share.** Models published under an anonymous or stealth provider can't have vendor or licence established. Their volume is reported separately with its magnitude visible — currently a substantial fraction of gateway traffic — so readers can judge the effect rather than having it silently folded into someone's total.

**Tokens from different vendors aren't comparable.** Each provider counts with its own tokenizer. Summing across vendors adds unlike units, which is what every "AI market share by tokens" figure quietly does. Request share is offered alongside as the comparable measure.

**What can't be measured is stated, not estimated.** Industry segmentation — financial services, healthcare, legal, manufacturing, public sector, academic — is structurally invisible to a routing gateway, which sees task type but never caller identity. Those appear in the Known Unknowns panel with the reason, not as invented numbers.

## Data discipline

Raw API responses are committed verbatim under `data/`, each wrapped with its citation, `as_of` timestamp, refresh cadence and content hash. The computation layer (`scripts/compute.py`) never mutates source data. Golden tests in `tests/` recompute shares from a fixed fixture, so the build fails if the rendering layer and the arithmetic ever disagree.

The daily workflow commits only when content genuinely changed — a re-fetch of identical data updates `fetched_at` but not `content_hash`, and that alone doesn't produce a commit.

## Limitations

- **Single-source dependency.** Four of five feeds come from OpenRouter. A licence or API change stops most of this.
- **Gateway sample.** Direct-to-provider enterprise traffic is invisible.
- **List pricing only.** The spend estimate can't see negotiated rates, which are typically lower.
- **The advisor is a starting point.** It knows nothing about latency requirements, compliance, data residency, or your contracts.

## Attribution

Rankings and classification data © OpenRouter, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Each panel carries the citation line with its `as_of` timestamp, as the Data API specifies.

Built with [multi-agent-harness](https://github.com/monamishra95/multi-agent-harness). See `spec.md` and `acceptance.yaml` for the build contract.
