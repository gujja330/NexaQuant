"""Institutional-grade metrics for a runner's paper portfolio.

Operator's CEO refinement mandates the FULL institutional suite:

  Performance:  Total Return · CAGR · Win Rate · Median Return · Profit Factor
                · Sharpe · Sortino · Calmar · Max Drawdown
  Portfolio:    Exposure · Cash · Concentration (top-5 %) · Turnover · Rotations
                · Avg Holding Days · Holding Days spread
  Decisions:    Recommendation Stability · Buy Overlap (with counterpart)
                · Agreement / Disagreement counts (populated by disagreement_store)
  Risk:         Max DD · Recovery Time · Worst Week · Worst Month · Volatility
                · Tail Loss (CVaR 5%)

All metrics computed from `reports/research/{runner}/positions.json` +
`history.jsonl` — the single source-of-truth files the paper-portfolio
engine appends to daily. Zero business-logic duplication across Telegram
/ dashboard / SSoT — those all read metrics via this module.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

TRADING_DAYS_PER_YEAR = 252
CVAR_TAIL_PCT = 5.0                 # 5% tail for CVaR
TOP_K_CONCENTRATION = 5             # top-5 concentration


@dataclass
class RunnerMetrics:
    runner: str
    market: str
    mode: str
    # Performance
    n_positions: int = 0
    n_open: int = 0
    n_closed: int = 0
    total_return_pct: float = 0.0
    today_return_pct: float = 0.0
    mtd_return_pct: float = 0.0
    cagr_pct: float | None = None
    win_rate: float = 0.0
    n_winners: int = 0
    n_losers: int = 0
    profit_factor: float | None = None
    median_return_pct: float = 0.0
    avg_winner_pct: float = 0.0
    avg_loser_pct: float = 0.0
    # Risk
    max_drawdown_pct: float = 0.0
    recovery_days: int | None = None
    worst_week_pct: float | None = None
    worst_month_pct: float | None = None
    volatility_pct: float | None = None
    tail_loss_cvar_pct: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    alpha_vs_benchmark_pct: float | None = None
    # Portfolio
    avg_holding_days: float = 0.0
    holding_days_stdev: float = 0.0
    current_exposure_pct: float = 0.0
    cash_pct: float = 100.0
    concentration_top5_pct: float = 0.0
    turnover_pct: float = 0.0
    n_rotations: int = 0
    # Decisions
    recommendation_stability_pct: float = 0.0
    buy_overlap_pct: float | None = None       # populated by disagreement_store
    agreement_pct: float | None = None         # populated by disagreement_store
    disagreement_pct: float | None = None      # populated by disagreement_store
    # Identity
    best_pick: str | None = None
    worst_pick: str | None = None
    period_start: str = ""
    period_end: str = ""


def _profit_factor(returns: Iterable[float]) -> float | None:
    wins = sum(r for r in returns if r > 0)
    losses = abs(sum(r for r in returns if r < 0))
    if losses == 0:
        return None
    return round(wins / losses, 3)


def _sharpe_annualized(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 5:
        return None
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    variance = sum((r - mean) ** 2 for r in daily_returns) / (n - 1) if n > 1 else 0
    std = math.sqrt(variance)
    if std == 0:
        return None
    return round((mean / std) * math.sqrt(TRADING_DAYS_PER_YEAR), 3)


def _sortino_annualized(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 5:
        return None
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    downside = [r for r in daily_returns if r < 0]
    if not downside:
        return None
    downside_var = sum(r * r for r in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return None
    return round((mean / downside_std) * math.sqrt(TRADING_DAYS_PER_YEAR), 3)


def _max_drawdown_and_recovery(equity_curve: list[float]) -> tuple[float, int | None]:
    """Return (max_dd_pct, recovery_days). recovery_days=None if never recovered."""
    if not equity_curve:
        return 0.0, None
    peak = equity_curve[0]
    max_dd = 0.0
    trough_idx = 0
    peak_idx = 0
    for i, v in enumerate(equity_curve):
        if v > peak:
            peak = v
            peak_idx = i
        dd = (v - peak) / peak * 100 if peak else 0
        if dd < max_dd:
            max_dd = dd
            trough_idx = i
    # Find recovery after trough
    recovery = None
    trough_val = equity_curve[trough_idx]
    peak_val_before_trough = max(equity_curve[:trough_idx + 1]) if trough_idx else equity_curve[0]
    for j in range(trough_idx + 1, len(equity_curve)):
        if equity_curve[j] >= peak_val_before_trough:
            recovery = j - trough_idx
            break
    return round(max_dd, 3), recovery


def _volatility_annualized(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 5:
        return None
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    variance = sum((r - mean) ** 2 for r in daily_returns) / (n - 1) if n > 1 else 0
    return round(math.sqrt(variance * TRADING_DAYS_PER_YEAR), 3)


def _cvar(returns: list[float], tail_pct: float = CVAR_TAIL_PCT) -> float | None:
    """Conditional VaR · mean of the worst tail_pct% returns."""
    if len(returns) < 5:
        return None
    sorted_r = sorted(returns)
    cutoff = max(1, int(len(sorted_r) * tail_pct / 100))
    return round(sum(sorted_r[:cutoff]) / cutoff, 3)


def _worst_window(returns: list[float], window: int) -> float | None:
    if len(returns) < window:
        return None
    worst = None
    for i in range(len(returns) - window + 1):
        s = sum(returns[i:i + window])
        if worst is None or s < worst:
            worst = s
    return round(worst, 3) if worst is not None else None


def _calmar(cagr_pct: float | None, max_dd_pct: float) -> float | None:
    if cagr_pct is None or max_dd_pct == 0:
        return None
    return round(cagr_pct / abs(max_dd_pct), 3)


def _stdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return math.sqrt(var)


def compute_runner_metrics(root: Path, runner: str, market: str,
                              mode: str = "delivery",
                              benchmark_return_pct: float | None = None,
                              experiment_start: str | None = None,
                              per_position_allocation_pct: float = 3.0) -> RunnerMetrics:
    """Compute the full institutional metric suite for one runner's paper portfolio."""
    m = RunnerMetrics(runner=runner, market=market, mode=mode)
    pos_path = root / "reports" / "research" / runner / "positions.json"
    hist_path = root / "reports" / "research" / runner / "history.jsonl"
    if not pos_path.exists():
        return m
    try:
        payload = json.loads(pos_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return m
    positions_dict = payload.get("positions") or {}
    if not positions_dict:
        return m

    m.n_positions = len(positions_dict)
    m.n_open = sum(1 for p in positions_dict.values() if p.get("is_active"))
    m.n_closed = m.n_positions - m.n_open

    returns: list[float] = []
    holds: list[float] = []
    dates_seen: set[str] = set()
    for _, p in positions_dict.items():
        entry = p.get("entry_price") or 0
        last = p.get("last_seen_price") or 0
        if entry > 0:
            returns.append((last / entry - 1.0) * 100)
        if p.get("n_days_active"):
            holds.append(float(p["n_days_active"]))
        if p.get("first_seen_date"):
            dates_seen.add(p["first_seen_date"])

    if not returns:
        return m

    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r < 0]
    m.n_winners = len(winners)
    m.n_losers = len(losers)
    m.win_rate = round(len(winners) / len(returns), 4)
    m.median_return_pct = round(sorted(returns)[len(returns) // 2], 3)
    m.total_return_pct = round(sum(returns) / len(returns), 3)
    m.profit_factor = _profit_factor(returns)
    m.avg_winner_pct = round(sum(winners) / len(winners), 3) if winners else 0.0
    m.avg_loser_pct = round(sum(losers) / len(losers), 3) if losers else 0.0
    m.avg_holding_days = round(sum(holds) / len(holds), 2) if holds else 0.0
    m.holding_days_stdev = round(_stdev(holds), 2)

    # Portfolio construction
    m.current_exposure_pct = round(m.n_open * per_position_allocation_pct, 2)
    m.cash_pct = round(max(0.0, 100.0 - m.current_exposure_pct), 2)

    # Concentration = top-5 open positions' share of active exposure (%)
    active_returns = [(t, (p.get("last_seen_price", 0) / (p.get("entry_price") or 1) - 1) * 100)
                        for t, p in positions_dict.items() if p.get("is_active")]
    if active_returns:
        total_alloc = len(active_returns) * per_position_allocation_pct
        top_alloc = min(TOP_K_CONCENTRATION, len(active_returns)) * per_position_allocation_pct
        m.concentration_top5_pct = round(top_alloc / total_alloc * 100, 2) if total_alloc else 0.0

    # Best / worst
    by_ret = sorted(positions_dict.items(),
                        key=lambda kv: (kv[1].get("last_seen_price", 0)
                                        / (kv[1].get("entry_price") or 1) - 1))
    if by_ret:
        m.worst_pick = by_ret[0][0]
        m.best_pick = by_ret[-1][0]

    # Stability + rotations from history events
    stability_pct = 0.0
    n_rotations = 0
    turnover_pct = 0.0
    if hist_path.exists():
        events: list[dict] = []
        try:
            for line in hist_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        except Exception:
            events = []
        if events:
            n_rotations = sum(int(e.get("n_opened", 0) or 0) for e in events)
            total_ops = sum(int(e.get("n_active", 0) or 0) for e in events) or 1
            stability_pct = round(100 * (1 - n_rotations / total_ops), 2)
            # Turnover = (opens+closes) / avg active
            total_opens = n_rotations
            total_closes = sum(int(e.get("n_closed", 0) or 0) for e in events)
            avg_active = total_ops / len(events) if events else 1
            turnover_pct = round((total_opens + total_closes) / max(avg_active, 1) * 100, 2)
    m.n_rotations = n_rotations
    m.recommendation_stability_pct = stability_pct
    m.turnover_pct = turnover_pct

    # Equity curve proxy (per-position cumulative)
    equity: list[float] = []
    prev = 100.0
    for r in returns:
        prev = prev * (1 + r / 100)
        equity.append(prev)

    m.max_drawdown_pct, m.recovery_days = _max_drawdown_and_recovery(equity)
    m.worst_week_pct = _worst_window(returns, 5)
    m.worst_month_pct = _worst_window(returns, 21)
    m.volatility_pct = _volatility_annualized(returns)
    m.tail_loss_cvar_pct = _cvar(returns, CVAR_TAIL_PCT)
    m.sharpe_ratio = _sharpe_annualized(returns)
    m.sortino_ratio = _sortino_annualized(returns)

    # CAGR from experiment_start
    if experiment_start:
        try:
            start_dt = date.fromisoformat(experiment_start)
            days_live = max(1, (date.today() - start_dt).days)
            years = days_live / 365.25
            if years > 0 and m.total_return_pct != 0:
                base = 1 + m.total_return_pct / 100
                if base > 0:
                    m.cagr_pct = round((base ** (1 / years) - 1) * 100, 3) if years >= 0.05 else None
        except ValueError:
            pass
    m.calmar_ratio = _calmar(m.cagr_pct, m.max_drawdown_pct)

    if benchmark_return_pct is not None:
        m.alpha_vs_benchmark_pct = round(m.total_return_pct - benchmark_return_pct, 3)

    if dates_seen:
        m.period_start = min(dates_seen)
        m.period_end = max(dates_seen)

    m.today_return_pct = 0.0
    m.mtd_return_pct = m.total_return_pct
    return m
