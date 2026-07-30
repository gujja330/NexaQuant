"""Historical Backtest · reduced (2y re-rank) + per-year per-runner per-market.

Two functions:
  run_reduced_backtest(root)          · legacy: Runner 2 re-ranks Runner 1
                                          universe · overall + per-year edge
  run_historical_per_year(root, market) · operator's CEO ask: for each year
                                          {2022..2026}, per-runner metrics,
                                          declares yearly winner or TIE

Storage:
  reports/research/backtest_2y.json
  reports/research/historical_per_year_{market}.json

HONEST DISCLOSURE (unchanged from prior version):
  This is a REDUCED backtest. A full historical replay of Runner 2 would
  need feature-snapshot history back to 2022 (partial today) and daily
  NSE-200 candidate selection. What we do: re-rank Runner 1's realized
  universe with Runner 2's ensemble scoring on captured dim_* fields.
"""
from __future__ import annotations

import json
import statistics as st
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.research.backtest_historical.v1.20260731"
ENGINE_ID = "aegis.research.backtest_historical.v1"

DEFAULT_DIM_WEIGHTS = {
    "dim_momentum":      1.0 / 6,
    "dim_trend":         1.0 / 6,
    "dim_rs_nifty":      1.0 / 6,
    "dim_volatility":    1.0 / 6,
    "dim_drawdown":      1.0 / 6,
    "dim_position_52w":  1.0 / 6,
}
TOP_N_PER_YEAR_PCT = 0.20


def _profit_factor(returns) -> float | None:
    wins = sum(r for r in returns if r > 0)
    losses = abs(sum(r for r in returns if r < 0))
    if losses == 0:
        return None
    return round(wins / losses, 3)


@dataclass
class YearlyBacktest:
    year: int
    n_universe: int
    n_runner2_selected: int
    runner1_median_return_pct: float
    runner1_win_rate: float
    runner1_profit_factor: float | None
    runner2_median_return_pct: float
    runner2_win_rate: float
    runner2_profit_factor: float | None
    edge_median_pct: float
    edge_win_rate: float
    winner_this_year: str


@dataclass
class ReducedBacktest2Y:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    method: str = ("REDUCED · Runner 2 re-ranks Runner 1's historical universe "
                    "using ensemble of dim_* fields · does NOT test whether "
                    "Runner 2 would have picked different candidates entirely")
    limitations: list = field(default_factory=list)
    n_trades: int = 0
    per_year: list = field(default_factory=list)
    overall_runner1_median: float = 0.0
    overall_runner2_median: float = 0.0
    overall_edge_pct: float = 0.0
    overall_winner: str = ""
    verdict: str = ""


