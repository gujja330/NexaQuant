"""Ticker Health Tracker · flags dead / renamed / stale symbols.

Operator 2026-08-24: showed a fundamentals ingest log with 4 permanent
404s (TATAMOTORS.NS · MM.NS · LTIM.NS · PEL.NS) and asked "how do u
handle such errors". Answer: they were logged but not tracked. Fix:

  1. Every ingest module logs successes + failures per ticker to a
     shared JSONL sidecar via record().
  2. compute_report() walks the sidecar, aggregates last N days per
     ticker, classifies:
        HEALTHY   · succeeded in ≥ 80% of recent attempts
        STALE     · fewer attempts than expected (data provider slow)
        DEGRADED  · 20-80% success rate · watch
        DEAD      · < 20% success in ≥ 5 recent attempts · rename/delist
  3. Report surfaces in daily_ops_diagnostic warnings + emits
     reports/context/ticker_health_{market}.json.
  4. Config alias map handles known renames (TATAMOTORS → new symbol).

Auto-removal from universe is NOT done here · operator reviews the
report first, then can add to universe blocklist or alias map.
"""
from __future__ import annotations

import json
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, date, timedelta
from pathlib import Path


def _health_path(root: Path, market: str) -> Path:
    return root / "reports" / "context" / f"ticker_health_{market.lower()}.jsonl"


def record(root: Path, market: str, ticker: str, source: str,
                 ok: bool, error: str = "") -> None:
    """Append one health event. Called from within any ingest per-ticker loop.
    Failure to write is silently ignored (never breaks the ingest)."""
    try:
        p = _health_path(root, market)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "asof":    date.today().isoformat(),
            "market":  market.lower(),
            "ticker":  str(ticker).upper().replace(".NS","").replace(".BO",""),
            "source":  source,
            "ok":      bool(ok),
            "error":   str(error or "")[:200],
        }
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


@dataclass
class TickerHealthRow:
    ticker:         str = ""
    n_attempts:     int = 0
    n_success:      int = 0
    n_failure:      int = 0
    success_rate:   float = 0.0
    last_success:   str = ""
    last_failure:   str = ""
    latest_error:   str = ""
    verdict:        str = "HEALTHY"   # HEALTHY | STALE | DEGRADED | DEAD


@dataclass
class TickerHealthReport:
    engine:         str = "aegis.ticker_health.v1"
    generated_utc:  str = ""
    market:         str = ""
    asof:           str = ""
    lookback_days:  int = 7
    n_tickers:      int = 0
    n_healthy:      int = 0
    n_stale:        int = 0
    n_degraded:     int = 0
    n_dead:         int = 0
    dead_tickers:   list = field(default_factory=list)
    degraded_tickers: list = field(default_factory=list)


def compute_report(root: Path, market: str, asof: str,
                              lookback_days: int = 7) -> TickerHealthReport:
    """Aggregate the last N days of health events per ticker."""
    market = market.lower(); asof = asof[:10]
    rep = TickerHealthReport(
        market=market, asof=asof, lookback_days=lookback_days,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    p = _health_path(root, market)
    if not p.exists(): return rep
    try:
        cutoff = (date.fromisoformat(asof) - timedelta(days=lookback_days)).isoformat()
    except Exception:
        cutoff = "0000"
    by_ticker: dict = defaultdict(list)
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        if str(d.get("asof", ""))[:10] < cutoff: continue
        by_ticker[d.get("ticker", "?")].append(d)

    for tk, events in by_ticker.items():
        n = len(events)
        n_ok = sum(1 for e in events if e.get("ok"))
        n_fail = n - n_ok
        rate = round(n_ok / max(1, n), 3)
        last_ok = max((e["asof"] for e in events if e.get("ok")), default="")
        last_fail = max((e["asof"] for e in events if not e.get("ok")), default="")
        latest_err = ""
        for e in sorted(events, key=lambda e: e.get("ts_utc", ""), reverse=True):
            if not e.get("ok") and e.get("error"):
                latest_err = e["error"]; break
        if n < 3:
            verdict = "STALE"
        elif rate < 0.20 and n_fail >= 5:
            verdict = "DEAD"
        elif rate < 0.80:
            verdict = "DEGRADED"
        else:
            verdict = "HEALTHY"
        row = TickerHealthRow(
            ticker=tk, n_attempts=n, n_success=n_ok, n_failure=n_fail,
            success_rate=rate, last_success=last_ok, last_failure=last_fail,
            latest_error=latest_err, verdict=verdict,
        )
        rep.n_tickers += 1
        if verdict == "HEALTHY":  rep.n_healthy += 1
        elif verdict == "STALE":   rep.n_stale += 1
        elif verdict == "DEGRADED":
            rep.n_degraded += 1
            rep.degraded_tickers.append(asdict(row))
        elif verdict == "DEAD":
            rep.n_dead += 1
            rep.dead_tickers.append(asdict(row))
    return rep


def emit(root: Path, rep: TickerHealthReport) -> Path:
    p = (root / "reports" / "context"
             / f"ticker_health_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(rep: TickerHealthReport) -> str:
    if rep.n_dead > 0:
        return (f"⚠️ {rep.n_dead} DEAD tickers · {rep.n_degraded} degraded · "
                    f"first dead: {', '.join(t['ticker'] for t in rep.dead_tickers[:3])}")
    if rep.n_degraded > 0:
        return f"⚠️ {rep.n_degraded} tickers degraded · monitor for auto-flag"
    return f"✅ {rep.n_healthy}/{rep.n_tickers} tickers healthy"


# ─────────────────────────────────────────────────────────────
# Known-alias map · maintained in configs/ticker_aliases.yaml
# Ingest modules can consult resolve_alias(ticker, market) to
# swap in the current live symbol before calling yfinance.
# ─────────────────────────────────────────────────────────────

def _load_aliases(root: Path, market: str) -> dict:
    p = root / "configs" / "ticker_aliases.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return (cfg.get(market.lower(), {}) or {})
    except Exception:
        return {}


def resolve_alias(root: Path, market: str, ticker: str) -> str:
    """Return the current live symbol for a legacy/renamed ticker.
    Passes through unchanged if no alias registered."""
    bare = str(ticker).upper().replace(".NS","").replace(".BO","")
    aliases = _load_aliases(root, market)
    return aliases.get(bare, ticker)
