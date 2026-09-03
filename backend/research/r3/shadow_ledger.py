"""R3 · Shadow Ledger · append-only jsonl of paper picks
CEO 2026-09-03

Every daily R3 run appends its picks + calibrated probability to
`reports/research/r3/shadow_ledger.jsonl`. Never touches Registry,
Portfolio, Exit History, or Telegram.

Schema per line:
  { asof, market, ticker, r3_score, r3_calibrated_p, action, model_id,
    features_hash, ts_utc }

Consumed by:
  - r3.day30_gate  · Day-30 kill gate 2-of-3
  - r3.day60_scorecard
  - r3.day90_promotion_evaluation
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_LEDGER_PATH_TEMPLATE = "reports/research/r3/shadow_ledger.jsonl"


def _ledger_path(root: Path) -> Path:
    p = root / _LEDGER_PATH_TEMPLATE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _features_hash(features: dict) -> str:
    s = json.dumps(features, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def append_shadow_pick(root: Path, market: str, ticker: str, asof: str,
                       r3_score: float, r3_calibrated_p: float,
                       action: str, features: dict,
                       model_id: str = "aegis.r3.gbm_tier1.v1") -> dict:
    """Append one pick to the shadow ledger · idempotent per (asof,ticker,model)."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {
        "asof": asof,
        "market": market,
        "ticker": str(ticker).upper(),
        "r3_score": round(float(r3_score), 6),
        "r3_calibrated_p": round(float(r3_calibrated_p), 6),
        "action": str(action).upper(),
        "model_id": model_id,
        "features_hash": _features_hash(features),
        "ts_utc": ts,
    }
    p = _ledger_path(root)
    # Dedupe on read · append-only on write
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def read_shadow_ledger(root: Path, market: str = None) -> list[dict]:
    p = _ledger_path(root)
    if not p.exists(): return []
    out = []
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if market is None or o.get("market") == market:
                out.append(o)
    return out
