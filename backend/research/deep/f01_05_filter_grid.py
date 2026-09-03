"""Fundamental Filter Grid · CEO 2026-09-03 · turn the 7-filter screenshot
into an actual DSR-deflated experiment · not a hard-coded rule.

Threshold grids per filter (per CEO):
  sales_growth   · [0, 5, 10, 15, 20]%     → but we don't have growth history · flagged
  earnings_growth same                       → same blocker
  ROE            · [5, 10, 15, 20, 25]%    → but ROE not in yfinance snapshot · use ROA proxy
  D/E            · [0.25, 0.5, 1.0, 1.5]   → computable now
  FCF            · positive / negative      → computable now (FCF yield > 0)
  Valuation      · sector-relative percentile  → computable now
  Governance     · promoter pledge > 0     → India-only + limited data

Test each threshold individually · then ONE combination test (all-filters pass).
Trial family count recorded · DSR deflation applied.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result


RESEARCH_TICKET = build_ticket(
    ticket_id="D01-05-FILTER-GRID",
    domain_num=1,
    name="Fundamental Filter Grid · 7-filter test (from screenshot)",
    description="Threshold grids per filter · trailing-20d proxy · DSR deflation applied",
    gate_precondition="FS ≥30 tickers with FCF + IntCov + Piotroski",
    additive_extension_id="D01-05-FILTER-GRID",
)


def _r20d(root, market, ticker):
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


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research.walkforward.deflated_sharpe import deflated_sharpe_ratio

    fs_path = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_path.exists():
        return blocked_result(RESEARCH_TICKET, market, "fundamentals_feature_store missing")
    fs = pd.read_parquet(fs_path)
    fs = fs.sort_values(["ticker","asof"]).drop_duplicates("ticker", keep="last")
    if len(fs) < 20:
        return blocked_result(RESEARCH_TICKET, market, f"FS has {len(fs)} < 20 tickers")

    # Attach 20d trailing return
    fs = fs.copy()
    fs["r20d"] = fs["ticker"].apply(lambda t: _r20d(root, market, t))
    fs_with_ret = fs[fs["r20d"].notna()]
    baseline_mean = float(fs_with_ret["r20d"].mean()) if len(fs_with_ret) else 0.0

    # Threshold grids per filter (only for signals we have data for)
    threshold_tests = {
        "fcf_positive":     ("fcf_yield", [0.0]),                  # >0
        "int_cov_ge_1.5":   ("interest_coverage", [1.5]),           # >=1.5
        "int_cov_ge_3.0":   ("interest_coverage", [3.0]),
        "int_cov_ge_5.0":   ("interest_coverage", [5.0]),
        "piotroski_ge_6":   ("piotroski_f", [6]),
        "piotroski_ge_7":   ("piotroski_f", [7]),
        "piotroski_ge_8":   ("piotroski_f", [8]),
        "altman_ge_1.81":   ("altman_z", [1.81]),                   # safe zone
        "altman_ge_2.99":   ("altman_z", [2.99]),                   # very safe
        "beneish_le_neg1.78": ("beneish_m", [-1.78]),               # NOT flagged
        "sloan_abs_le_0.10": ("sloan_accruals", [0.10]),
        "fcf_yield_ge_0.05":  ("fcf_yield", [0.05]),                # >=5%
        "ev_ebitda_le_15":  ("ev_ebitda", [15]),
        "ev_ebitda_le_10":  ("ev_ebitda", [10]),
    }

    variants = []
    for name, (col, thresholds) in threshold_tests.items():
        if col not in fs.columns: continue
        for thr in thresholds:
            # Direction based on name
            if col == "beneish_m" or col == "ev_ebitda" or (col == "sloan_accruals" and "abs" in name):
                # Filter: value <= threshold (or absolute value for accruals)
                if "abs" in name:
                    passing = fs_with_ret[fs_with_ret[col].abs() <= thr]
                else:
                    passing = fs_with_ret[fs_with_ret[col] <= thr]
            else:
                passing = fs_with_ret[fs_with_ret[col] >= thr]
            if len(passing) < 3: continue
            failing = fs_with_ret[~fs_with_ret["ticker"].isin(passing["ticker"])]
            mean_pass = float(passing["r20d"].mean())
            mean_fail = float(failing["r20d"].mean()) if len(failing) else 0.0
            lift = mean_pass - mean_fail
            variants.append({
                "filter": name, "col": col, "threshold": thr,
                "n_pass": int(len(passing)), "n_fail": int(len(failing)),
                "mean_ret_pass_pct": round(mean_pass * 100, 3),
                "mean_ret_fail_pct": round(mean_fail * 100, 3),
                "lift_pct": round(lift * 100, 3),
            })

    # Combined filter · all six primary filters pass simultaneously
    combined_mask = (
        (fs_with_ret.get("fcf_yield", 0) > 0)
        & (fs_with_ret.get("interest_coverage", 0) >= 1.5)
        & (fs_with_ret.get("piotroski_f", 0) >= 6)
        & (fs_with_ret.get("altman_z", 0) >= 1.81)
        & (fs_with_ret.get("beneish_m", -99) <= -1.78)
    ) if all(c in fs_with_ret.columns for c in ("fcf_yield", "interest_coverage", "piotroski_f", "altman_z", "beneish_m")) else None

    combined = None
    if combined_mask is not None:
        passing = fs_with_ret[combined_mask]
        failing = fs_with_ret[~combined_mask]
        if len(passing) >= 3 and len(failing) >= 3:
            mp = float(passing["r20d"].mean())
            mf = float(failing["r20d"].mean())
            combined = {
                "filter": "COMBINED · fcf>0 + IntCov>=1.5 + Piotroski>=6 + Altman>=1.81 + Beneish<=-1.78",
                "n_pass": int(len(passing)),
                "n_fail": int(len(failing)),
                "mean_ret_pass_pct": round(mp * 100, 3),
                "mean_ret_fail_pct": round(mf * 100, 3),
                "lift_pct": round((mp - mf) * 100, 3),
            }

    trial_count = len(variants) + (1 if combined else 0)

    # Best variant (excluding combined) · then DSR-deflate by trial_count
    if variants:
        best = max(variants, key=lambda v: v["lift_pct"])
        # Sharpe proxy on the passing bucket
        import math
        pass_series = fs_with_ret[fs_with_ret[best["col"]] >= best["threshold"]]["r20d"].tolist() \
            if best["col"] not in ("beneish_m", "ev_ebitda") \
            else fs_with_ret[fs_with_ret[best["col"]] <= best["threshold"]]["r20d"].tolist()
        if pass_series:
            mu = sum(pass_series) / len(pass_series)
            sd = math.sqrt(sum((x-mu)**2 for x in pass_series) / max(1, len(pass_series)-1))
            sharpe = mu/sd if sd > 0 else 0
            dsr = deflated_sharpe_ratio(sharpe, n_trials=trial_count, n_returns=len(pass_series))
        else:
            dsr = None
    else:
        best = None; dsr = None

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 1,
        "market": market,
        "gate_status": "EXECUTED",
        "coverage_status": "TRAILING_20D_PROXY · not walk-forward",
        "n_tickers_with_returns": int(len(fs_with_ret)),
        "baseline_mean_ret_20d_pct": round(baseline_mean * 100, 3),
        "trial_family_count": trial_count,
        "individual_variants": variants,
        "combined_all_filters": combined,
        "best_individual_variant": best,
        "dsr_of_best_deflated_by_trials": dsr,
        "verdict": (
            f"EXECUTED · {trial_count} filter variants tested · " +
            (f"best={best['filter']} lift={best['lift_pct']}%" if best else "no variant qualified") +
            " · TRAILING PROXY · needs walk-forward + real forward returns"
        ),
        "governance_note": (
            "Filter-grid research per CEO 2026-09-03 · turns 7-filter screenshot "
            "into a proper experiment. Trailing-20d used as proxy · true forward-return "
            "test requires historical PIT fundamentals. DSR-deflated by trial count. "
            "No filter promoted · this is directional research only."
        ),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
