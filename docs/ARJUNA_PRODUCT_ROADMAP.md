# ARJUNA — Product Roadmap (v3.1) — Horizon Modes, Probability Surface, Branches

> The product communicates **probability + distribution**, never a false "target price Rs 350".
> Saying "Hold 6 months · P(profit) 93% · expected +Rs 8,700 · bad case -Rs 1,000 · Confidence HIGH"
> is far more honest and useful than a single number pretending at certainty.

## Horizon Modes (we label short holds honestly — we do NOT ban them)

| Mode | Horizon | Confidence | Status | What it means |
|---|---|---|---|---|
| **TACTICAL** | ≤ 1 month | LOW | SPECULATION | swing trade; ~coin flip (P 55–64%), no strong claim |
| **OPPORTUNITY** | 1–3 months | MEDIUM | TACTICAL | the edge starts to appear (P 75–86%) |
| **CORE** | ≥ 6 months | HIGH | CORE | the flagship; 90%+ odds (P 93–96%) |

A hold under 6 months is *allowed* — it's just labelled LOW/MEDIUM confidence so it's never
over-sold. The Confidence Engine takes the **weaker** of the regime read and the horizon mode, so
short holds in a weak regime can't masquerade as HIGH confidence.

## Probability Surface (the flagship output — `india/probability_surface.py`)

The fine-grained odds-of-profit curve (champion, on Rs 1,00,000), not just the 1-year number:

```
  1W  55%   2W 60%   1M 64%   2M 75%   3M 80%   4M 86%   6M 93%   9M 94%   1Y 96%
```

`horizon_view()` feeds one horizon into the Confidence Engine; `surface()` prints the whole curve.
This is the single most valuable client-facing artifact: it shows the *shape of certainty*, so the
investor self-selects a horizon they're comfortable with instead of being sold false precision.

## The four branches

| Branch | Horizon | Confidence | Status | Notes |
|---|---|---|---|---|
| **ARJUNA Core** | 6–12 months | HIGH | mature, frozen (v2.2) | the flagship; HRP/EW + regime |
| **ARJUNA OS** | n/a (planner) | — | **highest priority** | Goal Engine · Capital Ladder · Confidence Engine · client-facing |
| **ARJUNA Tactical** | 1 week–3 months | LOW | **research, NOT production** | needs new data (below) |
| **ARJUNA Lab** | — | — | CLOSED | reopens on data triggers (see ARJUNA_V4_ROADMAP.md) |

## The honest short-term statement (corrected)

We do **not** say "no system can ever help at 1 week/1 month." We say:

> With **current public data and current architecture**, 1-week/1-month holds are near coin flips.

A future **ARJUNA Tactical** built on different fuel — options flow, intraday microstructure, order
books, futures positioning, market profile, news embeddings — could change the short-term picture.
That is a research branch, gated by the same reopen protocol, not a production promise.

## Open research idea: Horizon-aware stock selection (⭐⭐⭐⭐⭐⭐, unexplored)

The selection signal that matters may depend on the horizon:
- **~1 month:** momentum tends to dominate.
- **~6 months:** quality + low volatility tend to dominate.
- **~1 year:** regime + HRP construction dominates (what Core already does).

Untested. Belongs in `india/lab/` when explored, A/B'd against the current selector, gated by the
usual DSR/PBO/forward rules. Do not assume it works — it's a hypothesis.

## v3.1 priority order (as set with the user)

1. **Probability Surface** ⭐⭐⭐⭐⭐⭐⭐⭐⭐ — DONE (`probability_surface.py`)
2. **Horizon Modes** ⭐⭐⭐⭐⭐⭐⭐⭐ — DONE (`mode_of()` + Confidence Engine integration)
3. **Confidence Engine integration** ⭐⭐⭐⭐⭐⭐⭐⭐ — DONE (horizon-aware, surface embedded)
4. **Horizon-aware stock selection** ⭐⭐⭐⭐⭐⭐ — research (above), not built
5. **ARJUNA Tactical** ⭐⭐⭐⭐⭐ — research branch, awaits short-term data

Core (6–12 months) remains the flagship product throughout.
