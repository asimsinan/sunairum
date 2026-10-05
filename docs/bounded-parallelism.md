# Bounded parallelism for Job A (design note)

**Status:** design only — not implemented. Sequential speed cuts land first
(skip Page Designer LLM, one Executor call, combined Chromium measure+preview).

## Goal

Cut a 14-slide PDF-grounded Job A from ~10–12 min (post sequential cuts) toward
**~5 min**, without one LLM call authoring the whole deck.

## Shape

```
P01 sequential (style seed + diary anchor)
        │
        ▼
wave of k=3–4 workers for P02…PN
        │
        ▼
release compile (unchanged)
```

1. **P01 first** — keeps palette/type continuity and a short diary seed.
2. **Wave of k=3–4** — author remaining slides concurrently. `AuthoringBudget`
   already has a lock; workers share the budget.
3. **Diary** — after P01, each later slide gets only the P01 summary line (not
   a growing chain of prior paints). Continuity is weaker than sequential.
4. **Playwright sidecar** — not in the Celery forked worker. A small daemon or
   per-wave process pool owns Chromium; workers submit HTML and receive
   measure JSON + PNG. In-worker reuse under prefork deadlocks.
5. **OpenRouter rate limits** — k=4 × ~40 s Executor still needs headroom on
   tokens/min; back off on 429 rather than spinning more workers.
6. **Host-lane races** — `resolve_native_host_lanes` is per-slide HTML; safe in
   parallel. Shared `images/` / `preview/.preview.lock` need the existing flock
   (or per-slide lock files).

## Expected wall clock

If Executor stays ~40 s/slide and k=4 after P01:

- Strategist ~90 s (unchanged)
- P01 ~40 s
- Remaining 13 slides ≈ ceil(13/4) × 40 s ≈ **160 s**
- Total ≈ **5 min** (+ Docling in a separate job)

Quality risk: weaker continuity, more host-lane collisions on dense decks,
harder A/B vs sequential logs. Keep `PAGE_DESIGN_LLM=1` available for
title/hero/closing if covers regress.

## Non-goals (this note)

- Batch-HTML (one call for 14 pages)
- Skipping Strategist
- In-worker long-lived Chromium
