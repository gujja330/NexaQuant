# ARJUNA Alpha — Master Research Prompt & Evidence Ledger

The canonical objective for the project. Evidence-driven: nothing is assumed; everything proves
itself through validation. (Companion to [ARJUNA_V2_ARCHITECTURE.md](ARJUNA_V2_ARCHITECTURE.md).)

## Objective
Given **capital · horizon (1M/3M/6M/1Y/3Y) · risk appetite · max-drawdown tolerance**, recommend:
which stocks to buy today, allocation per stock, holding period, expected risk, exit criteria,
confidence, and why.

## The objective, sharpened (post-evidence)
> Do NOT optimize "which stock will double?" — proven not predictable in advance.
> Optimize: **"Which PORTFOLIO gives the highest probability of hitting the target return at
> acceptable risk?"** — institutional, realistic, and what the data supports.

## Core Principle
Never assume returns are predictable. Let evidence decide. Nothing enters production without
surviving: walk-forward · purged CV · embargo · **Deflated Sharpe · PBO · SPA · White Reality Check**.

## Inputs
`capital · horizon · risk_appetite(low/med/high) · max_drawdown · universe=Nifty200 · sector_cap=20% · position_cap=25%`

## To evaluate (full menu — Lab)
- **Models:** Logistic/RF/ExtraTrees/HistGBM/XGBoost/LightGBM/CatBoost/SVM · XGBRanker/LambdaMART ·
  LSTM/GRU/Transformer/PatchTST/Chronos · PPO/DQN/SAC · GCN/GAT · HMM/GMM · Cox/DeepSurv
- **Targets:** P(1M>10%), P(3M>15%), P(6M>25%) · beat-Nifty / top-decile · volatility / drawdown /
  P(−20%) / tail risk / crash · triple-barrier
- **Portfolio:** EW · inverse-vol · min-var · HRP · risk-budgeting · Black-Litterman · Kelly
- **Explain:** SHAP · permutation · gain   **Metrics:** CAGR · Sharpe · Sortino · maxDD · Calmar ·
  hit-ratio · alpha · beta · Information Ratio

## Promotion rule (Lab → Core)
DSR > threshold · PBO acceptable · stable across periods AND universes · survives walk-forward ·
survives BOTH bull and bear markets.

---

## EVIDENCE LEDGER (what's been tested — updated through the validation sprint)
### ✅ Confirmed (in Core)
- **Risk is predictable** — volatility AUC **0.76**, drawdown **0.62**.
- **Portfolio construction matters** — inverse-vol / min-var / **HRP** + **regime + Global Risk** →
  Sharpe **2.04**, maxDD **12.8%** (DSR 0.996, PBO 0.00).
- **News sentiment** useful as a **blow-up filter** (not alpha).

### ❌ Rejected (tested, failed — stay in Lab)
- Return prediction, 13 model families — AUC ≈ 0.50
- **XGBRanker** rank-IC ≈ −0.012 · **Triple-barrier** AUC ≈ 0.456
- **HMM regime** (simple rule beat it) · **PPO** (lost to buy-hold) · **GCN** (0.485)
- **GARCH** (no gain vs trailing vol) · **Vol-targeting** (levers, no Sharpe gain) · **Crash classifier** (0.56, wash)
- Per-horizon "big-move probability" (P(>10/25%)) scored 0.61–0.63 BUT the confirmatory test showed
  it's **symmetric (up≈down) → VOLATILITY in disguise, not direction**. One weak 1M-upside flicker
  (0.61 vs 0.49 down) appeared only in a bull OOS window — not trusted until a bear-market test.

### Net finding
**With CURRENT data, per-stock return has NOT shown predictability (could change with new data); per-stock RISK is.** So the recommendation output is
**basket-level expected return + risk-based allocation + holding-period probabilities** — honest
numbers, not fabricated per-stock "confidence."

## Current bottleneck = DATA, not models
Missing (the real ceiling): point-in-time fundamentals · earnings revisions · insider trades ·
options flow · analyst estimates · historical news · alt-data.

## Architecture split (implemented)
- **ARJUNA Core** (`india/`) — production: risk · regime · Global Risk · breadth · FII/DII · news
  filter · portfolio construction. Goal: max Sharpe, min drawdown.
- **ARJUNA Alpha Lab** (`india/research/`) — research: is per-stock return predictable? Test new
  targets/features/datasets. Evidence decides; promote only on the rule above.

## Final question the system answers
> "I have ₹1 lakh today. Given my horizon and risk tolerance, where do I allocate now, what risk am
> I taking, how long do I hold, and why?"  → delivered by `run_arjuna.py` (dated recommendation +
> hold + target + exit), honestly framed at the portfolio level.

## Gap to fully realize this spec
1. ✅ **DONE** — Input config (risk_appetite low/med/high, max_drawdown, sector/position cap) in
   `config.py`; `run_arjuna.py --risk low|medium|high` applies the profile.
2. ✅ **DONE** — Metrics: Sortino · Calmar · alpha · beta · Information Ratio (in `arjuna_v2.stats`).
3. ✅ **DONE (SHAP)** — `research/explain_shap.py` (native XGBoost SHAP on the risk model).
   SPA / White Reality Check still ⏸ (DSR+PBO already gate strongly).
4. ⏸ Black-Litterman / Kelly / risk-budgeting — optional portfolio variants (HRP already wins).
5. ❗ The DATA unlock (point-in-time fundamentals) — the ONLY thing that could move per-stock return.
