# Running Verifier and Red-team for real

Everything is installed. This is the Wave 1 test — the first time the harness runs as designed, with agents that never saw the build reasoning.

## Why this can't be me

I built this artifact. If I also verify it, I'm checking my own work while holding every justification I made for it — which is the specific failure the harness exists to prevent. Verifier and Red-team must run in **fresh context**, dispatched as subagents that receive the spec and the artifact but none of my reasoning.

That requires Claude Code. In this conversation I can only simulate it, and a simulated independence check is worth nothing.

## Setup

Open a terminal in the project and start Claude Code:

```cmd
cd /d "C:\Users\monam\OneDrive\Documents\Claude\Projects\Product Management\openrouter-traffic-share"
claude
```

The `.claude/` folder is already in place with all six agent definitions and the `/build`, `/retro` and `/mechanic` commands.

## Step 1 — Verifier

Don't run `/build` — that would rebuild something that already exists. Dispatch Verifier directly. Paste this:

```
Use the verifier subagent to verify this project.

Read engine/agents/verifier/agent.md for your binding rules. You are running in
fresh context: you have not seen how this was built and must not ask for that
history.

Inputs: spec.md, acceptance.yaml, data/computed.json, index.html,
scripts/compute.py, tests/test_compute.py.

Run both modes:
- Mode A, fact audit: independently re-fetch from the OpenRouter Data API and
  confirm the figures in data/computed.json. Recompute the vendor shares from
  raw token counts and check they match what index.html renders. My key is in
  the OPENROUTER_API_KEY environment variable.
- Mode B, functional: run tests/test_compute.py, run the harness gates, open
  index.html and look at every tab, check the console for errors.

Check all 12 acceptance criteria. Output verification-report.json per
engine/schemas/. Verdict is GREEN or RED, binary. File a defect record in
engine/defects/ for every finding. Report, do not repair.
```

Set the key first so Verifier can re-fetch:

```cmd
set OPENROUTER_API_KEY=your-key
```

## Step 2 — Red-team

Only after Verifier returns. Fresh context again:

```
Use the red-team subagent to review this project.

Read engine/agents/red-team/agent.md and engine/agents/red-team/rubric.md.
Fresh context: you see the artifact and the spec, never the build reasoning.

Persona: a skeptical enterprise architect deciding whether to cite this in a
vendor selection review. Score all 8 rubric lines with quoted evidence. Name
exactly three weaknesses ranked by real-world damage.

The question this has to survive: "isn't this just one gateway's traffic, not
the market?" If the answer isn't already visible on the page, R4 fails.

Output redteam-score.json per engine/schemas/. Flag rubric gaps separately.
```

## Step 3 — Retro

```
/retro
```

Librarian routes every defect the two passes filed, writes lessons into the
responsible agent's memory, and applies the promotion ladder.

## What to expect

Four defects surfaced during the build, three of them only on contact with live data. A genuinely independent pass will probably find more — that's a working harness, not a failing build. Some candidates I'd expect it to catch:

- **Verifier has zero memories.** It has never run, so it carries no earned lessons. Its first pass is also its own bootstrap.
- The open-weight view classifies 30 of 122 models; 36% of volume sits in "unknown".
- The advisor's cost estimates use blended prompt/completion pricing, which is an assumption, not a measurement.
- `data/computed.json` was assembled in a bootstrap pass rather than by `compute.py` — the script and the committed data have not been proven to agree.

That last one is the finding I'd most want an independent reviewer to catch, and it's the reason this step matters.

## Current state of the engine

| Agent | Memories | Defect records |
|---|---|---|
| Scout | 4 | |
| Builder | 8 | |
| Verifier | **0** | |
| Red-team | 2 | |
| Librarian | 4 | |
| Mechanic | **0** | |
| **Total defect log** | | **9 records** |
