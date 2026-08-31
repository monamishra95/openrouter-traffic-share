---
description: Run the full engine loop on the current project (G0 → Scout → Builder → Verifier → Red-team → gates)
---

Orchestrate a build through the engine. Spec authority: `docs/PROTOCOL.md`.

1. **G0 — Spec gate.** Confirm `spec.md` + `acceptance.yaml` exist in the project root with declared tier, build mode, and a `verify` method per criterion (manual ≤40% for the harness's first two projects, ≤20% after). If missing, help the operator write them now — do not proceed without them.
2. **Scout.** Dispatch the `scout` subagent (fan out one per source cluster for independent clusters, in parallel). Deliverable: `factsheet.json`. Do not start building while facts are outstanding for the critical path; keep working on structure that needs no facts.
3. **Builder.** Dispatch the `builder` subagent with spec + factsheet. In `staged` mode, loop stages with per-stage Verifier passes. Builder ends at `ready-for-verification`.
4. **Verifier.** Dispatch the `verifier` subagent **fresh** — pass only spec, factsheet, and the build package; never Builder's transcript. RED → route the report back to Builder, loop (count the cycles; they're a §1.7 metric). GREEN → continue.
5. **Red-team.** Dispatch the `red-team` subagent fresh — artifact + spec only. Score below G4 thresholds (see `agents/red-team/rubric.md`) → back to Builder with the weaknesses; else continue.
6. **Hard gates.** Run `python checks/run_gates.py . --release`. RED → fix, file defect records, re-run.
7. **Close.** Report to the operator: verdicts, scores, cycles-to-green, defects filed. Remind them that `/retro` (Librarian) runs at project close and Mechanic runs on cadence.

Throughout: pause for the operator only on destructive/irreversible actions, real scope changes, or input only they can provide. Ground every progress claim in a tool result.
