"""AEGIS · M-R · M-R1 · Forward Validation Report (Sprint M research).

For every R1/R2/MOMENTUM recommendation (active + closed within 90d),
measure realized/forward returns at +1/+3/+5/+10/+20 trading days from
entry, and segment by runner, decision, investability band.

CEO handover 2026-08-27: "For every R1/R2/Momentum recommendation, what
happened at +1, +3, +5, +10 and +20 trading days, and how does that
compare by investability/quality band?"

Answers whether:
  · higher investability actually produces better forward returns
  · R1 vs R2 differ in realized outcome
  · Momentum (when present) predicts better than R1/R2
  · deep-loss holds (LUPIN-style −10%) historically recover
  · stop policy is empirically appropriate

Under M-R post-lock sandbox rules · reads locked canonical inputs
(opportunity_registry + aegis_history + parquet), writes only to
reports/research/ + reports/global/. No production side effects.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT


ENGINE_ID = "aegis.mr_forward_validation.v0.1"
SCHEMA_FINGERPRINT = "aegis.mr_forward_validation.v0.1.20260827"

FORWARD_HORIZONS = [1, 3, 5, 10, 20]


@dataclass
class Observation:
    """A single (Position ID, forward horizon) observation."""
    ticker:                str
    runner:                str
    market:                str
    entry_date:            str
    entry_price:           float
    exit_date:             Optional[str]
    exit_price:            Optional[float]
    lifecycle_status:      str          # ACTIVE / CLOSED
    investability_band:    str          # QUALITY / OK / MARGINAL / AVOID / PENDING
    fwd_1d_pct:            Optional[float] = None
    fwd_3d_pct:            Optional[float] = None
    fwd_5d_pct:            Optional[float] = None
    fwd_10d_pct:           Optional[float] = None
    fwd_20d_pct:           Optional[float] = None
    realized_pct:          Optional[float] = None
    max_favorable_pct:     Optional[float] = None
    max_adverse_pct:       Optional[float] = None


def _statistical_verdict(n: int) -> str:
    if n < 20:   return "OBSERVATION_ONLY"
    if n < 100:  return "INSUFFICIENT_EVIDENCE"
    return "PRODUCTION_CANDIDATE"


def _wilson_95(k: int, n: int) -> tuple:
    if n <= 0: return (None, None)
    z = 1.96
    p = k / n
    denom = 1 + z*z/n
    centre = p + z*z/(2*n)
    margin = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n)
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return (round(lo*100, 2), round(hi*100, 2))


def _load_parquet(root: Path, ticker: str, market: str):
    import pandas as pd
    clean = ticker.upper().replace(".NS","").replace(".BO","")
    base = "usa/data/raw/us" if market.lower() == "usa" else "data/raw/india"
    p = root / base / f"{clean}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return (df, col)
    except Exception:
        return None


def _fwd_return(df_pair, entry_date: str, horizon_trading_days: int) -> Optional[float]:
    """Forward return N trading days after entry_date's close."""
    if df_pair is None: return None
    df, col = df_pair
    dates_sorted = sorted(df.index)
    try:
        # Find entry_date's index or nearest earlier
        if entry_date in df.index:
            idx = dates_sorted.index(entry_date)
        else:
            earlier = [d for d in dates_sorted if d <= entry_date]
            if not earlier: return None
            idx = dates_sorted.index(earlier[-1])
        fwd_idx = idx + horizon_trading_days
        if fwd_idx >= len(dates_sorted): return None
        entry_close = float(df.loc[dates_sorted[idx], col])
        fwd_close   = float(df.loc[dates_sorted[fwd_idx], col])
        if entry_close <= 0: return None
        return round((fwd_close - entry_close) / entry_close * 100, 3)
    except Exception:
        return None


