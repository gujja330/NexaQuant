"""Delivery Paper Portfolios · Runner 1 + Runner 2.

Storage:
  reports/research/runner1/positions.json + history.jsonl
  reports/research/runner2/positions.json + history.jsonl

Each runner's positions.json is a rolling paper-portfolio snapshot:
  ticker · first_seen_date · entry_price · last_seen_date · last_seen_price
  · high_water_price · low_water_price · n_days_active · is_active

history.jsonl appends one event per daily ingest with n_opened/updated/dropped.

Migrated from backend/analytics/head_to_head/engine.py into the permanent
Research Platform namespace. Ingest logic unchanged, path updated.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

SCHEMA_FINGERPRINT = "aegis.research.paper_portfolio.v1.20260731"
ENGINE_ID = "aegis.research.paper_portfolio.v1"

RUNNER1_ACTIVE_STRENGTHS = {"STRONG BUY", "BUY", "ACCUMULATE"}


@dataclass
class PaperPosition:
    ticker: str
    first_seen_date: str
    entry_price: float
    last_seen_date: str
    last_seen_price: float
    high_water_price: float
    low_water_price: float
    n_days_active: int
    is_active: bool = True

    @property
    def cumulative_return_pct(self) -> float:
        if not self.entry_price:
            return 0.0
        return round((self.last_seen_price / self.entry_price - 1.0) * 100, 3)


def _store_dir(root: Path, runner: str) -> Path:
    return root / "reports" / "research" / runner


def _load_positions(root: Path, runner: str) -> dict[str, PaperPosition]:
    p = _store_dir(root, runner) / "positions.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    out: dict[str, PaperPosition] = {}
    for t, rec in (raw.get("positions") or {}).items():
        try:
            out[t] = PaperPosition(**{k: v for k, v in rec.items()
                                       if k in PaperPosition.__dataclass_fields__})
        except TypeError:
            continue
    return out


def _save_positions(root: Path, runner: str, positions: Mapping[str, PaperPosition]) -> None:
    d = _store_dir(root, runner)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":              ENGINE_ID,
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "runner":              runner,
        "written_utc":         datetime.now(timezone.utc).isoformat(),
        "n_positions":         len(positions),
        "positions":           {t: asdict(p) for t, p in positions.items()},
    }
    (d / "positions.json").write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")


def _append_history(root: Path, runner: str, event: dict) -> None:
    d = _store_dir(root, runner)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def _normalize(ticker: str) -> str:
    return str(ticker).split(".", 1)[0].strip().upper() if ticker else ""


def _upsert(positions: dict, ticker: str, price: float, asof: str,
              entry_price_override: float | None = None) -> tuple[str, PaperPosition]:
    if ticker in positions:
        p = positions[ticker]
        # ALWAYS refresh last_seen_price (idempotent mid-day mark-to-market)
        # regardless of whether last_seen_date already equals asof.
        p.last_seen_price = float(price)
        if price > p.high_water_price:
            p.high_water_price = float(price)
        if price < p.low_water_price:
            p.low_water_price = float(price)
        if p.last_seen_date != asof:
            p.last_seen_date = asof
            p.n_days_active += 1
        p.is_active = True
        return "UPDATED", p
    # First-seen: entry_price = prior_close (if provided) so today's move
    # shows non-zero cumulative return. Otherwise fall back to current price.
    entry = float(entry_price_override if entry_price_override else price)
    p = PaperPosition(
        ticker=ticker,
        first_seen_date=asof,
        entry_price=entry,
        last_seen_date=asof,
        last_seen_price=float(price),
        high_water_price=max(entry, float(price)),
        low_water_price=min(entry, float(price)),
        n_days_active=1,
        is_active=True,
    )
    positions[ticker] = p
    return "OPENED", p


def ingest_runner1_picks_for_date(root: Path, asof: str) -> dict:
    """Load Runner 1's picks from data/aegis_today.csv · update paper portfolio.

    Semantics:
      · Entry price = Runner 1 CSV 'Current Price' on first-seen day (locked)
      · On subsequent days, that ticker's last_seen_price is MARKED-TO-MARKET
        from today's daily bar close · so cumulative returns are real, not zero
    """
    csv_path = root / "data" / "aegis_today.csv"
    positions = _load_positions(root, "runner1")
    active_today: set[str] = set()
    n_opened, n_updated = 0, 0
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                strength = str(row.get("Strength", "")).strip().upper()
                if strength not in RUNNER1_ACTIVE_STRENGTHS:
                    continue
                ticker = _normalize(row.get("Stock", ""))
                if not ticker:
                    continue
                try:
                    csv_price = float(row.get("Current Price", 0) or 0)
                except (TypeError, ValueError):
                    csv_price = 0.0
                # Mark-to-market: today's close for last_seen_price;
                # yesterday's close as entry_price (so Day-1 return != 0).
                mtm = _fallback_price(root, ticker) or csv_price
                if mtm <= 0:
                    continue
                prior = _prior_close(root, ticker)
                active_today.add(ticker)
                evt, _ = _upsert(positions, ticker, mtm, asof,
                                    entry_price_override=prior)
                if evt == "OPENED":
                    n_opened += 1
                elif evt == "UPDATED":
                    n_updated += 1
    n_dropped = 0
    for t, p in positions.items():
        if t not in active_today and p.is_active:
            p.is_active = False
            n_dropped += 1
    _save_positions(root, "runner1", positions)
    event = {
        "ts_utc":      datetime.now(timezone.utc).isoformat(),
        "asof":        asof,
        "n_active":    len(active_today),
        "n_opened":    n_opened,
        "n_updated":   n_updated,
        "n_dropped":   n_dropped,
        "n_closed":    n_dropped,
    }
    _append_history(root, "runner1", event)
    return event


def ingest_runner2_picks_for_date(root: Path, asof: str) -> dict:
    """Load Runner 2's picks from reports/recommendations.json · update paper portfolio."""
    recs_path = root / "reports" / "recommendations.json"
    positions = _load_positions(root, "runner2")
    active_today: set[str] = set()
    n_opened, n_updated = 0, 0
    if recs_path.exists():
        try:
            payload = json.loads(recs_path.read_text(encoding="utf-8"))
            for r in payload.get("recommendations") or []:
                ia = r.get("investor_action") or {}
                pact = str(r.get("percentile_action") or "").upper()
                if ia.get("entry") != "BUY" and pact not in ("STRONG_BUY", "BUY"):
                    continue
                ticker = _normalize(r.get("ticker") or "")
                if not ticker:
                    continue
                pp = r.get("position_plan") or {}
                ez = pp.get("entry_zone") or {}
                # Always mark-to-market with today's close · fall back to entry_zone
                mtm = _fallback_price(root, ticker) or ez.get("current_price")
                if not mtm or mtm <= 0:
                    continue
                prior = _prior_close(root, ticker)
                active_today.add(ticker)
                evt, _ = _upsert(positions, ticker, float(mtm), asof,
                                    entry_price_override=prior)
                if evt == "OPENED":
                    n_opened += 1
                elif evt == "UPDATED":
                    n_updated += 1
        except (ValueError, OSError):
            pass
    n_dropped = 0
    for t, p in positions.items():
        if t not in active_today and p.is_active:
            p.is_active = False
            n_dropped += 1
    _save_positions(root, "runner2", positions)
    event = {
        "ts_utc":      datetime.now(timezone.utc).isoformat(),
        "asof":        asof,
        "n_active":    len(active_today),
        "n_opened":    n_opened,
        "n_updated":   n_updated,
        "n_dropped":   n_dropped,
        "n_closed":    n_dropped,
    }
    _append_history(root, "runner2", event)
    return event


