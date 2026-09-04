"""Apply the AEGIS Standard Testing Pattern (STP) retroactively to today's
four V2 §D.8 items · report clear WORTH verdicts.

CEO 2026-09-04 · make STP the default for every research/upgrade · no need
to request individually.
"""
from __future__ import annotations
import io, json, sys, math
from datetime import date, timedelta
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.standard_test_pattern import (
    TestResult, STPReport, run_stp, emit_stp_report, format_worth_table,
    LAST_60D_WINDOW, DSR_P_ACCEPTANCE, MIN_SAMPLE,
)


# ── shared T1/T2 stubs ──────────────────────────────────────────────────

def _t1_backend_unit(module_name: str) -> TestResult:
    """Verify module imports and evaluate() is callable."""
    try:
        import importlib
        mod = importlib.import_module(module_name)
        if not hasattr(mod, "evaluate"):
            return TestResult("FAIL", f"{module_name}.evaluate missing")
        return TestResult("PASS", f"module importable · evaluate() present")
    except Exception as e:
        return TestResult("FAIL", f"import error · {str(e)[:100]}")


def _t2_backend_integration(module_name: str, market: str, result_glob: str = None) -> TestResult:
    """Confirm evaluate() has produced a result artifact on real data (avoids
    re-running expensive integration · reads the JSON already emitted)."""
    try:
        if result_glob:
            p = _ROOT / result_glob.format(market=market)
            if not p.exists():
                return TestResult("FAIL", f"no artifact at {result_glob.format(market=market)}")
            import json as _j
            r = _j.loads(p.read_text(encoding="utf-8"))
            if "gate_status" not in r:
                return TestResult("FAIL", "artifact missing gate_status")
            return TestResult("PASS", f"gate_status={r['gate_status']}", metric={"gate": r["gate_status"]})
        # Fallback · import-only check
        import importlib
        importlib.import_module(module_name)
        return TestResult("PASS", "module importable")
    except Exception as e:
        return TestResult("FAIL", f"error · {str(e)[:100]}")


# ── Item 1 · F01-05 OOS ─────────────────────────────────────────────────

def _item1(market: str) -> STPReport:
    mod = "backend.research.deep.f01_05_oos_walkforward"

    def t3():
        try:
            j = json.loads((_ROOT / f"reports/research/deep/f01-05-oos-ticker_{market}.json").read_text(encoding="utf-8"))
        except Exception:
            return TestResult("BLOCKED", "no result file (evaluate must run first)")
        if j.get("gate_status") != "EXECUTED":
            return TestResult("BLOCKED", j.get("blocker_reason") or "gate not executed")
        train = j.get("train_decile_lift") or {}
        test = j.get("test_decile_lift") or {}
        dsr = j.get("dsr_test_top_decile") or {}
        train_lift = train.get("lift_pct", 0)
        test_lift = test.get("lift_pct", 0)
        p = dsr.get("p_value", 1.0) if dsr else 1.0
        if train_lift > 0 and test_lift > train_lift * 0.5 and p < DSR_P_ACCEPTANCE:
            return TestResult("PASS", f"train={train_lift}% test={test_lift}% p={p}",
                                metric={"train_lift": train_lift, "test_lift": test_lift, "p": p})
        return TestResult("FAIL", f"train={train_lift}% test={test_lift}% p={p} · does not clear gate",
                            metric={"train_lift": train_lift, "test_lift": test_lift, "p": p})

    def t4():
        """Forward last-60d test · take last-60d predictions from recommendation_history,
        attach fundamentals composite score, check correlation with realized fwd-20d returns."""
        return _forward_60d_fundamental_composite(market)

    def t5():
        return TestResult("N/A", "research-only · does not touch delivery layer")

    return run_stp("F01-05-OOS", market,
                    lambda: _t1_backend_unit(mod),
                    lambda: _t2_backend_integration(mod, market,
                        result_glob="reports/research/deep/f01-05-oos-ticker_{market}.json"),
                    t3, t4, t5)


# ── Item 2 · D06 P2 regime ranking ──────────────────────────────────────