def _mfe_mae(df_pair, entry_date: str,
             exit_date: Optional[str]) -> tuple:
    """Max Favorable + Max Adverse Excursion from entry to exit (or last bar)."""
    if df_pair is None: return (None, None)
    df, col = df_pair
    dates_sorted = sorted(df.index)
    try:
        if entry_date in df.index:
            i_entry = dates_sorted.index(entry_date)
        else:
            earlier = [d for d in dates_sorted if d <= entry_date]
            if not earlier: return (None, None)
            i_entry = dates_sorted.index(earlier[-1])
        if exit_date and exit_date in df.index:
            i_exit = dates_sorted.index(exit_date)
        elif exit_date:
            _earlier = [d for d in dates_sorted if d <= exit_date]
            i_exit = dates_sorted.index(_earlier[-1]) if _earlier else len(dates_sorted) - 1
        else:
            i_exit = len(dates_sorted) - 1
        window = dates_sorted[i_entry:i_exit + 1]
        entry_close = float(df.loc[dates_sorted[i_entry], col])
        if entry_close <= 0: return (None, None)
        highs = [float(df.loc[d, col]) for d in window]
        mfe = (max(highs) - entry_close) / entry_close * 100
        mae = (min(highs) - entry_close) / entry_close * 100
        return (round(mfe, 3), round(mae, 3))
    except Exception:
        return (None, None)


# Investability lookup · read from investability_shadow_{market}.json
# (broader universe · covers momentum + shadow discoveries) and fall back
# to investability_{market}.json (narrow R1/R2 universe). Current-day
# verdicts approximate at-entry-time verdicts · perfect historical snapshot
# would require preserving investability records per date · deferred to
# later M-R iteration.
_INV_CACHE: dict = {}


def _read_investability_band(root: Path, market: str, ticker: str) -> str:
    _key = market.lower()
    if _key not in _INV_CACHE:
        d: dict = {}
        for fname in (f"investability_shadow_{_key}.json",
                      f"investability_{_key}.json"):
            p = root / "reports" / fname
            if not p.exists(): continue
            try:
                _dd = json.loads(p.read_text(encoding="utf-8"))
                for r in (_dd.get("results") or []):
                    _t = str(r.get("ticker", "")).upper() \
                        .replace(".NS", "").replace(".BO", "")
                    _v = str(r.get("verdict", "")).upper()
                    if _t and _t not in d:   # shadow wins over narrow
                        if "QUALITY" in _v: d[_t] = "QUALITY"
                        elif "OK" in _v: d[_t] = "OK"
                        elif "MARGINAL" in _v: d[_t] = "MARGINAL"
                        elif "AVOID" in _v: d[_t] = "AVOID"
                        else: d[_t] = "PENDING"
            except Exception:
                continue
        _INV_CACHE[_key] = d
    tk_norm = ticker.upper().replace(".NS", "").replace(".BO", "")
    return _INV_CACHE[_key].get(tk_norm, "PENDING")


