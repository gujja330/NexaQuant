# india/exit_reasons.py
"""
EXIT REASON CLASSIFIER — attribute WHY a stock left the portfolio, not just "SELL NOW".

Called by telegram_notify when a symbol is present in the previous snapshot but absent from
today's. Runs a cascade of checks and returns the first matching reason. Never invents; only
uses signals actually observed in the two snapshots + the registry.

Cascade (first match wins):
  HORIZON_COMPLETE  registry mature_date <= today   -> natural exit at end of holding period
  SCORE_BREAKDOWN   last score < 45 (WATCH threshold) or dropped >= 15 points
  ROTATED           same-sector new entrant scored HIGHER than the exiter's last score
  REGIME_DE_RISK    prev-day suggested exposure was higher than today's by >= 10pp
  RISK_BREACH       realized 20d vol jumped one tier (Low->Med, Med->High)
  REBALANCE         fallback: dropped from top-N by portfolio construction

Each exit returns a dict with the reason code, a plain-English one-liner for Telegram, and an
emoji for the tier (🔴 exit, ⚠️ regime/risk, 🔄 rotate, ✅ horizon, 🟠 reduce).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

_TIER = {
    "HORIZON_COMPLETE": ("✅", "TARGET / HORIZON COMPLETE"),
    "SCORE_BREAKDOWN": ("🔴", "EXIT — Score Breakdown"),
    "ROTATED": ("🔄", "ROTATED — replaced by stronger candidate"),
    "REGIME_DE_RISK": ("⚠️", "REGIME DE-RISK — market exposure reduced"),
    "RISK_BREACH": ("🔴", "EXIT — Risk Breach"),
    "REBALANCE": ("🟠", "PORTFOLIO REBALANCE — dropped from top-N"),
}


def _horizon_complete(sym, reg_df, today):
    """True only if a LIVE-source registry row's mature_date has genuinely passed.

    Two guards:
    - Only source=='live' rows count (historical backfill rows all have past mature_dates and
      would false-positive every removed stock).
    - Reject rows where mature_date <= asof — these are degenerate entries from the registry
      logger capping mature at closes.index[-1] when future bars aren't yet available."""
    if reg_df is None or reg_df.empty:
        return False
    if "source" not in reg_df.columns or "mature_date" not in reg_df.columns:
        return False
    rows = reg_df[(reg_df["symbol"] == sym) & (reg_df["source"] == "live")].copy()
    if rows.empty:
        return False
    md = pd.to_datetime(rows["mature_date"], errors="coerce")
    asof = pd.to_datetime(rows["asof"], errors="coerce")
    genuine = rows[md > asof]
    if genuine.empty:
        return False
    latest_md = pd.to_datetime(genuine["mature_date"], errors="coerce").max()
    if pd.isna(latest_md):
        return False
    return latest_md.normalize() <= pd.Timestamp(today).normalize()


def _score_breakdown(sym, prev_row, cur_scores_by_sec):
    if prev_row is None:
        return False, None
    try:
        prev_score = float(prev_row.get("score", prev_row.get("Score /100", 50)))
    except Exception:
        return False, None
    if prev_score < 45:
        return True, f"last score {prev_score:.0f} fell below buy threshold (45)"
    return False, None


def _rotated(sym, prev_row, entries, cur):
    """Same-sector new entrant scored higher than the exiter's last score."""
    if prev_row is None or not entries:
        return False, None
    try:
        prev_score = float(prev_row.get("score", prev_row.get("Score /100", 50)))
    except Exception:
        return False, None
    sec = str(prev_row.get("sector", prev_row.get("Sector", "")))
    for new_sym in entries:
        new_row = cur[cur["symbol"] == new_sym] if "symbol" in cur.columns else cur[cur["Stock"] == new_sym]
        if new_row.empty:
            continue
        new_r = new_row.iloc[0]
        new_sec = str(new_r.get("sector", new_r.get("Sector", "")))
        if new_sec == sec:
            try:
                new_score = float(new_r.get("score", new_r.get("Score /100", 0)))
            except Exception:
                continue
            if new_score >= prev_score - 2:
                return True, f"replaced by {new_sym} ({sec}, score {new_score:.0f} vs {prev_score:.0f})"
    return False, None


def _regime_de_risk(prev_snap, cur_snap, prev_exp, cur_exp):
    if prev_exp is None or cur_exp is None:
        return False, None
    if (prev_exp - cur_exp) >= 0.10:
        return True, f"deploy cut {prev_exp:.0%}→{cur_exp:.0%} (>=10pp)"
    return False, None


def _risk_breach(sym, closes):
    if closes is None or sym not in closes.columns:
        return False, None
    ser = closes[sym].dropna()
    if len(ser) < 60:
        return False, None
    rets = ser.pct_change().dropna()
    vol_now = rets.tail(20).std()
    vol_prev = rets.iloc[-60:-20].std() if len(rets) >= 60 else None
    if vol_prev is None or vol_prev == 0:
        return False, None
    if vol_now / vol_prev >= 1.6:
        return True, f"20d vol jumped {100*(vol_now/vol_prev-1):.0f}% vs prior 40d"
    return False, None


def classify_exit(sym, prev_snap, cur_snap, reg_df=None, closes=None,
                  prev_exp=None, cur_exp=None, today=None, entries=None):
    """Return (code, emoji, headline, detail) for the exit of `sym`.

    prev_snap / cur_snap  DataFrames of prior & current snapshot rows (from aegis_recommendation_db).
    reg_df                aegis_registry rows (for mature_date lookup).
    closes                price DataFrame (for realized-vol check).
    prev_exp / cur_exp    suggested-exposure floats 0-1 (from confidence_engine).
    entries               list of new-entry symbols today (for rotate detection).
    """
    today = today or pd.Timestamp.now().normalize()
    prev_row = None
    if prev_snap is not None and not prev_snap.empty:
        pr = prev_snap[prev_snap["symbol"] == sym] if "symbol" in prev_snap.columns else \
             prev_snap[prev_snap["Stock"] == sym]
        if not pr.empty:
            prev_row = pr.iloc[0]

    if _horizon_complete(sym, reg_df, today):
        emoji, headline = _TIER["HORIZON_COMPLETE"]
        return ("HORIZON_COMPLETE", emoji, headline,
                "holding period reached mature_date — natural cycle end")

    ok, why = _score_breakdown(sym, prev_row, None)
    if ok:
        emoji, headline = _TIER["SCORE_BREAKDOWN"]
        return ("SCORE_BREAKDOWN", emoji, headline, why)

    ok, why = _rotated(sym, prev_row, entries or [], cur_snap if cur_snap is not None else pd.DataFrame())
    if ok:
        emoji, headline = _TIER["ROTATED"]
        return ("ROTATED", emoji, headline, why)

    ok, why = _regime_de_risk(prev_snap, cur_snap, prev_exp, cur_exp)
    if ok:
        emoji, headline = _TIER["REGIME_DE_RISK"]
        return ("REGIME_DE_RISK", emoji, headline, why)

    ok, why = _risk_breach(sym, closes)
    if ok:
        emoji, headline = _TIER["RISK_BREACH"]
        return ("RISK_BREACH", emoji, headline, why)

    emoji, headline = _TIER["REBALANCE"]
    return ("REBALANCE", emoji, headline, "rank fell outside today's top-N by portfolio construction")
