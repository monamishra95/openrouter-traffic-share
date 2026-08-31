---
description: Project-close retro — Librarian routes and closes defects, updates brains, runs the demotion sweep
---

Dispatch the `librarian` subagent to run the project-close retro per `agents/librarian/agent.md`:

1. Route and close every open record in `defects/` (lesson file + regression artifact + benchmark case each).
2. Apply the promotion ladder; make any hard-rule edits with benchmark evidence attached.
3. Run the demotion sweep (rules unfired in 5 projects / 90 days).
4. Update the wave checklist in `README.md` if a wave criterion was met this project.
5. Summarize for the operator: defects routed by class/owner, brains changed (with diffs), anything needing her sign-off (Librarian self-edits, spec amendments like the pending P4 taxonomy proposal).