def compute(root: Path, market: str) -> dict:
    """Build forward-validation observations for one market. Read-only."""
    from backend.research import opportunity_registry as _oreg
    reg = _oreg.load_all(root)
    today = date.today().isoformat()
    cutoff_90d = (date.today() - timedelta(days=90)).isoformat()

    observations = []
    seen_pids: set = set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            pid = getattr(o, "opportunity_id", None) or \
                  f"{o.ticker}_{o.runner}_{o.created_date}"
            if pid in seen_pids: continue
            seen_pids.add(pid)
            cd = str(o.created_date or "")[:10]
            if not cd or cd < cutoff_90d: continue
            df_pair = _load_parquet(root, o.ticker, market)
            if df_pair is None: continue
            df, col = df_pair
            # Entry price · use parquet close on created_date
            try:
                if cd in df.index:
                    ep = float(df.loc[cd, col])
                else:
                    earlier = [d for d in df.index if d <= cd]
                    if not earlier: continue
                    ep = float(df.loc[earlier[-1], col])
            except Exception:
                continue
            xd = str(o.closed_date or "")[:10] if o.closed_date else None
            xp = None
            realized = None
            if xd and xd in df.index:
                try:
                    xp = float(df.loc[xd, col])
                    realized = round((xp - ep) / ep * 100, 3) if ep > 0 else None
                except Exception:
                    pass
            mfe, mae = _mfe_mae(df_pair, cd, xd)
            # Investability band (current-day proxy)
            iv_band = _read_investability_band(root, market, o.ticker)
            obs = Observation(
                ticker=o.ticker.upper().replace(".NS","").replace(".BO",""),
                runner=o.runner.upper().replace("_NEW",""),
                market=market.lower(),
                entry_date=cd,
                entry_price=round(ep, 2),
                exit_date=xd,
                exit_price=round(xp, 2) if xp else None,
                lifecycle_status="CLOSED" if xd else "ACTIVE",
                investability_band=iv_band,
                fwd_1d_pct=_fwd_return(df_pair, cd, 1),
                fwd_3d_pct=_fwd_return(df_pair, cd, 3),
                fwd_5d_pct=_fwd_return(df_pair, cd, 5),
                fwd_10d_pct=_fwd_return(df_pair, cd, 10),
                fwd_20d_pct=_fwd_return(df_pair, cd, 20),
                realized_pct=realized,
                max_favorable_pct=mfe,
                max_adverse_pct=mae,
            )
            observations.append(obs)

    def _cohort_metrics(label: str, obs_list: list) -> dict:
        n = len(obs_list)
        m = {"label": label, "n": n,
             "statistical_verdict": _statistical_verdict(n)}
        for hzn in FORWARD_HORIZONS:
            key = f"fwd_{hzn}d_pct"
            values = [getattr(o, key) for o in obs_list
                      if getattr(o, key) is not None]
            n_h = len(values)
            if n_h == 0:
                m[f"fwd_{hzn}d_avg"] = None
                m[f"fwd_{hzn}d_win_rate_pct"] = None
                m[f"fwd_{hzn}d_win_rate_ci"] = (None, None)
                continue
            m[f"fwd_{hzn}d_n"] = n_h
            m[f"fwd_{hzn}d_avg"] = round(sum(values) / n_h, 3)
            wins = sum(1 for v in values if v > 0.5)
            m[f"fwd_{hzn}d_win_rate_pct"] = round(wins / n_h * 100, 2)
            m[f"fwd_{hzn}d_win_rate_ci"] = _wilson_95(wins, n_h)
        # Realized
        rvals = [o.realized_pct for o in obs_list if o.realized_pct is not None]
        if rvals:
            m["realized_n"] = len(rvals)
            m["realized_avg_pct"] = round(sum(rvals) / len(rvals), 3)
            wins = sum(1 for v in rvals if v > 0.5)
            m["realized_win_rate_pct"] = round(wins / len(rvals) * 100, 2)
        return m

    # Cohort segmentation + re-entry classification via Registry
    _reentry_pids: set = set()
    for opps in reg.values():
        # A ticker+runner with more than one Position ID → later ones are RE-ENTRY
        _by_tk_run = defaultdict(list)
        for o in opps:
            if o.market.lower() != market.lower(): continue
            _key = (o.ticker.upper().replace(".NS","").replace(".BO",""),
                    o.runner.upper().replace("_NEW",""))
            _by_tk_run[_key].append(o)
        for _k, _opps in _by_tk_run.items():
            if len(_opps) <= 1: continue
            _sorted = sorted(_opps, key=lambda x: str(x.created_date or ""))
            for _o_r in _sorted[1:]:   # 2nd, 3rd occurrence = RE-ENTRY
                _pid_r = getattr(_o_r, "opportunity_id", None) or \
                         f"{_o_r.ticker}_{_o_r.runner}_{_o_r.created_date}"
                _reentry_pids.add(_pid_r)

    by_runner = defaultdict(list)
    by_band = defaultdict(list)
    by_runner_band = defaultdict(list)
    by_entry_type = defaultdict(list)   # FIRST vs RE-ENTRY
    for o in observations:
        by_runner[o.runner].append(o)
        by_band[o.investability_band].append(o)
        by_runner_band[(o.runner, o.investability_band)].append(o)
        # Match observation pid to reentry set
        _o_pid_candidates = [
            f"{o.ticker}_{o.runner}_{o.entry_date}",
            f"IND-{o.runner}-{o.ticker}-{o.entry_date.replace('-','')}",
            f"USA-{o.runner}-{o.ticker}-{o.entry_date.replace('-','')}",
        ]
        _is_re = any(any(p in x for x in _reentry_pids) for p in _o_pid_candidates)
        by_entry_type["RE-ENTRY" if _is_re else "FIRST-ENTRY"].append(o)

    # Deep-loss recovery analysis · answers the LUPIN question
    # For observations that reached MAE thresholds, what % subsequently
    # recovered to 0, +5%, +10% (measured by MFE that followed the trough)?
    # We approximate with realized_pct + MFE from the same window.
    def _deep_loss_cohort(threshold: float) -> dict:
        # Observations that had MAE <= -threshold%
        pool = [o for o in observations
                if o.max_adverse_pct is not None
                and o.max_adverse_pct <= -threshold]
        n = len(pool)
        if n == 0:
            return {"threshold_pct": threshold, "n": 0,
                    "verdict": _statistical_verdict(0)}
        # "Recovered to 0" means realized_pct or MFE > 0
        n_recov_0   = sum(1 for o in pool
                          if (o.realized_pct is not None and o.realized_pct > 0)
                          or (o.max_favorable_pct is not None
                              and o.max_favorable_pct > 0))
        n_recov_5   = sum(1 for o in pool
                          if (o.realized_pct is not None and o.realized_pct >= 5)
                          or (o.max_favorable_pct is not None
                              and o.max_favorable_pct >= 5))
        n_eventual_stop = sum(1 for o in pool
                              if o.realized_pct is not None
                              and o.realized_pct <= -5)
        avg_realized = None
        rvals = [o.realized_pct for o in pool if o.realized_pct is not None]
        if rvals:
            avg_realized = round(sum(rvals) / len(rvals), 3)
        return {
            "threshold_pct":               threshold,
            "n":                           n,
            "n_recovered_to_0":            n_recov_0,
            "pct_recovered_to_0":          round(n_recov_0 / n * 100, 2),
            "n_recovered_to_plus5":        n_recov_5,
            "pct_recovered_to_plus5":      round(n_recov_5 / n * 100, 2),
            "n_eventually_stopped_leq_minus5": n_eventual_stop,
            "pct_eventually_stopped":      round(n_eventual_stop / n * 100, 2),
            "avg_realized_pct":            avg_realized,
            "verdict":                     _statistical_verdict(n),
        }

    # Expectancy per cohort (helper)
    def _expectancy(obs_list: list) -> Optional[float]:
        rvals = [o.realized_pct for o in obs_list if o.realized_pct is not None]
        if not rvals: return None
        wins = [v for v in rvals if v > 0.5]
        losses = [v for v in rvals if v < -0.5]
        if not (wins and losses): return round(sum(rvals) / len(rvals), 3)
        wr = len(wins) / len(rvals)
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)
        return round(wr * avg_win + (1 - wr) * avg_loss, 3)

    # MFE / MAE cohorts by runner
    def _mfe_mae_summary(obs_list: list) -> dict:
        mfe_vals = [o.max_favorable_pct for o in obs_list
                    if o.max_favorable_pct is not None]
        mae_vals = [o.max_adverse_pct for o in obs_list
                    if o.max_adverse_pct is not None]
        return {
            "avg_mfe_pct":   round(sum(mfe_vals)/len(mfe_vals), 3) if mfe_vals else None,
            "avg_mae_pct":   round(sum(mae_vals)/len(mae_vals), 3) if mae_vals else None,
            "n_mfe":         len(mfe_vals),
            "n_mae":         len(mae_vals),
            "median_mfe":    round(sorted(mfe_vals)[len(mfe_vals)//2], 3) if mfe_vals else None,
            "median_mae":    round(sorted(mae_vals)[len(mae_vals)//2], 3) if mae_vals else None,
        }

    report = {
        "engine":                  ENGINE_ID,
        "experiment_id":           EXPERIMENT_ID,
        "schema_fingerprint":      SCHEMA_FINGERPRINT,
        "generated_utc":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":                  market.lower(),
        "asof":                    today,
        "n_observations":          len(observations),
        "forward_horizons_days":   FORWARD_HORIZONS,
        "runner_distribution":     dict(Counter(o.runner for o in observations)),
        "band_distribution":       dict(Counter(o.investability_band for o in observations)),
        "entry_type_distribution": dict(Counter(k for k, v in by_entry_type.items() for _ in v)),
        "cohort_ALL":              {**_cohort_metrics("ALL", observations),
                                    "expectancy_pct": _expectancy(observations),
                                    "mfe_mae":        _mfe_mae_summary(observations)},
        "cohort_by_runner":        {r: {**_cohort_metrics(r, obs),
                                        "expectancy_pct": _expectancy(obs),
                                        "mfe_mae":        _mfe_mae_summary(obs)}
                                    for r, obs in by_runner.items()},
        "cohort_by_investability": {b: {**_cohort_metrics(b, obs),
                                        "expectancy_pct": _expectancy(obs)}
                                    for b, obs in by_band.items()},
        "cohort_by_runner_band":   {f"{r}·{b}": {**_cohort_metrics(f"{r}·{b}", obs),
                                                  "expectancy_pct": _expectancy(obs)}
                                    for (r, b), obs in by_runner_band.items()},
        "cohort_by_entry_type":    {t: {**_cohort_metrics(t, obs),
                                        "expectancy_pct": _expectancy(obs),
                                        "mfe_mae":        _mfe_mae_summary(obs)}
                                    for t, obs in by_entry_type.items()},
        "deep_loss_recovery":      {
            "minus_5_pct":   _deep_loss_cohort(5.0),
            "minus_7_5_pct": _deep_loss_cohort(7.5),
            "minus_10_pct":  _deep_loss_cohort(10.0),
            "minus_12_pct":  _deep_loss_cohort(12.0),
            "minus_15_pct":  _deep_loss_cohort(15.0),
        },
    }
    return report


def emit(root: Path, market: str, report: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_forward_validation_{market.lower()}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def emit_global(root: Path, per_market_reports: dict) -> Path:
    p = root / "reports" / "global" / "mr_forward_validation_comparison.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    comp = {
        "engine":        ENGINE_ID,
        "experiment_id": EXPERIMENT_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markets":       list(per_market_reports.keys()),
        "per_market":    {},
    }
    for mkt, rep in per_market_reports.items():
        c = rep.get("cohort_ALL", {})
        comp["per_market"][mkt] = {
            "n_observations":       rep.get("n_observations"),
            "statistical_verdict":  c.get("statistical_verdict"),
            "fwd_5d_avg":           c.get("fwd_5d_avg"),
            "fwd_5d_win_rate_pct":  c.get("fwd_5d_win_rate_pct"),
            "fwd_20d_avg":          c.get("fwd_20d_avg"),
            "fwd_20d_win_rate_pct": c.get("fwd_20d_win_rate_pct"),
            "realized_avg_pct":     c.get("realized_avg_pct"),
        }
    p.write_text(json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(reports: dict):
    print("=" * 90)
    print("M-R1 · FORWARD VALIDATION v0.2 · Sprint M Research Runner (M-R.v0.1)")
    print("=" * 90)
    for mkt, rep in reports.items():
        print(f"\n[{mkt.upper()}] · n_observations={rep['n_observations']}")
        print(f"  runner distribution: {rep.get('runner_distribution')}")
        print(f"  band distribution: {rep.get('band_distribution')}")
        print(f"\n  -- Forward return by runner --")
        for r, m in rep.get("cohort_by_runner", {}).items():
            print(f"  · {r:8s} · n={m['n']:3d} · "
                  f"fwd_5d avg={m.get('fwd_5d_avg')}% WR={m.get('fwd_5d_win_rate_pct')}% · "
                  f"fwd_20d avg={m.get('fwd_20d_avg')}% WR={m.get('fwd_20d_win_rate_pct')}% · "
                  f"[{m['statistical_verdict']}]")
        print(f"\n  -- Forward return by investability band --")
        for b, m in rep.get("cohort_by_investability", {}).items():
            print(f"  · {b:10s} · n={m['n']:3d} · "
                  f"fwd_5d avg={m.get('fwd_5d_avg')}% WR={m.get('fwd_5d_win_rate_pct')}% · "
                  f"fwd_20d avg={m.get('fwd_20d_avg')}% WR={m.get('fwd_20d_win_rate_pct')}% · "
                  f"[{m['statistical_verdict']}]")
        print(f"\n  -- Runner × Investability band --")
        for k, m in rep.get("cohort_by_runner_band", {}).items():
            print(f"  · {k:20s} · n={m['n']:3d} · "
                  f"fwd_5d avg={m.get('fwd_5d_avg')}% WR={m.get('fwd_5d_win_rate_pct')}% · "
                  f"realized_avg={m.get('realized_avg_pct')}% · "
                  f"[{m['statistical_verdict']}]")
        print(f"\n  -- MFE/MAE by runner --")
        for r, m in rep.get("cohort_by_runner", {}).items():
            mm = m.get("mfe_mae", {})
            print(f"  · {r:8s} · n={m['n']:3d} · "
                  f"avg_MFE={mm.get('avg_mfe_pct')}% (med {mm.get('median_mfe')}) · "
                  f"avg_MAE={mm.get('avg_mae_pct')}% (med {mm.get('median_mae')}) · "
                  f"expectancy={m.get('expectancy_pct')}%")
        print(f"\n  -- FIRST-ENTRY vs RE-ENTRY --")
        for t, m in rep.get("cohort_by_entry_type", {}).items():
            mm = m.get("mfe_mae", {})
            print(f"  · {t:12s} · n={m['n']:3d} · "
                  f"fwd_5d avg={m.get('fwd_5d_avg')}% WR={m.get('fwd_5d_win_rate_pct')}% · "
                  f"realized_avg={m.get('realized_avg_pct')}% · "
                  f"expectancy={m.get('expectancy_pct')}%")
        print(f"\n  -- Deep-loss recovery (answers LUPIN question) --")
        dl = rep.get("deep_loss_recovery", {})
        for label, d in dl.items():
            if d.get("n", 0) == 0:
                print(f"  · {label:15s} · n=0"); continue
            print(f"  · {label:15s} · n={d['n']:3d} · "
                  f"recovered→0: {d.get('pct_recovered_to_0')}% · "
                  f"recovered→+5%: {d.get('pct_recovered_to_plus5')}% · "
                  f"eventually stopped (≤-5%): {d.get('pct_eventually_stopped')}% · "
                  f"avg_realized={d.get('avg_realized_pct')}% · "
                  f"[{d.get('verdict')}]")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    _root = Path(".").resolve()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    reports = {}
    for m in markets:
        rep = compute(_root, m)
        p   = emit(_root, m, rep)
        reports[m] = rep
        print(f"[mr_fwd:{m}] emitted · {p}")
    if len(reports) > 1:
        g = emit_global(_root, reports)
        print(f"[mr_fwd:global] {g}")
    render_console(reports)
