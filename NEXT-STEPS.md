# Next steps

**Phases 1–3 are done with real data.** The dashboard works right now.

**Rotate the API key you pasted into chat** — it's in a transcript. Generate a new one at openrouter.ai and use that below.

---

## Look at it now

Open **`index.html`** in a browser. No install, no server, no key needed — it reads `data/computed.json`, which contains real figures from a 90-day pull.

See **`FINDINGS.md`** for what the data actually says.

## Ship it

```cmd
cd /d "C:\Users\monam\OneDrive\Documents\Claude\Projects\Product Management\openrouter-traffic-share"
git init
git add .
git commit -m "Share of Traffic on OpenRouter — first build with live data"
git branch -M main
```

Create an empty repo at github.com/new named `openrouter-traffic-share` (no README, no .gitignore, no licence), then:

```cmd
git remote add origin https://github.com/monamishra95/openrouter-traffic-share.git
git push -u origin main
```

**Add the secret:** GitHub → Settings → Secrets and variables → Actions → New repository secret → name `OPENROUTER_API_KEY`, value your new key. The daily refresh won't run without it.

**Vercel:** import the repo, framework preset **Other**, no build command, output directory `.`.

## Keep it fresh

The daily workflow re-fetches at 06:00 UTC, recomputes, runs the golden tests against the new data, and commits only if content genuinely changed. You can trigger it manually from the Actions tab.

To refresh locally you'll need Python (python.org, tick "Add python.exe to PATH"):

```cmd
pip install requests
set OPENROUTER_API_KEY=your-new-key
python scripts\fetch_all.py --days 90
python scripts\compute.py --print
python tests\test_compute.py
```

---

## Status

| | |
|---|---|
| Phase 0 — spec + 12 acceptance criteria | Done, G0 satisfied |
| Phase 1 — live taxonomy inventory | **Done** — 29 classifications, 4 macro-categories |
| Phase 2 — provenance join | **Done** — 98.9% price coverage, 10 licences confirmed |
| Phase 3 — dashboard with real data | **Done** — 7 views incl. advisor |
| Phase 4 — verification | Partial: 15 golden tests green, gates GREEN. **Not fresh-context.** |
| Phase 5 — Red-team | **Not done** — needs a fresh-context agent |
| Phases 6–8 | Not started |

## What still needs you

**Phases 4 and 5 done properly.** I verified my own work in the same context that produced it, which is exactly the thing your harness exists to prevent. A real Verifier and Red-team pass means running `/build` in Claude Code so they execute without seeing my reasoning. Given three defects surfaced on first contact with live data, a genuinely independent pass is likely to find more.

**A judgment call I made for you:** cloaked models under `openrouter/*` (owl-alpha, ox-alpha) are excluded alongside `stealth/*`. They have a vendor string but an undisclosed author. Reasonable people could count them as OpenRouter's — worth confirming you agree, since it moves 38.1T tokens.

**Open-weight coverage is partial.** 30 of 122 models classified in this bootstrap pass; 36.3% of volume sits in "unknown". The scheduled workflow covers the full registry and will shrink that considerably.
