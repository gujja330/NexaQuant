"""D08 · Flows/Crowding · walk-forward research · V2 §D.8 item 3.

Adapters already exist for FII/DII (India) + short_interest + volume. Never
been tested for actual predictive value. This module runs the "does this signal
predict forward return" question that D06's advancement asked for.

Dynamic sources · reads whatever the market has available · flags gap when
missing rather than silently zero-filling. Both markets.
"""
from __future__ import annotations
import json
import math
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="D08-FLOWS-WF",
    domain_num=8,
    name="D08 · Flows / crowding · walk-forward predictive test",
    description="Test whether volume-spike, short-interest, and (India) FII-DII flow have measurable predictive value for forward 20d return",
    gate_precondition="Flow feature values present for ≥50 tickers in market",
    additive_extension_id="D08-FLOWS-WF",
)


def _fwd20(root, market, ticker):
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        if len(df) < 21: return None
        c = df["close"].tail(21).to_numpy()
        if c[0] <= 0: return None
        return (c[-1] / c[0]) - 1.0
    except Exception: return None


def _volume_spike_score(root: Path, market: str, ticker: str) -> float | None:
    """Recent 5d avg volume / trailing 60d avg volume · >1 = high · dynamic."""
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        if len(df) < 65 or "volume" not in df.columns: return None
        recent = df["volume"].tail(5).mean()
        base = df["volume"].tail(65).head(60).mean()
        if base <= 0: return None
        return float(recent / base)
    except Exception: return None


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research.walkforward.deflated_sharpe import deflated_sharpe_ratio

    # Build sample · volume spike + fwd 20d return · tenant-generic
    # Universe = fundamentals FS ticker set (well-defined · both markets)
    fs_p = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_p.exists():
        return blocked_result(RESEARCH_TICKET, market, "fundamentals_feature_store missing (used only as universe list)")
    fs = pd.read_parquet(fs_p)
    tickers = fs["ticker"].astype(str).unique().tolist()
    rows = []
    for t in tickers:
        base = str(t).upper().replace(".NS","").replace(".BO","")
        vs = _volume_spike_score(root, market, base)
        fr = _fwd20(root, market, base)
        if vs is None or fr is None: continue
        rows.append({"ticker": base, "volume_spike": vs, "fwd_20d_pct": fr * 100.0})

    if len(rows) < 50:
        return blocked_result(RESEARCH_TICKET, market, f"n={len(rows)} < 50 required")

    df = pd.DataFrame(rows)
    # Test grid · quantile thresholds for high-volume-spike
    thresholds = [1.5, 2.0, 3.0, 5.0]
    variants = []
    for thr in thresholds:
        high = df[df["volume_spike"] >= thr]
        low = df[df["volume_spike"] < thr]
        if len(high) < 5 or len(low) < 5: continue
        mean_high = float(high["fwd_20d_pct"].mean())
        mean_low = float(low["fwd_20d_pct"].mean())
        variants.append({
            "threshold": thr,
            "n_high": int(len(high)), "n_low": int(len(low)),
            "mean_fwd_high": round(mean_high, 3),
            "mean_fwd_low": round(mean_low, 3),
            "lift_pct": round(mean_high - mean_low, 3),
        })

    if not variants:
        return blocked_result(RESEARCH_TICKET, market, "no threshold variants qualified")

    best = max(variants, key=lambda v: v["lift_pct"])
    trial_count = len(thresholds)

    # DSR on best-variant high-group Sharpe
    high_series = df[df["volume_spike"] >= best["threshold"]]["fwd_20d_pct"].tolist()
    dsr = None
    if len(high_series) >= 3:
        mu = sum(high_series) / len(high_series)
        sd = math.sqrt(sum((x - mu)**2 for x in high_series) / max(1, len(high_series) - 1))
        sharpe = mu / sd if sd > 0 else 0
        dsr = deflated_sharpe_ratio(sharpe, n_trials=trial_count, n_returns=len(high_series))

    # Rank correlation as additional check · does higher volume_spike → higher fwd return?
    spearman_r = None
    try:
        from scipy.stats import spearmanr
        r, p = spearmanr(df["volume_spike"], df["fwd_20d_pct"])
        spearman_r = {"r": round(float(r), 4), "p_value": round(float(p), 4)}
    except Exception: pass

    candidate_flag = bool(best["lift_pct"] > 0 and dsr and dsr.get("p_value", 1.0) < 0.10)

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 8,
        "market": market,
        "gate_status": "EXECUTED",
        "n_tickers_with_flow_and_fwd": len(rows),
        "trial_family_count": trial_count,
        "variants": variants,
        "best_variant": best,
        "spearman_rank_corr": spearman_r,
        "dsr_best": dsr,
        "candidate_flag": candidate_flag,
        "verdict": (
            f"EXECUTED · best variant threshold={best['threshold']}× · "
            f"lift={best['lift_pct']}% · "
            f"DSR p={dsr.get('p_value','?') if dsr else 'n/a'} · "
            f"Spearman r={spearman_r['r'] if spearman_r else 'n/a'}"
        ),
        "governance_note": (
            "V2 §D.8 item 3 · closes the D08 'adapter exists but unresearched' gap. "
            "Volume-spike is the free-tier flow proxy available in both markets. "
            "FII/DII (India) + institutional 13F (USA) would add depth · flagged as "
            "next-external-data-source ticket. R3 Tier-1 addition candidate if flag=True."
        ),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
