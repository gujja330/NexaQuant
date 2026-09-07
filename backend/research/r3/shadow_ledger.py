"""R3 · Shadow Ledger · append-only jsonl of paper picks
CEO 2026-09-03

Every daily R3 run appends its picks + calibrated probability to
`reports/research/r3/shadow_ledger.jsonl`. Never touches Registry,
Portfolio, Exit History, or Telegram.

Schema per line:
  { runner, opportunity_id, shadow_only,
    asof, market, ticker, r3_score, r3_calibrated_p, action, model_id,
    features_hash, ts_utc }

CEO 2026-09-07 · R3-0 · `runner` and `opportunity_id` are MANDATORY.
The R3-1 audit found records carried neither, so an R3 row was
indistinguishable from an R2 row by schema alone and could not be
rejected on identity by a production consumer. See
docs/AEGIS/R3_BASELINE_READINESS.md (blocker B9).

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
                       model_id: str = "aegis.r3.gbm_tier1.v1",
                       *,
                       r3_raw_p=None, rank=None,
                       model_version="NOT_AVAILABLE_AT_ASOF",
                       feature_version="NOT_AVAILABLE_AT_ASOF",
                       calibrator_version="NOT_AVAILABLE_AT_ASOF",
                       entry_price=None, stop_price=None, target_price=None,
                       horizon_days=None, size_pct_simulated=None,
                       top_features=None, regime=None,
                       comparator=None) -> dict:
    """Append one pick to the shadow ledger · idempotent per (asof,ticker).

    CEO 2026-09-07 · R3 Sprint 1 · the record is now the CANONICAL
    five-block schema (identity · signal · risk · outcome · comparator ·
    attribution). The outcome block is written PENDING at T0 and filled
    forward by `backend.research.r3.outcomes`, never at write time.
    """
    from backend.research.r3.identity import stamp_identity
    from backend.research.r3.ledger_schema import build_record

    row = build_record(
        market=market, ticker=ticker, asof=asof,
        r3_score=r3_score, r3_raw_p=r3_raw_p,
        r3_calibrated_p=r3_calibrated_p, rank=rank, action=action,
        model_id=model_id, model_version=model_version,
        feature_version=feature_version,
        calibrator_version=calibrator_version, features=features,
        entry_price=entry_price, stop_price=stop_price,
        target_price=target_price, horizon_days=horizon_days,
        size_pct_simulated=size_pct_simulated,
        top_features=top_features, regime=regime, comparator=comparator,
    )
    # R3-0 identity · runner=R3 + canonical shadow Position ID.
    stamp_identity(row, market, ticker, asof)
    p = _ledger_path(root)
    # IDEMPOTENCE (B11) · the docstring promised "idempotent per
    # (asof,ticker,model)" but nothing enforced it · a re-run appended the
    # whole day again, silently inflating the position count the Day-30
    # gate measures. The R3 Position ID is deterministic per
    # (market, ticker, asof), so it is the natural dedupe key.
    if row["opportunity_id"] in _seen_ids(root):
        return row
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    _seen_ids(root).add(row["opportunity_id"])
    return row


# Per-path cache so a daily batch does not re-read the ledger per row.
_SEEN_CACHE: dict = {}


def _seen_ids(root: Path) -> set:
    p = _ledger_path(root)
    key = str(p)
    if key not in _SEEN_CACHE:
        ids = set()
        if p.exists():
            for line in p.read_text(encoding="utf-8",
                                     errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    ids.add(json.loads(line).get("opportunity_id"))
                except ValueError:
                    continue
        _SEEN_CACHE[key] = ids
    return _SEEN_CACHE[key]


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
