# ARJUNA — Alpha Data Research (the next phase)

> The bottleneck is no longer **algorithms**. It is **information the market hasn't already priced
> into public price history.** So the next phase is NOT "AI Research" — it is **Alpha Data Research.**

## The reframe (why this, why now)

Wrong question: *"Can ARJUNA rank the best stocks each week?"* — answered NO, four times, on price data.

Right question: **"What information do successful weekly/monthly recommendations use that ARJUNA
doesn't?"**

The alpha experiment (`evidence/alpha_ranking.py`) failed with IC ≈ 0 — but every feature in it was
**price-derived** (momentum, low-vol, sector strength). That doesn't mean ranking is impossible; it
means *these widely-known price transforms* don't rank future returns on this data. We have been
proving `price → price` doesn't predict price. Unsurprising. The edge lives in **non-price
information.**

## The product split

| Product | Purpose | Status |
|---|---|---|
| **ARJUNA Portfolio** | protect capital, allocate intelligently (regime + risk construction) | built, excellent |
| **ARJUNA Discover** | weekly **Top-20 + WHY / catalysts / risks / suggested horizon** | future — data-gated |

Discover proposes; Portfolio disposes. Discover generates candidates from *new information*;
Portfolio decides if any actually enter (risk, regime, sizing). Two engines, as institutions run.

## The six research streams (information ARJUNA does NOT have)

| # | Stream | What it adds | Price-derivable? | Priority |
|---|---|---|---|---|
| 1 | **Earnings Engine** | earnings dates, surprise, 4-qtr trend, guidance, margin | NO (new data) | ⭐⭐⭐⭐⭐ |
| 2 | **Relative Strength** | stock vs sector vs Nifty (not raw momentum) | YES (partly tested, low prior) | ⭐⭐⭐ |
| 3 | **Sector Rotation** | which sector is attracting money (scores) | PARTLY (price + flow) | ⭐⭐⭐⭐ |
| 4 | **Institutional Flow** | FII / DII / MF / ETF history (money moves sectors first) | NO (forward collector exists, no history) | ⭐⭐⭐⭐⭐ |
| 5 | **News/Event Engine** | EVENTS (order win, approval, promoter buy, upgrade), not generic sentiment | NO (new data) | ⭐⭐⭐⭐⭐ |
| 6 | **Fundamental Change** | Δ ROE, Δ valuation, revenue *acceleration* (markets react to CHANGE) | NO (PIT fundamentals) | ⭐⭐⭐⭐⭐ |

Honest nuance: streams **2 & 3 are price/derivable** and are *partly* covered by the IC~0 result —
low prior, cheap to re-check, not the frontier. The real value is the **non-price streams (1, 4, 5,
6)** — that's where information the price hasn't absorbed actually lives.

## The new composite score (ONLY after the data arrives)

```
Alpha = Fundamental Improvement + Sector Rotation + Institutional Flow
        + Events + Relative Strength + Risk
```
Note: almost none of these were in the rejected experiment. That is the point.

## The five datasets to acquire (priority order)

1. **Point-in-time fundamentals** (removes look-ahead; powers streams 1 & 6)
2. **Earnings history & estimate revisions** (IBES/Zacks-style)
3. **FII/DII & institutional flow history**
4. **Event database** (orders, approvals, management changes, promoter txns, rating actions)
5. **Sector-rotation indicators** (derivable now; lowest cost)

## The discipline does NOT change

Every stream earns its place the same way (this is not a licence to assume it works):
1. Acquire the dataset · 2. Engineer causal, point-in-time features · 3. Measure **IC vs the target**
(top-quintile over 1M/3M/6M) · 4. Beat random AND the current low-vol selector · 5. Only THEN ML
(LightGBM/CatBoost/ranking) · 6. Rolling OOS → forward paper → production gate.

A stream that lands at IC ~0 (like the price factors) is rejected, regardless of how good the story
sounds. Information first, models last.

## What this renames

The v4 "AI Reopen" signboard is the *mechanism*; **"Alpha Data Research" is the mission.** The
triggers in `ARJUNA_V4_ROADMAP.md` / `india/ai_reopen.py` are these datasets. Until they arrive,
ARJUNA Portfolio stays the product and forward paper stays the only experiment that moves the needle.