def _bar_path(root: Path, ticker: str, market: str) -> Path:
    """Locate the daily bar parquet · India first, then USA."""
    if market == "usa":
        # USA daily bars live at data/raw/us/{TICKER}_D1.parquet
        return root / "data" / "raw" / "us" / f"{ticker}_D1.parquet"
    return root / "data" / "raw" / "india" / f"{ticker}_D1.parquet"


def _fallback_price(root: Path, ticker: str, market: str = "india") -> float | None:
    """Read latest close price · local parquet first, yfinance fallback for USA."""
    try:
        import pandas as pd
    except ImportError:
        return None
    p = _bar_path(root, ticker, market)
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if not df.empty:
                return float(df["close"].iloc[-1])
        except Exception:
            pass
    try:
        import yfinance as yf
        df = yf.download(ticker, period="5d", interval="1d",
                            progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            return None
        close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 3]
        return float(close_col.iloc[-1])
    except Exception:
        return None


def _prior_close(root: Path, ticker: str, market: str = "india") -> float | None:
    """Yesterday's close (or the row before latest) from daily parquet.
    Used as entry_price on first-seen day so today's move shows non-zero.
    Falls back to on-demand yfinance fetch (USA · no local cache)."""
    try:
        import pandas as pd
    except ImportError:
        return None
    p = _bar_path(root, ticker, market)
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if len(df) >= 2:
                return float(df["close"].iloc[-2])
        except Exception:
            pass
    # On-demand yfinance fallback (USA typically has no local cache)
    try:
        import yfinance as yf
        symbol = ticker  # USA tickers already bare
        df = yf.download(symbol, period="10d", interval="1d",
                            progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty or len(df) < 2:
            return None
        # Column may be MultiIndex when threads=False for single symbol
        close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 3]
        try:
            return float(close_col.iloc[-2])
        except Exception:
            return None
    except Exception:
        return None


