"""AEGIS Intraday Hourly · standalone parallel job.

Runs SEPARATE from the main advisory pipeline (backend/recommendation/ssot/run.py)
so its external-fetch cost (yfinance ~10s per ticker · rate-limit risk) never
blocks daily advisory delivery.

What it does:
  1. Reads today's Runner 1 picks (data/aegis_today.csv) + Runner 2 picks
     (reports/recommendations.json)
  2. Fetches real hourly bars from yfinance for the picks' tickers
     (cached at data/raw/india_hourly/{TICKER}_H1.parquet)
  3. Builds hourly-intraday paper portfolios:
        reports/research/runner1_intraday_h1/positions.json + history.jsonl
        reports/research/runner2_intraday_h1/positions.json + history.jsonl
  4. Rebuilds reports/research/research_platform.json (SSoT) so Telegram
     and dashboards immediately reflect the fresh hourly numbers

Usage:
    python scripts/intraday_hourly_run.py                     # today · both runners
    python scripts/intraday_hourly_run.py --as-of 2026-07-30  # specific date

Idempotent: reruns safely, no duplication, cache used when present.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research.intraday_hourly import ingest_hourly_intraday    # noqa: E402
from backend.research.platform import build_research_platform          # noqa: E402


def _load_runner1_picks(root: Path) -> list[dict]:
    src = root / "data" / "aegis_today.csv"
    picks: list[dict] = []
    if not src.exists():
        return picks
    active = {"STRONG BUY", "BUY", "ACCUMULATE"}
    try:
        with src.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                strength = str(row.get("Strength") or "").strip().upper()
                if strength not in active:
                    continue
                try:
                    score = float(row.get("Score /100") or 0) or None
                except (TypeError, ValueError):
                    score = None
                picks.append({"ticker": row.get("Stock"), "score": score})
    except Exception:
        pass
    return picks


def _load_runner2_picks(root: Path) -> list[dict]:
    src = root / "reports" / "recommendations.json"
    picks: list[dict] = []
    if not src.exists():
        return picks
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        for r in data.get("recommendations") or []:
            inv = (r.get("investor_action") or {}).get("entry")
            pct = r.get("percentile_action")
            if inv == "BUY" or pct in ("STRONG_BUY", "BUY"):
                picks.append({
                    "ticker":  r.get("ticker"),
                    "score":   r.get("composite_decision_score") or r.get("ensemble_score"),
                })
    except Exception:
        pass
    return picks


def _read_experiment_start(root: Path) -> str:
    cfg = root / "configs" / "research_program.json"
    if cfg.exists():
        try:
            return json.loads(cfg.read_text(encoding="utf-8")).get("experiment_start") \
                        or date.today().isoformat()
        except Exception:
            pass
    return date.today().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None,
                       help="Trading date (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                       help="Report picks + skip fetch")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    asof = args.as_of or date.today().isoformat()
    print(f"[intraday_hourly] as_of={asof}")

    r1 = _load_runner1_picks(_ROOT)
    r2 = _load_runner2_picks(_ROOT)
    print(f"[intraday_hourly] runner1 picks: {len(r1)} · runner2 picks: {len(r2)}")

    if args.dry_run:
        print(f"  R1: {[p['ticker'] for p in r1]}")
        print(f"  R2: {[p['ticker'] for p in r2]}")
        return 0

    if not r1 and not r2:
        print("[intraday_hourly] no picks to process · skipping")
        return 0

    result = ingest_hourly_intraday(_ROOT, r1, r2, as_of=asof, refresh_cache=True)
    fs = result.get("fetch_summary") or {}
    print(f"[intraday_hourly] fetched={fs.get('fetched', 0)}  "
              f"cached_hits={fs.get('cached_hits', 0)}  "
              f"rows_written={fs.get('rows_written', 0)}  "
              f"errors={len(fs.get('errors', []))}")
    print(f"[intraday_hourly] R1 hourly positions: "
              f"{result['runner1_intraday_h1']['n_positions']}")
    print(f"[intraday_hourly] R2 hourly positions: "
              f"{result['runner2_intraday_h1']['n_positions']}")

    # Refresh the unified Research Platform SSoT so Telegram / dashboards
    # immediately pick up the fresh hourly numbers.
    exp_start = _read_experiment_start(_ROOT)
    rp = build_research_platform(_ROOT, experiment_start=exp_start)
    intra = ((rp.get("layers") or {}).get("live_evaluation") or {}) \
                .get("india_intraday") or {}
    hourly = intra.get("hourly") or {}
    r1h = hourly.get("runner1") or {}
    r2h = hourly.get("runner2") or {}
    print(f"[intraday_hourly] SSoT hourly · R1 ret {r1h.get('total_return_pct', 0):+.2f}% "
              f"win {(r1h.get('win_rate') or 0)*100:.0f}% N={r1h.get('n_positions', 0)}")
    print(f"[intraday_hourly] SSoT hourly · R2 ret {r2h.get('total_return_pct', 0):+.2f}% "
              f"win {(r2h.get('win_rate') or 0)*100:.0f}% N={r2h.get('n_positions', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