def compute_reduced_backtest(df, weights: dict | None = None,
                                 top_n_pct: float = TOP_N_PER_YEAR_PCT) -> ReducedBacktest2Y:
    import pandas as pd
    rep = ReducedBacktest2Y(run_utc=datetime.now(timezone.utc).isoformat())
    rep.limitations = [
        "Same candidate universe as Runner 1 (not Runner 2's own selection from NSE 200)",
        "Uses historically captured dim_* values (may have data-labeling issues per Evidence Cycle 1)",
        "Uniform-fallback weights if configs/ensemble_weights_adaptive.yaml missing",
        "Top-N slice per year approximates Runner 2's percentile classifier",
    ]
    if df is None or len(df) == 0:
        rep.verdict = "insufficient_data"
        return rep
    df = df.copy()
    w = weights if weights else DEFAULT_DIM_WEIGHTS
    dim_cols = [c for c in w.keys() if c in df.columns]
    if not dim_cols:
        rep.verdict = "no_dim_columns_available"
        return rep
    df["runner2_score"] = sum(df[c].fillna(0) * w.get(c, 0) for c in dim_cols)
    if "exit_date" not in df.columns:
        rep.verdict = "missing_exit_date"
        return rep
    df["exit_year"] = pd.to_datetime(df["exit_date"], errors="coerce").dt.year
    df = df.dropna(subset=["exit_year", "return_pct"])
    rep.n_trades = int(len(df))
    all_r1: list[float] = []
    all_r2: list[float] = []
    for yr, sub in df.groupby("exit_year"):
        n = int(len(sub))
        if n < 20:
            continue
        n_select = max(3, int(n * top_n_pct))
        r2_selected = sub.nlargest(n_select, "runner2_score")
        r1_returns = sub["return_pct"].tolist()
        r2_returns = r2_selected["return_pct"].tolist()
        r1_median = float(sub["return_pct"].median())
        r2_median = float(r2_selected["return_pct"].median())
        r1_wr = float((sub["return_pct"] > 0).mean())
        r2_wr = float((r2_selected["return_pct"] > 0).mean())
        edge_median = r2_median - r1_median
        winner = "RUNNER_2" if edge_median > 0.5 else "RUNNER_1" if edge_median < -0.5 else "TIE"
        rep.per_year.append(asdict(YearlyBacktest(
            year=int(yr),
            n_universe=n,
            n_runner2_selected=n_select,
            runner1_median_return_pct=round(r1_median, 3),
            runner1_win_rate=round(r1_wr, 4),
            runner1_profit_factor=_profit_factor(r1_returns),
            runner2_median_return_pct=round(r2_median, 3),
            runner2_win_rate=round(r2_wr, 4),
            runner2_profit_factor=_profit_factor(r2_returns),
            edge_median_pct=round(edge_median, 3),
            edge_win_rate=round(r2_wr - r1_wr, 4),
            winner_this_year=winner,
        )))
        all_r1.extend(r1_returns)
        all_r2.extend(r2_returns)
    rep.per_year.sort(key=lambda y: y["year"])
    if all_r1 and all_r2:
        rep.overall_runner1_median = round(st.median(all_r1), 3)
        rep.overall_runner2_median = round(st.median(all_r2), 3)
        rep.overall_edge_pct = round(rep.overall_runner2_median - rep.overall_runner1_median, 3)
        if rep.overall_edge_pct > 0.5:
            rep.overall_winner = "RUNNER_2"
            rep.verdict = "runner2_ensemble_adds_measurable_value"
        elif rep.overall_edge_pct < -0.5:
            rep.overall_winner = "RUNNER_1"
            rep.verdict = "runner1_selection_beats_runner2_reranking"
        else:
            rep.overall_winner = "TIE"
            rep.verdict = "no_meaningful_difference"
    else:
        rep.verdict = "insufficient_yearly_data"
    return rep


def _load_adaptive_weights(root: Path) -> dict | None:
    cfg = root / "configs" / "ensemble_weights_adaptive.yaml"
    if not cfg.exists():
        return None
    try:
        wd = json.loads(cfg.read_text(encoding="utf-8"))
        raw = wd.get("weights") or {}
        MODEL_TO_DIM = {
            "aegis.momentum.v1":         "dim_momentum",
            "aegis.trend.v1":            "dim_trend",
            "aegis.sector_rotation.v1":  "dim_rs_nifty",
            "aegis.mean_reversion.v1":   "dim_volatility",
            "aegis.quality.v1":          "dim_drawdown",
            "aegis.event_driven.v1":     "dim_position_52w",
        }
        weights: dict[str, float] = {}
        for mid, w in raw.items():
            d = MODEL_TO_DIM.get(mid)
            if d:
                weights[d] = float(w)
        total = sum(weights.values()) or 1
        return {k: v / total for k, v in weights.items()}
    except Exception:
        return None