def ingest_runner2_picks_usa_for_date(root: Path, asof: str) -> dict:
    """USA Runner 2 delivery paper portfolio · reads usa/reports/recommendations.json.
    Stores at reports/research/runner2_usa/positions.json + history.jsonl.
    Runner 1 does NOT cover USA · so only Runner 2 is tracked."""
    recs_path = root / "usa" / "reports" / "recommendations.json"
    positions = _load_positions(root, "runner2_usa")
    active_today: set[str] = set()
    n_opened, n_updated = 0, 0
    if recs_path.exists():
        try:
            payload = json.loads(recs_path.read_text(encoding="utf-8"))
            for r in payload.get("recommendations") or []:
                ia = r.get("investor_action") or {}
                pact = str(r.get("percentile_action") or "").upper()
                if ia.get("entry") != "BUY" and pact not in ("STRONG_BUY", "BUY"):
                    continue
                ticker = _normalize(r.get("ticker") or "")
                if not ticker:
                    continue
                pp = r.get("position_plan") or {}
                ez = pp.get("entry_zone") or {}
                mtm = _fallback_price(root, ticker, "usa") or ez.get("current_price")
                if not mtm or mtm <= 0:
                    continue
                prior = _prior_close(root, ticker, "usa")
                active_today.add(ticker)
                evt, _ = _upsert(positions, ticker, float(mtm), asof,
                                    entry_price_override=prior)
                if evt == "OPENED":
                    n_opened += 1
                elif evt == "UPDATED":
                    n_updated += 1
        except (ValueError, OSError):
            pass
    n_dropped = 0
    for t, p in positions.items():
        if t not in active_today and p.is_active:
            p.is_active = False
            n_dropped += 1
    _save_positions(root, "runner2_usa", positions)
    event = {
        "ts_utc":      datetime.now(timezone.utc).isoformat(),
        "asof":        asof,
        "n_active":    len(active_today),
        "n_opened":    n_opened,
        "n_updated":   n_updated,
        "n_dropped":   n_dropped,
        "n_closed":    n_dropped,
    }
    _append_history(root, "runner2_usa", event)
    return event


def mark_to_market(root: Path, runner: str, prices: Mapping[str, float],
                     asof: str) -> None:
    positions = _load_positions(root, runner)
    for ticker, p in positions.items():
        if not p.is_active:
            continue
        px = prices.get(ticker) or prices.get(_normalize(ticker))
        if px is None or px <= 0:
            continue
        p.last_seen_date = asof
        p.last_seen_price = float(px)
        if px > p.high_water_price:
            p.high_water_price = float(px)
        if px < p.low_water_price:
            p.low_water_price = float(px)
    _save_positions(root, runner, positions)


def compute_head_to_head_summary(root: Path,
                                     experiment_start: str | None = None,
                                     window_days: int = 90) -> dict:
    """Legacy alias for daily rollup · full metrics via metrics.compute_runner_metrics."""
    def _stats(runner: str) -> dict:
        positions = _load_positions(root, runner)
        if not positions:
            return {"n_positions": 0, "cumulative_return_pct": 0.0,
                     "win_rate": 0.0, "n_winners": 0, "n_losers": 0,
                     "n_active": 0, "median_return_pct": 0.0}
        returns = [p.cumulative_return_pct for p in positions.values()]
        winners = [r for r in returns if r > 0]
        cum_return = sum(returns) / len(returns) if returns else 0.0
        median = sorted(returns)[len(returns) // 2] if returns else 0.0
        return {
            "n_positions":               len(positions),
            "n_active":                  sum(1 for p in positions.values() if p.is_active),
            "cumulative_return_pct":     round(cum_return, 3),
            "median_return_pct":         round(median, 3),
            "n_winners":                 len(winners),
            "n_losers":                  len(returns) - len(winners),
            "win_rate":                  round(len(winners) / max(1, len(returns)), 3),
        }

    r1 = _stats("runner1")
    r2 = _stats("runner2")
    diff = r2["cumulative_return_pct"] - r1["cumulative_return_pct"]
    if abs(diff) < 0.5:
        leader = "TIE"
    elif diff > 0:
        leader = "RUNNER_2"
    else:
        leader = "RUNNER_1"
    day_n = 0
    if experiment_start:
        try:
            day_n = (date.today() - date.fromisoformat(experiment_start)).days + 1
        except ValueError:
            pass
    return {
        "engine":              ENGINE_ID,
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "experiment_start":    experiment_start,
        "day_of_window":       day_n,
        "window_days":         window_days,
        "runner1":             r1,
        "runner2":             r2,
        "leader":              leader,
        "leader_edge_pp":      round(diff, 3),
        "canonical":           "UNDECIDED",
    }
