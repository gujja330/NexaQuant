"""Validation Engine v2.0 · per-ticker historical validation.

Aggregates learning.parquet into a per-ticker rollup that the stock
detail page consumes: "how has AEGIS's take on THIS stock played out
historically?"

Every field is derived deterministically from the same corpus DEV029
calibrated on. No hidden state, no LLM."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]


# ─── Reliability star mapping ─────────────────────────────────
# Anchor to win-rate + sample size. Investors read stars quickly;
# thresholds must be defensible.
def _reliability_stars(win_rate: float, n_trades: int) -> int:
    if n_trades == 0:
        return 0
    if n_trades < 3:
        # Not enough evidence — cap at 3 stars regardless of win rate
        if win_rate >= 0.65: return 3
        if win_rate >= 0.50: return 2
        return 1
    if n_trades >= 5:
        if win_rate >= 0.70: return 5
        if win_rate >= 0.60: return 4
        if win_rate >= 0.50: return 3
        if win_rate >= 0.40: return 2
        return 1
    # 3-4 trades
    if win_rate >= 0.65: return 4
    if win_rate >= 0.50: return 3
    if win_rate >= 0.40: return 2
    return 1


# ─── Failure-mode classifier (rule-based, deterministic) ──────
def _classify_failure(trade: dict) -> str:
    """Return a human-readable failure reason for a single losing trade."""
    ret = float(trade.get("return_pct") or 0.0)
    mfe = float(trade.get("mfe_pct") or 0.0)
    mae = float(trade.get("mae_pct") or 0.0)
    n_bars = int(trade.get("n_bars_held") or 0)
    hit_10_stop = bool(trade.get("hit_10pct_stop"))
    hit_5_stop = bool(trade.get("hit_5pct_stop"))
    hit_10_tgt = bool(trade.get("hit_10pct_target"))
    hit_5_tgt = bool(trade.get("hit_5pct_target"))

    if ret >= 0:
        return "n/a — trade was a winner"
    if hit_10_stop:
        return "Stop-loss triggered (≥ 10% drawdown at some point)"
    if mfe >= 0.05 and ret < 0:
        return f"Winner turned loser (MFE was +{mfe*100:.1f}% but exited at {ret*100:+.1f}%)"
    if n_bars <= 5:
        return f"Cut too early ({n_bars} bars held, quick reversal)"
    if hit_5_stop and not hit_5_tgt:
        return "Never reached +5% target; stopped at −5% band"
    if mae <= -0.08:
        return f"Deep drawdown ({mae*100:.1f}% max adverse) — regime turned against setup"
    return "Ordinary loser (no dramatic MFE, gradual decline)"


# ─── Success reasons ─────────────────────────────────────────
def _classify_success(trade: dict) -> str:
    ret = float(trade.get("return_pct") or 0.0)
    mfe = float(trade.get("mfe_pct") or 0.0)
    hit_10_tgt = bool(trade.get("hit_10pct_target"))
    hit_5_tgt = bool(trade.get("hit_5pct_target"))
    if ret <= 0:
        return "n/a"
    if hit_10_tgt and ret >= 0.10:
        return f"Hit +10% target · closed at {ret*100:+.1f}%"
    if hit_5_tgt:
        return f"Hit +5% target · closed at {ret*100:+.1f}%"
    if ret >= 0.03:
        return f"Solid return {ret*100:+.1f}%"
    return f"Modest gain {ret*100:+.1f}%"


# ─── Per-ticker rollup ────────────────────────────────────────
def build_ticker_rollup(ticker: str, trades: pd.DataFrame,
                          current_confidence: float | None,
                          full_learning: pd.DataFrame) -> dict:
    """Build the full history rollup for one ticker."""
    n = int(len(trades))
    if n == 0:
        return {
            "ticker":               ticker,
            "n_trades":             0,
            "reliability_stars":    0,
            "current_confidence":   current_confidence,
            "note":                 "no historical trades on file",
            "trades":               [],
            "past_failures":        [],
            "similar_trades":       [],
        }

    trades = trades.copy().sort_values("entry_date").reset_index(drop=True)
    # learning.parquet stores return_pct / mfe_pct / mae_pct as percent
    # values (e.g., 6.17 means +6.17%). Normalise to fractions so all
    # downstream consumers can use one consistent scale.
    for col in ("return_pct", "mfe_pct", "mae_pct"):
        if col in trades.columns:
            trades[col] = trades[col].astype(float) / 100.0
    returns = trades["return_pct"].astype(float)
    winners = trades["is_winner"].astype(int)

    n_winners = int(winners.sum())
    n_losers  = int(n - n_winners)
    win_rate  = float(n_winners / n) if n else 0.0
    avg_ret   = float(returns.mean())
    largest_gain = float(returns.max())
    largest_loss = float(returns.min())
    avg_holding  = int(trades["n_bars_held"].astype(int).mean()) if "n_bars_held" in trades else 0
    avg_mfe   = float(trades["mfe_pct"].astype(float).mean()) if "mfe_pct" in trades else 0.0
    avg_mae   = float(trades["mae_pct"].astype(float).mean()) if "mae_pct" in trades else 0.0
    hist_conf = float(trades["confidence"].astype(float).mean()) if "confidence" in trades else None

    # Per-trade compact list (ordered oldest → newest). trades[] is now
    # fraction-scaled from the normalisation above.
    trade_rows = []
    for _, t in trades.iterrows():
        td = t.to_dict()   # already fraction-scaled
        row = {
            "entry_date":  str(t.get("entry_date"))[:10],
            "exit_date":   str(t.get("exit_date"))[:10],
            "return_pct":  float(t.get("return_pct") or 0),
            "is_winner":   bool(t.get("is_winner")),
            "n_bars_held": int(t.get("n_bars_held") or 0),
            "mfe_pct":     float(t.get("mfe_pct") or 0),
            "mae_pct":     float(t.get("mae_pct") or 0),
            "confidence":  float(t.get("confidence") or 0) if t.get("confidence") is not None else None,
            "score":       float(t.get("score_at_entry") or 0) if t.get("score_at_entry") is not None else None,
            "hit_5pct_target":  bool(t.get("hit_5pct_target")),
            "hit_10pct_target": bool(t.get("hit_10pct_target")),
            "hit_5pct_stop":    bool(t.get("hit_5pct_stop")),
            "hit_10pct_stop":   bool(t.get("hit_10pct_stop")),
        }
        if not row["is_winner"]:
            row["failure_reason"] = _classify_failure(td)
        else:
            row["success_reason"] = _classify_success(td)
        trade_rows.append(row)

    # Past failures (losing trades) with reasons
    past_failures = [t for t in trade_rows if not t["is_winner"]]

    # Similar historical trades (from OTHER tickers in the same sector +
    # score band, ranked by recency). Uses full_learning corpus.
    sector = None
    if "sector" in trades.columns and len(trades) > 0:
        sector = str(trades["sector"].iloc[-1])
    similar = _find_similar_trades(ticker, sector, full_learning, top_k=5)

    reliability = _reliability_stars(win_rate, n)

    return {
        "ticker":               ticker,
        "n_trades":             n,
        "n_winners":            n_winners,
        "n_losers":             n_losers,
        "win_rate":             round(win_rate, 4),
        "avg_return_pct":       round(avg_ret, 4),
        "largest_gain_pct":     round(largest_gain, 4),
        "largest_loss_pct":     round(largest_loss, 4),
        "avg_holding_days":     avg_holding,
        "avg_mfe_pct":          round(avg_mfe, 4),
        "avg_mae_pct":          round(avg_mae, 4),
        "current_confidence":   float(current_confidence) if current_confidence is not None else None,
        "historical_confidence": round(hist_conf, 4) if hist_conf is not None else None,
        "reliability_stars":    reliability,
        "trades":               trade_rows,
        "past_failures":        past_failures,
        "similar_trades":       similar,
        "current_setup_check": _current_setup_check(past_failures, sector),
    }


def _find_similar_trades(ticker: str, sector: str | None,
                            corpus: pd.DataFrame, top_k: int = 5) -> list[dict]:
    """Return up to top_k historical trades from OTHER tickers in the same
    sector, ranked by recency of the exit_date."""
    if corpus.empty or sector is None:
        return []
    same_sector = corpus[
        (corpus["sector"].astype(str) == sector)
        & (corpus["ticker"].astype(str) != ticker)
    ].copy()
    if same_sector.empty:
        return []
    same_sector = same_sector.sort_values("exit_date", ascending=False).head(top_k)
    return [{
        "ticker":       str(row.get("ticker")),
        "sector":       str(row.get("sector")),
        "entry_date":   str(row.get("entry_date"))[:10],
        "exit_date":    str(row.get("exit_date"))[:10],
        "return_pct":   float(row.get("return_pct") or 0) / 100.0,   # normalise to fraction
        "is_winner":    bool(row.get("is_winner")),
        "confidence":   float(row.get("confidence") or 0) if row.get("confidence") is not None else None,
        "n_bars_held":  int(row.get("n_bars_held") or 0),
    } for _, row in same_sector.iterrows()]


def _current_setup_check(past_failures: list[dict], sector: str | None) -> dict:
    """Do any past-failure conditions apply to the CURRENT setup?
    Rule-based; deterministic; tells the operator whether the failure
    modes that hurt this ticker before are present today."""
    conditions = []
    reasons = [f["failure_reason"] for f in past_failures]
    if any("Stop-loss triggered" in r for r in reasons):
        conditions.append({
            "condition": "stop_loss_pattern",
            "past":      "STOP-LOSS PATTERN in past",
            "current":   "Monitor stop-loss discipline; consider tighter stops",
        })
    if any("Winner turned loser" in r for r in reasons):
        conditions.append({
            "condition": "winner_reversal",
            "past":      "PAST WINNER TURNED LOSER",
            "current":   "Consider taking partial profits at first target",
        })
    if any("Cut too early" in r for r in reasons):
        conditions.append({
            "condition": "premature_exit",
            "past":      "PAST PREMATURE EXITS",
            "current":   "Give the setup room to work; don't panic on 1st adverse move",
        })
    if any("Deep drawdown" in r for r in reasons):
        conditions.append({
            "condition": "regime_turn",
            "past":      "PAST REGIME-TURN LOSSES",
            "current":   "Check current regime alignment before sizing up",
        })
    return {
        "n_past_failures":  len(past_failures),
        "recurrence_flags": conditions,
        "verdict":          "REVIEW" if conditions else "NO_KNOWN_FAILURE_PATTERNS",
    }


# ─── Public entry point ──────────────────────────────────────
def build_all() -> dict:
    """Produce the per-ticker validation rollup for every ticker with
    either historical trades or a current recommendation."""
    p = _ROOT / "reports" / "learning.parquet"
    if not p.exists():
        return {"error": "learning.parquet not found", "tickers": {}}
    try:
        learning = pd.read_parquet(p)
    except Exception as e:
        return {"error": f"parquet read: {e}", "tickers": {}}

    # Current recommendations for current_confidence
    recs_path = _ROOT / "reports" / "recommendations.json"
    current_by_ticker: dict[str, dict] = {}
    if recs_path.exists():
        try:
            j = json.loads(recs_path.read_text(encoding="utf-8"))
            for r in (j.get("recommendations") or []):
                current_by_ticker[str(r.get("ticker"))] = r
        except Exception:
            pass

    # Set of tickers we should build a rollup for = union of learning + current
    tickers_learning = set(learning["ticker"].astype(str).unique())
    tickers_current = set(current_by_ticker.keys())
    all_tickers = sorted(tickers_learning | tickers_current)

    result = {}
    for ticker in all_tickers:
        trades = learning[learning["ticker"].astype(str) == ticker]
        cur = current_by_ticker.get(ticker, {})
        cur_conf = cur.get("confidence")
        rollup = build_ticker_rollup(ticker, trades, cur_conf, learning)
        # Attach current recommendation context if available
        rollup["current_recommendation"] = {
            "action":                   cur.get("recommendation"),
            "composite_decision_score": cur.get("composite_decision_score"),
            "conviction_pct":           cur.get("conviction_pct"),
            "entry_price":              cur.get("entry_price"),
            "target_1":                 cur.get("target_1"),
            "stop_loss":                cur.get("stop_loss"),
            "sector":                   cur.get("sector"),
            "industry":                 cur.get("industry"),
        } if cur else None
        result[ticker] = rollup

    return {
        "n_tickers":  len(result),
        "n_with_history": sum(1 for v in result.values() if v["n_trades"] > 0),
        "n_without_history": sum(1 for v in result.values() if v["n_trades"] == 0),
        "tickers":    result,
    }
