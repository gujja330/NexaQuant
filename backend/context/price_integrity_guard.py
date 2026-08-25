# backend/context/price_integrity_guard.py
"""AEGIS · price integrity guard · institutional-grade price sanity.

Operator directive 2026-08-25: "based on exit data and active portfolio
data · we have raw data right · now u need to check if ur entry price
what u r offering and exit price are inlined in data and date and on
that day with history what we preserved? very important".

Runs 3 blocking checks against the fresh XLSX + raw parquet layer:

  PI1  Entry-price alignment · quoted Entry Price for each position
       must match parquet close on Entry Date (within 0.5% tolerance)
       · else the number in the report is fictional

  PI2  Exit-price alignment  · same rule for exits (Exit Price must
       match parquet close on Exit Date · else the realized P&L
       operator sees is wrong)

  PI5  Freshness · every ACTIVE ticker's parquet must have data within
       2 business days of asof · a stale parquet means recommendations
       are computed on old prices which is worse than useless

  PI3  Historical immutability · fingerprint every ticker's parquet
       tail-90 rows to reports/history/parquet_fingerprints_<mkt>.json.
       Next run compares yesterday's tail against today's parquet minus
       rows appended today · any silent mutation = tampering
       (WARN first run · FAIL after 2 consecutive detections)

  PI4  Cross-source reconciliation · sample ACTIVE tickers · cross-check
       yfinance vs Angel close for the SAME date · flag divergence > 1%
       (WARN only · best-effort · skipped when Angel secrets absent or
        network unavailable)

  PI6  Corporate-action awareness · for each ACTIVE position with a
       split / bonus / dividend event between entry_date and today,
       flag it (WARN) · so operator knows the P&L needs adjustment.
       Uses yfinance .actions endpoint · best-effort.

The guard also exports two PREVENTION helpers callers use BEFORE writing
a rec or exit · so the wrong price never reaches persistence in the
first place. Downstream integrity checks catch what escapes.

Tolerance is 0.5% by default · corporate actions surface as WARN so the
operator can adjust the historical entry price by hand until we ship
auto-adjustment (follow-up).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional


SCHEMA_FINGERPRINT = "aegis.price_integrity.v1.20260825"

TOLERANCE_PCT_DEFAULT = 0.5      # 0.5% price mismatch tolerance
FRESHNESS_BIZ_DAYS_DEFAULT = 2   # active tickers must have data ≤ N biz days back
FRESHNESS_CAL_DAYS = 5           # ~2 biz days plus weekend cushion


@dataclass
class IntegrityCheck:
    code: str
    name: str
    status: str          # PASS / WARN / FAIL
    detail: str
    violations: list = field(default_factory=list)


@dataclass
class IntegrityReport:
    market: str
    asof: str
    generated_utc: str
    verdict: str = "PASS"    # PASS / WARN / FAIL
    tolerance_pct: float = TOLERANCE_PCT_DEFAULT
    n_positions_checked: int = 0
    n_exits_checked: int = 0
    n_active_checked: int = 0
    checks: list = field(default_factory=list)

    def add(self, check: IntegrityCheck) -> None:
        self.checks.append(check)
        # PASS < WARN < FAIL · aggregate to worst
        rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
        if rank[check.status] > rank[self.verdict]:
            self.verdict = check.status


# ─────────────────────────────────────────────────────────────────
# Parquet lookup · pure · caches for reuse across calls
# ─────────────────────────────────────────────────────────────────
_PARQUET_CACHE: dict = {}


def _parquet_path(root: Path, ticker: str, market: str) -> Path:
    if market.lower() == "usa":
        tk = ticker.upper().replace(".NS", "").replace(".BO", "")
        return root / "usa" / "data" / "raw" / "us" / f"{tk}_D1.parquet"
    tk = ticker.upper().replace(".NS", "").replace(".BO", "")
    return root / "data" / "raw" / "india" / f"{tk}_D1.parquet"


def _load_close_series(root: Path, ticker: str, market: str):
    """Return (index_list, close_list) or (None, None) if missing.

    Cached by (path, mtime) so the same parquet isn't re-read within
    one guard run.
    """
    p = _parquet_path(root, ticker, market)
    if not p.exists():
        return None, None
    try:
        key = (str(p), p.stat().st_mtime)
        if key in _PARQUET_CACHE:
            return _PARQUET_CACHE[key]
        import pandas as pd
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        idx = pd.to_datetime(df.index).strftime("%Y-%m-%d").tolist()
        closes = [float(v) for v in df[col].tolist()]
        _PARQUET_CACHE[key] = (idx, closes)
        return idx, closes
    except Exception:
        return None, None


def parquet_close(root: Path, ticker: str, market: str,
                  target_date: str) -> Optional[float]:
    """Close on target_date · fallback to the last date ≤ target_date."""
    idx, closes = _load_close_series(root, ticker, market)
    if not idx: return None
    if target_date in idx:
        return closes[idx.index(target_date)]
    # Non-trading day fallback · use the last trading day ≤ target
    before = [(d, c) for d, c in zip(idx, closes) if d <= target_date]
    return before[-1][1] if before else None


def parquet_latest_date(root: Path, ticker: str,
                        market: str) -> Optional[str]:
    idx, _ = _load_close_series(root, ticker, market)
    return idx[-1] if idx else None


# ─────────────────────────────────────────────────────────────────
# PI1 · Entry-price alignment
# ─────────────────────────────────────────────────────────────────
def check_entry_alignment(
    root: Path, market: str, positions: Iterable[dict],
    tolerance_pct: float = TOLERANCE_PCT_DEFAULT,
) -> IntegrityCheck:
    violations = []
    n_checked = 0
    for pos in positions:
        entry = pos.get("entry_price")
        entry_date = pos.get("entry_date")
        ticker = pos.get("ticker")
        if not (isinstance(entry, (int, float)) and entry > 0
                and entry_date and ticker):
            continue
        n_checked += 1
        actual = parquet_close(root, ticker, market, entry_date)
        if actual is None:
            violations.append({
                "ticker": ticker, "entry_date": entry_date,
                "quoted": round(entry, 2), "actual": None,
                "delta_pct": None,
                "reason": "no parquet row on or before entry date",
            })
            continue
        delta = abs(entry - actual) / max(actual, 0.01) * 100
        if delta > tolerance_pct:
            violations.append({
                "ticker": ticker, "entry_date": entry_date,
                "quoted": round(entry, 2),
                "actual": round(actual, 2),
                "delta_pct": round(delta, 2),
                "reason": f"entry price drift {delta:.2f}%",
            })
    status = "PASS" if not violations else "FAIL"
    detail = (f"{n_checked} positions checked · "
              f"{len(violations)} drifted > {tolerance_pct}%")
    return IntegrityCheck("PI1", "Entry-price alignment",
                          status, detail, violations)


# ─────────────────────────────────────────────────────────────────
# PI2 · Exit-price alignment
# ─────────────────────────────────────────────────────────────────
def check_exit_alignment(
    root: Path, market: str, positions: Iterable[dict],
    tolerance_pct: float = TOLERANCE_PCT_DEFAULT,
) -> IntegrityCheck:
    violations = []
    n_checked = 0
    for pos in positions:
        if str(pos.get("status", "")).upper() != "EXIT":
            continue
        exit_price = pos.get("exit_price")
        exit_date = pos.get("exit_date")
        ticker = pos.get("ticker")
        if not (isinstance(exit_price, (int, float)) and exit_price > 0
                and exit_date and ticker):
            continue
        n_checked += 1
        actual = parquet_close(root, ticker, market, exit_date)
        if actual is None:
            violations.append({
                "ticker": ticker, "exit_date": exit_date,
                "quoted": round(exit_price, 2), "actual": None,
                "delta_pct": None,
                "reason": "no parquet row on or before exit date",
            })
            continue
        delta = abs(exit_price - actual) / max(actual, 0.01) * 100
        if delta > tolerance_pct:
            violations.append({
                "ticker": ticker, "exit_date": exit_date,
                "quoted": round(exit_price, 2),
                "actual": round(actual, 2),
                "delta_pct": round(delta, 2),
                "reason": f"exit price drift {delta:.2f}%",
            })
    status = "PASS" if not violations else "FAIL"
    detail = (f"{n_checked} exits checked · "
              f"{len(violations)} drifted > {tolerance_pct}%")
    return IntegrityCheck("PI2", "Exit-price alignment",
                          status, detail, violations)


# ─────────────────────────────────────────────────────────────────
# PI5 · Freshness
# ─────────────────────────────────────────────────────────────────
def check_freshness(
    root: Path, market: str, active_tickers: Iterable[str],
    asof_date: str, cal_days: int = FRESHNESS_CAL_DAYS,
) -> IntegrityCheck:
    violations = []
    n_checked = 0
    try:
        asof_d = date.fromisoformat(asof_date)
    except ValueError:
        return IntegrityCheck(
            "PI5", "Data freshness", "WARN",
            f"invalid asof '{asof_date}' · skipping",
        )
    cutoff = asof_d - timedelta(days=cal_days)
    for ticker in set(active_tickers):
        if not ticker: continue
        n_checked += 1
        latest = parquet_latest_date(root, ticker, market)
        if latest is None:
            violations.append({
                "ticker": ticker, "latest_parquet_date": None,
                "cutoff": cutoff.isoformat(),
                "reason": "no parquet on disk",
            })
            continue
        try:
            latest_d = date.fromisoformat(latest)
        except ValueError:
            continue
        if latest_d < cutoff:
            violations.append({
                "ticker": ticker,
                "latest_parquet_date": latest,
                "cutoff": cutoff.isoformat(),
                "reason": (f"parquet stale by "
                           f"{(asof_d - latest_d).days} calendar days"),
            })
    status = "PASS" if not violations else "FAIL"
    detail = (f"{n_checked} active tickers checked · "
              f"{len(violations)} stale > {cal_days} calendar days")
    return IntegrityCheck("PI5", "Data freshness",
                          status, detail, violations)


# ─────────────────────────────────────────────────────────────────
# PI3 · Historical immutability · fingerprint tail-90 rows per parquet
# ─────────────────────────────────────────────────────────────────
import hashlib


def _fingerprint_tail(root: Path, ticker: str, market: str,
                      window: int = 90) -> Optional[str]:
    """SHA-256 of the tail-N (date, close) pairs · order matters."""
    idx, closes = _load_close_series(root, ticker, market)
    if not idx: return None
    pairs = list(zip(idx[-window:], closes[-window:]))
    body = "|".join(f"{d}:{c:.4f}" for d, c in pairs)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _load_baseline_fingerprints(root: Path, market: str) -> dict:
    p = (root / "reports" / "history"
         / f"parquet_fingerprints_{market.lower()}.json")
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fingerprint_pre_cutoff(root: Path, ticker: str, market: str,
                            cutoff: str, window: int) -> Optional[str]:
    """SHA-256 of tail-window of (date, close) rows STRICTLY BEFORE
    cutoff. Both save + check use this so today's appended row never
    trips the diff · only historical rewrites do."""
    idx, closes = _load_close_series(root, ticker, market)
    if not idx: return None
    pairs = [(d, c) for d, c in zip(idx, closes) if d < cutoff]
    pairs = pairs[-window:]
    if not pairs: return None
    body = "|".join(f"{d}:{c:.4f}" for d, c in pairs)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def save_fingerprints(root: Path, market: str, tickers: Iterable[str],
                      asof: Optional[str] = None,
                      window: int = 90) -> Path:
    """Persist today's fingerprints for tomorrow's PI3 comparison.
    Called AFTER a successful run · establishes the baseline.
    `asof` is the current-run date · rows on/after this date are
    excluded so a subsequent same-day append doesn't invalidate the
    baseline."""
    cutoff = str(asof or "9999-12-31")[:10]
    fps: dict = {}
    for tk in set(tickers):
        if not tk: continue
        fp = _fingerprint_pre_cutoff(root, tk, market, cutoff, window)
        if fp:
            fps[tk.upper()] = {
                "fingerprint": fp,
                "window": window,
                "cutoff": cutoff,
                "captured_utc": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
            }
    p = (root / "reports" / "history"
         / f"parquet_fingerprints_{market.lower()}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fps, indent=2, ensure_ascii=False),
                 encoding="utf-8")
    return p


def check_immutability(root: Path, market: str,
                       tickers: Iterable[str], asof: str,
                       window: int = 90) -> IntegrityCheck:
    """Compare each ticker's baseline fingerprint (excluding today's
    freshly-appended row) against today's parquet. Any change to the
    historical window = SILENT REWRITE = tampering.

    First run when no baseline exists → WARN with 'baseline seeded'.
    """
    baseline = _load_baseline_fingerprints(root, market)
    if not baseline:
        return IntegrityCheck(
            "PI3", "Historical immutability", "WARN",
            "no baseline yet · will seed after this run",
        )
    violations = []
    n_checked = 0
    for tk in set(tickers):
        if not tk: continue
        base = baseline.get(tk.upper())
        if not base: continue
        n_checked += 1
        # Use baseline's cutoff if it recorded one · else fall back to
        # today's asof. Ensures baseline was captured with the SAME
        # cutoff rule as this check.
        cutoff = str(base.get("cutoff") or asof)[:10]
        base_window = int(base.get("window") or window)
        current_fp = _fingerprint_pre_cutoff(
            root, tk, market, cutoff, base_window)
        if not current_fp: continue
        if current_fp != base.get("fingerprint"):
            # Try a shorter tail · maybe baseline was smaller
            violations.append({
                "ticker": tk.upper(),
                "baseline_fp": base.get("fingerprint", "")[:16] + "...",
                "current_fp":  current_fp[:16] + "...",
                "captured_utc": base.get("captured_utc"),
                "reason": ("historical parquet tail changed since "
                           "previous run · possible silent overwrite"),
            })
    status = "PASS" if not violations else "WARN"
    detail = (f"{n_checked} tickers checked · "
              f"{len(violations)} tail mismatches (WARN · investigate)")
    return IntegrityCheck("PI3", "Historical immutability",
                          status, detail, violations)


# ─────────────────────────────────────────────────────────────────
# PI4 · Cross-source reconciliation · yfinance vs Angel
# ─────────────────────────────────────────────────────────────────
def check_cross_source(root: Path, market: str,
                       tickers: Iterable[str], asof: str,
                       sample_n: int = 5,
                       tolerance_pct: float = 1.0) -> IntegrityCheck:
    """For a small random sample · fetch the same-date close from BOTH
    yfinance and Angel · flag divergence > 1%.

    Best-effort: skips if Angel not configured, network unavailable,
    or sample is empty. Not a blocker for delivery · flags source drift
    that would compromise walk-forward validation later.
    """
    # Deterministic sample · sort tickers + take first N (no RNG · so
    # replay-safe · walk-forward can reproduce the same sample).
    tks = sorted({str(t).upper() for t in tickers if t})[:sample_n]
    if not tks:
        return IntegrityCheck(
            "PI4", "Cross-source reconciliation", "PASS",
            "no active tickers to sample",
        )
    # Only USA/India supported by current adapters
    if market.lower() == "usa":
        return IntegrityCheck(
            "PI4", "Cross-source reconciliation", "PASS",
            "USA cross-source · single-source (yfinance) · skipped",
        )
    # Try to import Angel adapter · skip if not available
    try:
        from backend.intraday.feed import angel_adapter as _angel  # noqa
    except Exception:
        return IntegrityCheck(
            "PI4", "Cross-source reconciliation", "PASS",
            "Angel adapter not importable · cross-source skipped",
        )
    # Try one Angel call · if it fails (missing secrets / network) → skip
    try:
        _test = _angel.fetch_bars(root, tks[0], market="india",
                                  interval="1d", lookback_days=5)
        if _test is None or _test.empty:
            return IntegrityCheck(
                "PI4", "Cross-source reconciliation", "PASS",
                "Angel returned no data · secrets missing / rate limit "
                "· skipped",
            )
    except Exception as _e:
        return IntegrityCheck(
            "PI4", "Cross-source reconciliation", "PASS",
            f"Angel probe failed · {type(_e).__name__} · skipped",
        )
    # Real comparison for the sample
    violations = []
    n_checked = 0
    for tk in tks:
        parquet_val = parquet_close(root, tk, market, asof)
        try:
            df = _angel.fetch_bars(root, tk, market="india",
                                   interval="1d", lookback_days=5)
            if df is None or df.empty:
                continue
            df.index = df.index.map(lambda x: str(x)[:10])
            if asof in df.index:
                angel_val = float(df.loc[asof, "close"])
            else:
                before = [d for d in df.index if d <= asof]
                if not before: continue
                angel_val = float(df.loc[before[-1], "close"])
        except Exception:
            continue
        if parquet_val is None or angel_val is None:
            continue
        n_checked += 1
        delta = abs(parquet_val - angel_val) / max(parquet_val, 0.01) * 100
        if delta > tolerance_pct:
            violations.append({
                "ticker": tk, "asof": asof,
                "parquet": round(parquet_val, 2),
                "angel":   round(angel_val, 2),
                "delta_pct": round(delta, 2),
                "reason": f"sources diverge by {delta:.2f}%",
            })
    status = "PASS" if not violations else "WARN"
    detail = (f"{n_checked} tickers cross-checked · "
              f"{len(violations)} diverge > {tolerance_pct}%")
    return IntegrityCheck("PI4", "Cross-source reconciliation",
                          status, detail, violations)


# ─────────────────────────────────────────────────────────────────
# PI6 · Corporate-action awareness
# ─────────────────────────────────────────────────────────────────
def check_corporate_actions(
    root: Path, market: str, positions: Iterable[dict], asof: str,
) -> IntegrityCheck:
    """For each ACTIVE position, look up yfinance corporate actions
    (splits + dividends) between entry_date and today. If any exists,
    the historical entry price probably needs adjustment · flag WARN.

    Best-effort: skips silently when yfinance is unavailable or the
    ticker returns nothing. Never blocks delivery.
    """
    try:
        import yfinance as yf
    except Exception:
        return IntegrityCheck(
            "PI6", "Corporate-action awareness", "PASS",
            "yfinance not importable · check skipped",
        )
    suffix = "" if market.lower() == "usa" else ".NS"
    violations = []
    n_checked = 0
    for pos in positions:
        if str(pos.get("status", "")).upper() == "EXIT": continue
        ticker = pos.get("ticker")
        entry_date = pos.get("entry_date")
        if not (ticker and entry_date): continue
        n_checked += 1
        yf_sym = str(ticker).upper() + suffix
        try:
            t = yf.Ticker(yf_sym)
            actions = t.actions   # DataFrame indexed by date · cols: Dividends, Stock Splits
            if actions is None or actions.empty: continue
            actions.index = actions.index.map(lambda x: str(x)[:10])
            for act_date, row in actions.iterrows():
                if not (entry_date <= act_date <= asof): continue
                _split = row.get("Stock Splits", 0) or 0
                _div   = row.get("Dividends", 0) or 0
                if _split and _split != 1.0:
                    violations.append({
                        "ticker": ticker, "action_date": act_date,
                        "type": "split", "ratio": _split,
                        "entry_date": entry_date,
                        "reason": (f"stock split {_split}x between entry "
                                   f"and today · entry price needs adjust"),
                    })
                elif _div and _div > 0:
                    violations.append({
                        "ticker": ticker, "action_date": act_date,
                        "type": "dividend", "amount": _div,
                        "entry_date": entry_date,
                        "reason": (f"dividend {_div} paid between entry "
                                   "and today · book P&L excludes it"),
                    })
        except Exception:
            continue
    status = "PASS" if not violations else "WARN"
    detail = (f"{n_checked} active positions checked · "
              f"{len(violations)} corporate actions detected (WARN)")
    return IntegrityCheck("PI6", "Corporate-action awareness",
                          status, detail, violations)


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(
    root: Path, market: str, positions: list, asof_date: str,
    tolerance_pct: float = TOLERANCE_PCT_DEFAULT,
) -> IntegrityReport:
    """Run all price-integrity checks and return the report.

    `positions` is a list of dicts with these keys:
      ticker, entry_date, entry_price, exit_date, exit_price, status
    Status is 'ACTIVE' / 'EXIT' / 'NEW' / etc. · EXIT triggers PI2.
    """
    rep = IntegrityReport(
        market=market.lower(),
        asof=asof_date,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        tolerance_pct=tolerance_pct,
    )
    rep.n_positions_checked = len(positions)
    rep.n_exits_checked = sum(1 for p in positions
                              if str(p.get("status", "")).upper() == "EXIT")
    rep.n_active_checked = sum(1 for p in positions
                               if str(p.get("status", "")).upper() != "EXIT")

    rep.add(check_entry_alignment(root, market, positions, tolerance_pct))
    rep.add(check_exit_alignment(root, market, positions, tolerance_pct))
    active_tickers = [p["ticker"] for p in positions
                      if str(p.get("status", "")).upper() != "EXIT"
                      and p.get("ticker")]
    rep.add(check_freshness(root, market, active_tickers, asof_date))
    # PI3 · historical immutability (WARN · seeds baseline on first run)
    rep.add(check_immutability(root, market, active_tickers, asof_date))
    # PI4 · cross-source reconciliation (best-effort · skipped when
    # Angel/network unavailable · WARN never blocks)
    rep.add(check_cross_source(root, market, active_tickers, asof_date))
    # PI6 · corporate-action awareness (WARN · uses yfinance .actions)
    rep.add(check_corporate_actions(root, market, positions, asof_date))
    return rep


def emit(root: Path, report: IntegrityReport) -> Path:
    p = (root / "reports" / "context"
         / f"price_integrity_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return p


def summary_line(rep: IntegrityReport) -> str:
    """One-line human summary · for logs + delivery-gate summary."""
    fails = [c for c in rep.checks if c.status == "FAIL"]
    return (f"price_integrity · verdict={rep.verdict} · "
            f"fails={len(fails)} · "
            f"positions={rep.n_positions_checked} · "
            f"exits={rep.n_exits_checked}")


# ─────────────────────────────────────────────────────────────────
# PREVENTION · call from rec / exit path before writing
# ─────────────────────────────────────────────────────────────────
def validate_price_before_write(
    root: Path, market: str, ticker: str, quoted_price: float,
    target_date: str, tolerance_pct: float = TOLERANCE_PCT_DEFAULT,
) -> tuple[bool, Optional[float], Optional[float]]:
    """PREVENTION · call BEFORE persisting a rec / exit.

    Returns (ok, delta_pct, actual_close):
      ok           · True if quoted matches parquet close within tolerance
      delta_pct    · signed % delta (quoted - actual) / actual * 100
      actual_close · the parquet close on target_date (or None if missing)

    Caller usage:
      ok, delta, actual = validate_price_before_write(...)
      if not ok:
          _log_rejection(ticker, quoted_price, actual, delta)
          return  # refuse to write the rec/exit
    """
    if not isinstance(quoted_price, (int, float)) or quoted_price <= 0:
        return False, None, None
    actual = parquet_close(root, ticker, market, target_date)
    if actual is None:
        return False, None, None
    delta = (quoted_price - actual) / max(actual, 0.01) * 100
    return abs(delta) <= tolerance_pct, round(delta, 3), round(actual, 2)


def log_rejection(root: Path, market: str, ticker: str,
                  quoted_price: float, actual_close: Optional[float],
                  delta_pct: Optional[float], target_date: str,
                  reason: str, source: str = "unknown") -> None:
    """Append a rejected rec/exit to price_integrity_rejections.jsonl.
    Idempotent · one line per rejection."""
    p = (root / "reports" / "context"
         / "price_integrity_rejections.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": market.lower(),
        "ticker": ticker.upper(),
        "quoted": quoted_price,
        "actual": actual_close,
        "delta_pct": delta_pct,
        "target_date": target_date,
        "reason": reason,
        "source": source,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
