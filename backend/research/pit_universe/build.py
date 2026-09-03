"""AEGIS Point-in-Time Universe Audit · P5.4 deliverable

Reconstructs (market, date, ticker) membership from the best available
sources · in priority order:

  1. Snapshotted universe files (usa/reports/universe_YYYY-MM-DD.json)
  2. Historical constituent changes list (configs/universe_change_events.yaml)
  3. Fallback · current universe (flagged as UNKNOWN membership pre-inception)

The output is a parquet indexed by (market, date, ticker) with columns:
  - was_member: bool
  - source: str (snapshot | change_events | current_fallback)
  - confidence: str (HIGH | MEDIUM | LOW)

Consumers (backend/research/walkforward/*, P5 audit report) call
was_in_universe(market, date, ticker) which returns bool + source.
This is the ONLY way any backtest may filter its ticker set.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]


def _yaml_load(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _extract_ticker(x) -> str:
    """Normalize a universe entry to bare ticker · handles str, dict-with-SYMBOL,
    dict-with-symbol, dict-with-ticker."""
    if isinstance(x, str):
        return x.strip().upper()
    if isinstance(x, dict):
        for k in ("SYMBOL", "symbol", "TICKER", "ticker", "code"):
            v = x.get(k)
            if v: return str(v).strip().upper()
    return str(x).strip().upper()


def _current_universe(root: Path, market: str) -> list[str]:
    """Load today's declared universe as a fallback baseline."""
    cfg = _yaml_load(root / "configs" / "aegis_universes.yaml")
    src = cfg.get("markets", {}).get(market, {}).get("source_file")
    if not src: return []
    p = root / src
    if not p.exists(): return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return [_extract_ticker(x) for x in d if x]
        if isinstance(d, dict):
            for key in ("tickers", "constituents", "members"):
                if key in d and isinstance(d[key], list):
                    return [_extract_ticker(x) for x in d[key] if x]
    except (ValueError, OSError):
        pass
    return []


def _snapshotted_universe(root: Path, market: str, dt: date) -> Optional[list[str]]:
    """Return snapshotted universe if we have one for this exact date."""
    if market == "usa":
        base = root / "usa" / "reports"
    else:
        base = root / "reports"
    # Common pattern: universe_YYYY-MM-DD.json
    p = base / f"universe_{dt.isoformat()}.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, list):
                return [str(x).upper() for x in d]
            if isinstance(d, dict):
                for key in ("tickers", "constituents", "members"):
                    if key in d and isinstance(d[key], list):
                        return [str(x).upper() for x in d[key]]
        except (ValueError, OSError):
            pass
    return None


def _load_change_events(root: Path, market: str) -> list[dict]:
    """Load configs/universe_change_events.yaml if present.

    Schema:
      market: usa
      changes:
        - date: 2026-08-14
          added: [FOO, BAR]
          removed: [BAZ]
    """
    p = root / "configs" / "universe_change_events.yaml"
    if not p.exists(): return []
    try:
        cfg = _yaml_load(p) or {}
    except Exception:
        return []
    changes = []
    for mcfg in cfg.get("markets", []) or []:
        if str(mcfg.get("market", "")).lower() == market:
            for ev in mcfg.get("changes", []) or []:
                changes.append(ev)
    return sorted(changes, key=lambda e: str(e.get("date", "")))


def _apply_changes_backward(current: set[str], changes: list[dict],
                            target_date: str) -> set[str]:
    """Walk changes backward from today to target_date.
    For each change that occurred AFTER target_date, invert it."""
    membership = set(current)
    for ev in reversed(changes):
        ev_date = str(ev.get("date", ""))
        if not ev_date or ev_date <= target_date:
            break
        for t in (ev.get("added") or []):
            membership.discard(str(t).upper())
        for t in (ev.get("removed") or []):
            membership.add(str(t).upper())
    return membership


def build_pit_universe(root: Path, market: str,
                       start_date: str, end_date: str) -> dict:
    """Emit reports/research/pit_universe/{market}.parquet for [start, end].

    Row per (market, date, ticker) with was_member + source + confidence.
    Uses TRADING dates only (walks by 1 day but reader can filter to
    market open days). Small ranges recommended (< 3 years)."""
    import pandas as pd

    d0 = datetime.fromisoformat(start_date).date()
    d1 = datetime.fromisoformat(end_date).date()
    if d1 < d0: d0, d1 = d1, d0

    current = _current_universe(root, market)
    changes = _load_change_events(root, market)
    curr_set = set(current)

    rows: list[dict] = []
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    d = d0
    while d <= d1:
        iso = d.isoformat()
        snap = _snapshotted_universe(root, market, d)
        if snap is not None:
            members = set(snap); src = "snapshot"; conf = "HIGH"
        elif changes:
            members = _apply_changes_backward(curr_set, changes, iso)
            src = "change_events"; conf = "MEDIUM"
        else:
            members = curr_set; src = "current_fallback"; conf = "LOW"
        for t in members:
            rows.append({
                "market": market, "date": iso, "ticker": t,
                "was_member": True, "source": src, "confidence": conf,
                "built_utc": now,
            })
        d = d + timedelta(days=1)

    if not rows:
        return {"market": market, "n_rows": 0}

    df = pd.DataFrame(rows)
    out_dir = root / "reports" / "research" / "pit_universe"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{market}.parquet"
    df.to_parquet(p, index=False)

    summary = {
        "market": market,
        "date_range": [start_date, end_date],
        "n_rows": int(len(df)),
        "n_dates": int(df["date"].nunique()),
        "n_unique_tickers": int(df["ticker"].nunique()),
        "sources": df["source"].value_counts().to_dict(),
        "confidence": df["confidence"].value_counts().to_dict(),
        "parquet_path": str(p.relative_to(root)),
        "built_utc": now,
        "n_change_events_loaded": len(changes),
        "current_universe_size": len(current),
    }
    (out_dir / f"{market}.summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def load_pit_universe(root: Path, market: str):
    import pandas as pd
    p = root / "reports" / "research" / "pit_universe" / f"{market}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


_CACHE: dict = {}


def was_in_universe(root: Path, market: str, date_str: str, ticker: str) -> dict:
    """PIT membership check · returns {was_member, source, confidence}."""
    key = f"pit:{market}"
    if key not in _CACHE:
        _CACHE[key] = load_pit_universe(root, market)
    df = _CACHE[key]
    if df is None or df.empty:
        return {"was_member": False, "source": "no_pit_data", "confidence": "NONE"}
    q = df[(df["date"] == date_str) & (df["ticker"] == ticker.upper())]
    if q.empty:
        return {"was_member": False, "source": "not_in_pit", "confidence": "HIGH"}
    r = q.iloc[0]
    return {"was_member": bool(r["was_member"]),
            "source": str(r["source"]),
            "confidence": str(r["confidence"])}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    s = build_pit_universe(Path(args.root), args.market, args.start, args.end)
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