def _item2(market: str) -> STPReport:
    mod = "backend.research.deep.d06_p2_regime_ranking"

    def t3():
        try:
            j = json.loads((_ROOT / f"reports/research/deep/d06-p2-regime-rank_{market}.json").read_text(encoding="utf-8"))
        except Exception:
            return TestResult("BLOCKED", "no result file")
        if j.get("gate_status") != "EXECUTED":
            return TestResult("BLOCKED", j.get("blocker_reason") or "not executed")
        lift = j.get("lift_best_vs_baseline_pct", 0)
        dsr = j.get("dsr_best") or {}
        p = dsr.get("p_value", 1.0) if dsr else 1.0
        # PASS if best-adjusted lift > 0 AND DSR p<0.10
        if lift > 0 and p < DSR_P_ACCEPTANCE:
            return TestResult("PASS", f"lift={lift}% p={p}", metric={"lift": lift, "p": p})
        return TestResult("FAIL", f"lift={lift}% p={p} · best-adjusted did not beat baseline",
                            metric={"lift": lift, "p": p})

    def t4():
        """Forward last-60d · take last 60 days of recommendation_history · rank top-5
        by (base_score, sector-adjusted-score) · compare realized 20d returns."""
        return _forward_60d_d06_p2(market)

    def t5():
        return TestResult("N/A", "research-only · R2 P2 upgrade requires CEO auth")

    return run_stp("D06-P2", market,
                    lambda: _t1_backend_unit(mod),
                    lambda: _t2_backend_integration(mod, market,
                        result_glob="reports/research/deep/d06-p2-regime-rank_{market}.json"),
                    t3, t4, t5)


# ── Item 3 · D08 flows walk-forward ─────────────────────────────────────

def _item3(market: str) -> STPReport:
    mod = "backend.research.deep.d08_flows_walkforward"

    def t3():
        try:
            j = json.loads((_ROOT / f"reports/research/deep/d08-flows-wf_{market}.json").read_text(encoding="utf-8"))
        except Exception:
            return TestResult("BLOCKED", "no result file")
        if j.get("gate_status") != "EXECUTED":
            return TestResult("BLOCKED", j.get("blocker_reason") or "not executed")
        best = j.get("best_variant") or {}
        lift = best.get("lift_pct", 0)
        dsr = j.get("dsr_best") or {}
        p = dsr.get("p_value", 1.0) if dsr else 1.0
        if lift > 0 and p < DSR_P_ACCEPTANCE:
            return TestResult("PASS", f"lift={lift}% p={p}", metric={"lift": lift, "p": p})
        return TestResult("FAIL",
                            f"lift={lift}% p={p} · volume-spike does not beat baseline",
                            metric={"lift": lift, "p": p, "spearman": j.get("spearman_rank_corr")})

    def t4():
        """Forward last-60d · take tickers predicted in last 60 days from recommendation_history
        · compute their volume-spike + realized 20d return · check lift."""
        return _forward_60d_d08_flows(market)

    def t5():
        return TestResult("N/A", "research-only · would flow into R3 Tier-1 features")

    return run_stp("D08-FLOWS", market,
                    lambda: _t1_backend_unit(mod),
                    lambda: _t2_backend_integration(mod, market,
                        result_glob="reports/research/deep/d08-flows-wf_{market}.json"),
                    t3, t4, t5)


# ── Item 4 · Compounder Watchlist ───────────────────────────────────────

def _item4(market: str) -> STPReport:
    mod = "backend.research.compounder.watchlist_scaffold"

    def t3(): return TestResult("BLOCKED", "LT-COMPOUNDER-01 EXTERNAL_DATA · no 20+yr PIT fundamentals")
    def t4(): return TestResult("BLOCKED", "same · needs multi-decade data before any forward test possible")
    def t5(): return TestResult("N/A", "no delivery integration by design (Part C isolation contract)")

    return run_stp("LT-COMPOUNDER-01", market,
                    lambda: _t1_backend_unit(mod),
                    lambda: _t2_backend_integration(mod, market,
                        result_glob="reports/research/deep/lt-compounder-01_{market}.json"),
                    t3, t4, t5)


# ── shared last-60d prediction data loader ─────────────────────────────

def _load_last60d_predictions(market: str):
    """Return list of {asof, ticker, base_score, sector} from last 60 days of
    recommendation_history · dynamic · both markets."""
    import pandas as pd
    hist_p = (_ROOT / market / "reports/recommendation_history.parquet"
              if market.lower() == "usa"
              else _ROOT / "reports/recommendation_history.parquet")
    if not hist_p.exists(): return []
    hist = pd.read_parquet(hist_p)
    hist["asof_d"] = pd.to_datetime(hist["asof"]).dt.date
    cutoff = date.today() - timedelta(days=LAST_60D_WINDOW)
    last60 = hist[hist["asof_d"] >= cutoff]
    out = []
    for _, row in last60.iterrows():
        recs = row.get("recommendations")
        if isinstance(recs, str):
            try: recs = json.loads(recs)
            except Exception: continue
        elif hasattr(recs, "tolist"):
            recs = recs.tolist()
        if not isinstance(recs, list): continue
        asof = str(row["asof"])[:10]
        for r in recs:
            if not isinstance(r, dict): continue
            t = str(r.get("ticker","")).upper().replace(".NS","").replace(".BO","")
            score = r.get("ensemble_score")
            if not t or score is None: continue
            out.append({"asof": asof, "ticker": t, "base_score": float(score)})
    return out


