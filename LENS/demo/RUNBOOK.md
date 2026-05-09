# LENS Demo Runbook

Operator-facing reference for the 4-to-5-minute hackathon demo. Cross-references `LENS/DEMO_PLAN.md` (narrative + success criteria) and `LENS/IMPLEMENTATION_PLAN.md` §11 (architecture).

## Pre-flight (T minus 30 min)

1. Open the laptop on the demo screen, full brightness, screen lock disabled.
2. Close every Slack / iMessage / Discord client. Disable system notifications.
3. Confirm the network. The demo runs locally; no live LLM call is required for the staged simulation.
4. Ensure `bun install` has been run in `LENS/app/frontend/`.
5. Start the frontend: `cd LENS/app/frontend && bun run dev`.
6. Open the browser to `http://localhost:5173/board/00000000-0000-4000-8000-000000000001`.
7. Open the dashboard tab too as a backup landing page.
8. Press `Reset` once — verify the cold-start stage shows "stage 0 / 11" and 0 candidates.
9. Page through the 11 stages once silently to make sure each step renders. Reset.

## Live demo flow

The board has a stage controller (top of the page). Each press of `Next` advances the demo arc one stage. The narration row shows the operator the pitch beat for that stage.

| Stage | Time | What to say (≤2 sentences) | What the audience sees |
|---|---|---|---|
| 0 | 0:00 | "Cold start. Two seed corpora — YC history and a CS/AI principles catalog — give us five generic predictions. The system starts uncertain." | 5 cards, low V̂/Ĉ, no badges. |
| 1 | 0:30 | "I drop 90 days of HN top posts." | 3 contradiction-shaped candidates appear. The board churns. |
| 2 | 1:15 | "arXiv and Stratechery archives. Watch for the cross-domain transfer — that 💡 chip is a pattern from one domain showing up in another." | Cross-domain candidate appears with pulsing 💡 chip. |
| 3 | 1:20 | "This high-V̂ candidate triggers a CAR evidence dossier. Hermes goes deep across web, papers, and forums." | Dossier ticket appears in side panel, status `queued`. |
| 4 | 1:45 | "Founder interview transcripts — private corpus. Watch the personal-RAG candidate get reinforced across sources." | Dossier moves to `running`. Candidate V̂ jumps. |
| 5 | 2:00 | "Dossier complete. Confidence jumps because every claim is now grounded." | 📚 source badge appears, V̂ tweens to 0.91. |
| 6 | 2:30 | "Synthesizer runs on the dirty set. Two candidates share four sources — they merge into one stronger prediction." | One card collapses; the survivor gets a 🔁 reinforces badge. |
| 7 | 2:45 | "Challenger pass. Weak candidates die. The dossier-grounded candidate survives and gets the ✓ challenged-and-held badge." | 3 candidates strike-through; one provenance-failed; the strong one earns ✓. |
| 8 | 3:15 | "Reveal the YC Summer 2026 RFS — held out, published five days ago. Side-by-side comparison." | Benchmark widget reveals; precision/recall numbers fill in. |
| 9 | 3:45 | "Two of our predictions don't appear in the YC list. They're not noise — they're ahead of YC. Excess can be a leading indicator." | 🚀 ahead-of-YC badge on 2 cards. |
| 10 | 4:00 | "Open the opportunity brief — the artifact a partner reads before approving validation work." | Brief dialog opens with problem, pain owner, evidence, contradictions, why now, assumptions, validation path, verdict buttons. |

End with: "Every score, every badge, every kill traces to a source. That's the product."

Total target: 4:00–4:30. Practice 3x before going live.

## Risk register and fallbacks

| § | Risk | Concrete fallback |
|---|---|---|
| 11.6.a | **Live ingestion is too slow.** | The board uses a mocked simulation; ingestion latency is not on the demo path. If pivoting to real data, run `lens load-corpus <name>` ahead of time (corpus bundles in `LENS/fixtures/corpus/`). |
| 11.6.b | **Dirty-set bug**: state stuck or wrong candidate updates. | Toggle `full re-eval: ON` in the ranking header. The mock simulation does not have this risk; if running on real backend, set `LENS_FULL_REEVAL=1`. |
| 11.6.c | **CAR side-panel iframe disconnect.** | The panel is the native fallback today (no iframe). Kept inline so it can never disconnect. |
| 11.6.d | **Hermes setup fragile.** | Real backend uses `LENS_PREWARM_DOSSIERS=1` to surface pre-computed fixture dossiers within 30–60s. The board demo does not depend on Hermes. |
| 11.6.e | **Ahead-of-YC excess hallucinated.** | Open `LENS/demo/preset_excess.json` for the hand-picked excess predictions. Don't claim anything not in that file. |
| 11.6.f | **Live demo crashes.** | Have `LENS/demo/fallback.mp4` ready (recorded full run with narration). Keep it open in a second tab. |

## Operator's emergency switches

- `Reset` button — restart at cold start. Expect ~0.5s; nothing async to wait for.
- `Prev` button — step back one stage (reapplies the script from scratch up to N-1).
- Click any stage progress dot — jump to that stage directly.
- Refresh page — preserves login, returns to cold start.

## What NOT to say on stage

- "The agents do this." → Say "the system surfaces this", "the lens proposes this".
- "It's an AI brainstormer." → Say "it's a decision-support system for opportunity discovery".
- "We use Claude / GPT / etc." → Say "we use a multi-agent pipeline", talk providers only if a judge asks.
- "It's perfect." → Say "this is what we know, here's what we still need to validate" — the demo's value is honesty about uncertainty.

## What to point at

- Source badges before confidence numbers (provenance > prediction).
- Killed candidates as value (we save validation time).
- The 💡 cross-domain chip when it pulses (this is the demo's "non-obvious" punchline).
- The opportunity brief at the end (the paid artifact).

## Post-demo questions (likely)

| Question | One-line answer |
|---|---|
| Where do the candidates come from? | Three lenses (cross-domain, contradiction, distance-from-focus) running on Sonnet, with retrieval over user corpora and a curated CS/AI catalog. |
| How do you avoid hallucination? | Skeptic-folded Challenger does an AGE provenance audit — claims with no source are flagged `provenance_failed`. |
| Can it handle private data? | Yes. MinIO holds raw blobs; pgvector stores embeddings; nothing leaves the box unless explicitly re-routed to a hosted model. |
| What's the unit of cost? | Cost-per-candidate-shipped-to-brief, tracked in `llm_cost_log`. |
| How fast is it? | ~30s full pipeline on a 100-candidate session; ~5s dirty-set re-eval on a 5-candidate batch. |
| Can we evaluate it? | Yes — the held-out YC RFS reveal is one benchmark; we record precision/recall per stage. |
| What if YC is wrong? | Excess predictions are a feature, not a bug. We track defensible non-overlap in the gold map. |