def run_reduced_backtest(root: Path) -> dict:
    import pandas as pd
    out_dir = root / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    lp = root / "reports" / "learning.parquet"
    if not lp.exists():
        return asdict(ReducedBacktest2Y(verdict="learning_parquet_missing"))
    df = pd.read_parquet(lp)
    rep = compute_reduced_backtest(df, weights=_load_adaptive_weights(root))
    (out_dir / "backtest_2y.json").write_text(
        json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return asdict(rep)


def run_historical_per_year(root: Path, market: str = "india") -> dict:
    """Operator's CEO ask · per-year per-runner metrics with yearly winner.

    Output shape:
      {
        market: "india",
        years: [
          {year: 2022, runner1: {...metrics...}, runner2: {...metrics...},
           winner_this_year: "RUNNER_2", edge_pp: 1.2},
          ...
        ],
        overall_winner: "...", verdict: "..."
      }
    """
    import pandas as pd
    out_dir = root / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Runner 1 corpus (learning.parquet · India delivery)
    lp = root / "reports" / "learning.parquet" if market == "india" else \
                root / "usa" / "reports" / "learning.parquet"
    if not lp.exists():
        payload = {"market": market, "verdict": "learning_parquet_missing",
                     "years": [], "overall_winner": None}
        (out_dir / f"historical_per_year_{market}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    df = pd.read_parquet(lp)
    if "exit_date" not in df.columns or "return_pct" not in df.columns:
        payload = {"market": market, "verdict": "missing_columns",
                     "years": [], "overall_winner": None}
        (out_dir / f"historical_per_year_{market}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    weights = _load_adaptive_weights(root) or DEFAULT_DIM_WEIGHTS
    dim_cols = [c for c in weights if c in df.columns]
    if dim_cols:
        df["runner2_score"] = sum(df[c].fillna(0) * weights.get(c, 0) for c in dim_cols)
    else:
        df["runner2_score"] = 0

    df["exit_year"] = pd.to_datetime(df["exit_date"], errors="coerce").dt.year
    df = df.dropna(subset=["exit_year", "return_pct"])

    years_out = []
    r2_wins = 0
    r1_wins = 0
    ties = 0
    for yr, sub in df.groupby("exit_year"):
        n = int(len(sub))
        if n < 20:
            continue
        n_r2 = max(3, int(n * TOP_N_PER_YEAR_PCT))
        r2_sel = sub.nlargest(n_r2, "runner2_score") if dim_cols else sub

        def _metrics(rets):
            wins = [r for r in rets if r > 0]
            return {
                "n":                     len(rets),
                "median_return_pct":     round(float(pd.Series(rets).median()), 3),
                "mean_return_pct":       round(float(pd.Series(rets).mean()), 3),
                "win_rate":              round(len(wins) / max(1, len(rets)), 4),
                "profit_factor":         _profit_factor(rets),
                "n_winners":             len(wins),
                "n_losers":              len(rets) - len(wins),
                "best_return_pct":       round(max(rets) if rets else 0.0, 3),
                "worst_return_pct":      round(min(rets) if rets else 0.0, 3),
            }

        r1_m = _metrics(sub["return_pct"].tolist())
        r2_m = _metrics(r2_sel["return_pct"].tolist())
        edge = round(r2_m["median_return_pct"] - r1_m["median_return_pct"], 3)
        if edge > 0.5:
            winner = "RUNNER_2"; r2_wins += 1
        elif edge < -0.5:
            winner = "RUNNER_1"; r1_wins += 1
        else:
            winner = "TIE"; ties += 1
        years_out.append({
            "year":               int(yr),
            "runner1":            r1_m,
            "runner2":            r2_m,
            "edge_pp":            edge,
            "winner_this_year":   winner,
        })

    years_out.sort(key=lambda y: y["year"])
    if r2_wins > r1_wins:
        overall = "RUNNER_2"
    elif r1_wins > r2_wins:
        overall = "RUNNER_1"
    else:
        overall = "TIE"

    payload = {
        "engine":              ENGINE_ID,
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "market":              market,
        "years":               years_out,
        "year_wins_runner1":   r1_wins,
        "year_wins_runner2":   r2_wins,
        "year_ties":           ties,
        "overall_winner":      overall,
        "verdict":             (f"{overall} won {max(r1_wins, r2_wins)} of "
                                  f"{r1_wins + r2_wins + ties} scored years"
                                  if (r1_wins + r2_wins + ties) else "insufficient_years"),
        "limitations":         [
            "Runner 2 metrics from same-universe re-ranking (not independent selection)",
            "USA corpus tracked separately if usa/reports/learning.parquet exists",
        ],
    }
    (out_dir / f"historical_per_year_{market}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