def _fwd20d(ticker: str, entry_date: str) -> float | None:
    import pandas as pd
    from backend.research._paths import price_parquet_path
    try:
        for m in ("india","usa"):
            p = price_parquet_path(_ROOT, m, ticker)
            if p and p.exists(): break
        else: return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        entry = pd.Timestamp(entry_date)
        after = df[df.index >= entry]
        if after.empty: return None
        entry_price = float(after.iloc[0]["close"])
        if entry_price <= 0: return None
        target_dt = after.index[0] + pd.Timedelta(days=30)
        exit_slice = df[df.index >= target_dt]
        exit_price = float(exit_slice.iloc[0]["close"]) if not exit_slice.empty else float(df["close"].iloc[-1])
        return (exit_price / entry_price - 1.0) * 100.0
    except Exception: return None


def _forward_60d_fundamental_composite(market: str) -> TestResult:
    """T4 for F01-05 · does composite predict fwd-20d of last-60d predicted tickers?"""
    import pandas as pd, math
    fs_p = _ROOT / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_p.exists(): return TestResult("BLOCKED", "no fundamentals FS")
    fs = pd.read_parquet(fs_p)
    fs = fs.sort_values(["ticker","asof"]).drop_duplicates("ticker", keep="last")
    fs["ticker_clean"] = fs["ticker"].astype(str).str.replace(".NS","",regex=False).str.replace(".BO","",regex=False).str.upper()

    preds = _load_last60d_predictions(market)
    if len(preds) < 20: return TestResult("BLOCKED", f"n_last60d_preds={len(preds)} < 20")

    # Fundamental composite from populated cols · dynamic
    cols = [c for c in ("fcf_yield","piotroski_f","interest_coverage") if c in fs.columns]
    if len(cols) < 2: return TestResult("BLOCKED", f"only {cols} populated")
    stats = {c: (fs[c].mean(), fs[c].std()) for c in cols}
    fs_by_ticker = {}
    for _, r in fs.iterrows():
        parts = []
        for c in cols:
            v = r[c]; mu, sd = stats[c]
            if pd.isna(v) or sd == 0: continue
            z = max(-3.0, min(3.0, (v - mu) / sd))
            parts.append(z)
        if parts: fs_by_ticker[r["ticker_clean"]] = sum(parts) / len(parts)

    # Score last-60d predictions with composite · check top vs bottom fwd return
    scored = []
    for p in preds:
        c = fs_by_ticker.get(p["ticker"])
        fr = _fwd20d(p["ticker"], p["asof"])
        if c is None or fr is None: continue
        scored.append({"ticker": p["ticker"], "composite": c, "fwd": fr})
    if len(scored) < 10: return TestResult("BLOCKED", f"n_scored={len(scored)} < 10")

    scored.sort(key=lambda x: -x["composite"])
    n_decile = max(3, len(scored) // 3)   # tercile with small n
    top = scored[:n_decile]; bot = scored[-n_decile:]
    lift = (sum(x["fwd"] for x in top)/len(top)) - (sum(x["fwd"] for x in bot)/len(bot))
    if lift > 0:
        return TestResult("PASS", f"last-60d fund-composite top-tercile lift = +{lift:.2f}% (n={len(scored)})",
                            metric={"lift_pct": round(lift,3), "n_scored": len(scored)})
    return TestResult("FAIL", f"last-60d fund-composite top-tercile lift = {lift:.2f}% (n={len(scored)})",
                        metric={"lift_pct": round(lift,3), "n_scored": len(scored)})


def _forward_60d_d06_p2(market: str) -> TestResult:
    """T4 for D06 P2 · restrict α×β grid re-eval to last-60d of recommendation_history."""
    import pandas as pd
    preds = _load_last60d_predictions(market)
    if len(preds) < 20: return TestResult("BLOCKED", f"n_last60d_preds={len(preds)} < 20")

    # Sector load
    sector_cache_p = _ROOT / "reports" / "sectors_cache.json"
    sector_of = {}
    if sector_cache_p.exists():
        try:
            j = json.loads(sector_cache_p.read_text(encoding="utf-8"))
            m_dict = j.get(market.lower()) or j.get(market.upper()) or {}
            sector_of = {str(k).upper(): str(v) for k, v in m_dict.items()}
        except Exception: pass

    # Attach sector + fwd
    for p in preds:
        p["sector"] = sector_of.get(p["ticker"], "UNKNOWN")
        p["fwd"] = _fwd20d(p["ticker"], p["asof"])
    preds = [p for p in preds if p["fwd"] is not None]

    # Baseline top-5 per day
    df = pd.DataFrame(preds)
    if df.empty: return TestResult("BLOCKED", "no preds with fwd")
    baseline_rets = []; adj_rets = []
    for asof, day in df.groupby("asof"):
        top_base = day.nlargest(5, "base_score")
        baseline_rets.extend(top_base["fwd"].tolist())
        # Sector adjustment (α=0.10 fixed for T4 · not searching grid)
        sec_mean = day.groupby("sector")["fwd"].mean().to_dict()
        n_secs = len(sec_mean)
        sec_rank = {s: i+1 for i,(s,_) in enumerate(sorted(sec_mean.items(), key=lambda x:-x[1]))}
        def _sec_score(s):
            if n_secs <= 1 or s not in sec_rank: return 0.0
            return 1.0 - 2.0*(sec_rank[s]-1)/(n_secs-1)
        day_c = day.copy()
        day_c["adj_score"] = day_c["base_score"] + 0.10 * day_c["sector"].apply(_sec_score)
        top_adj = day_c.nlargest(5, "adj_score")
        adj_rets.extend(top_adj["fwd"].tolist())

    if not baseline_rets or not adj_rets: return TestResult("BLOCKED", "no top-N per day computed")
    b_mean = sum(baseline_rets)/len(baseline_rets)
    a_mean = sum(adj_rets)/len(adj_rets)
    lift = a_mean - b_mean
    if lift > 0:
        return TestResult("PASS", f"last-60d P2 adjusted top-5 = {a_mean:.2f}% vs baseline {b_mean:.2f}% · lift +{lift:.2f}%",
                            metric={"lift_pct": round(lift,3), "n_positions": len(baseline_rets)})
    return TestResult("FAIL", f"last-60d P2 adjusted top-5 = {a_mean:.2f}% vs baseline {b_mean:.2f}% · lift {lift:.2f}%",
                        metric={"lift_pct": round(lift,3), "n_positions": len(baseline_rets)})


def _forward_60d_d08_flows(market: str) -> TestResult:
    """T4 for D08 flows · restrict to tickers predicted in last 60 days · check volume-spike vs fwd."""
    import pandas as pd, math
    preds = _load_last60d_predictions(market)
    if len(preds) < 20: return TestResult("BLOCKED", f"n_last60d_preds={len(preds)} < 20")

    from backend.research.deep.d08_flows_walkforward import _volume_spike_score
    rows = []
    for p in preds:
        vs = _volume_spike_score(_ROOT, market, p["ticker"])
        fr = _fwd20d(p["ticker"], p["asof"])
        if vs is None or fr is None: continue
        rows.append({"vs": vs, "fwd": fr})
    if len(rows) < 20: return TestResult("BLOCKED", f"n_scored={len(rows)} < 20")

    hi = [r for r in rows if r["vs"] >= 1.5]
    lo = [r for r in rows if r["vs"] < 1.5]
    if len(hi) < 3 or len(lo) < 3: return TestResult("BLOCKED", "insufficient high/low split")
    m_hi = sum(r["fwd"] for r in hi)/len(hi)
    m_lo = sum(r["fwd"] for r in lo)/len(lo)
    lift = m_hi - m_lo
    if lift > 0:
        return TestResult("PASS", f"last-60d D08 vol-spike top vs bot lift = +{lift:.2f}%",
                            metric={"lift_pct": round(lift,3), "n_high": len(hi), "n_low": len(lo)})
    return TestResult("FAIL", f"last-60d D08 vol-spike top vs bot lift = {lift:.2f}%",
                        metric={"lift_pct": round(lift,3), "n_high": len(hi), "n_low": len(lo)})


# ── helpers ────────────────────────────────────────────────────────────

def _days_pit_history() -> int:
    """Count distinct asof dates in fundamentals_history · unblocks over time."""
    try:
        import pandas as pd
        p = _ROOT / "reports" / "research" / "fundamentals_history" / "usa.parquet"
        if not p.exists(): return 0
        df = pd.read_parquet(p)
        return int(df["asof"].nunique())
    except Exception:
        return 0


def main():
    reports: list[STPReport] = []
    for market in ("india", "usa"):
        for fn in (_item1, _item2, _item3, _item4):
            r = fn(market)
            reports.append(r)
            emit_stp_report(_ROOT, r)

    # Emit combined summary
    combined = {
        "engine": "aegis_stp_batch",
        "run_utc": reports[0].generated_utc,
        "n_reports": len(reports),
        "reports": [json.loads(json.dumps(r, default=lambda o: o.__dict__)) for r in reports],
        "worth_summary": {r.worth_verdict: sum(1 for x in reports if x.worth_verdict == r.worth_verdict)
                            for r in reports},
    }
    summary_p = _ROOT / "reports" / "research" / "stp" / "batch_summary_2026-09-04.json"
    summary_p.write_text(json.dumps(combined, indent=2, default=str), encoding="utf-8")

    # Print markdown table to stdout
    print(format_worth_table(reports))
    print()
    print(f"batch summary: {summary_p.relative_to(_ROOT)}")
    print(f"WORTH tally: {combined['worth_summary']}")


if __name__ == "__main__":
    main()
