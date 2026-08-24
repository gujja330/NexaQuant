"""AEGIS NEW Opportunity Diagnostic · § 2 / § 3 / § 31 of 2026-08-21 directive.

Operator's persistent complaint: "new stocks is not flowing day by day".
This module answers the question the daily portfolio silently ducks:

    "If NEW = zero (or ~one) today, WHY? What did the pipeline evaluate,
    and where did the funnel narrow?"

Consumed by:
  - scripts/telegram_command_center_send.py (visibility panel row)
  - reports/context/new_opportunity_diagnostic.json (audit artifact)

No R1/R2 engine changes · no new agents · pure reporting layer over the
data the pipeline already produced. Sits alongside the Opportunity
Registry as the "why zero NEW today" tool.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

from backend.research import opportunity_registry as oreg


SCHEMA_FINGERPRINT = "aegis.new_opportunity_diagnostic.v1.20260821"


@dataclass
class NewOpportunityDiagnostic:
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    asof:               str = ""
    market:             str = ""
    run_utc:            str = ""
    # Funnel from universe → NEW
    n_universe:         int = 0
    n_recs_today:       int = 0
    n_active_held:      int = 0
    n_recs_already_held: int = 0     # recs that overlap with holdings
    n_cooling_blocked:  int = 0
    n_new_today:        int = 0
    # Per-runner NEW counts
    n_new_r1:           int = 0
    n_new_r2:           int = 0
    # Top NEW candidates (up to 5) with reasoning
    top_new:            list = field(default_factory=list)
    # Reasons if n_new_today is 0 or below quota
    zero_reason:        str = ""
    quota_shortfall:    dict = field(default_factory=dict)


def _load_recs_today(root: Path, market: str) -> list:
    """Load today's recommendations for the given market."""
    if market == "usa":
        p = root / "usa" / "reports" / "recommendations.json"
    else:
        p = root / "reports" / "recommendations.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("recommendations", []) if isinstance(d, dict) else []
    except Exception:
        return []


def _universe_size(root: Path, market: str) -> int:
    """Best-effort universe count · looks at bar directory."""
    d = (root / "usa" / "data" / "raw" / "us" if market == "usa"
             else root / "data" / "raw" / "india")
    if not d.exists():
        return 0
    return sum(1 for _ in d.glob("*_D1.parquet"))


def _count_cooling_blocks_today(root: Path, market: str, asof: str) -> int:
    """Count today's cooling-block events from the sidecar log."""
    p = root / "reports" / "context" / "opportunity_cooling_blocks.jsonl"
    if not p.exists():
        return 0
    n = 0
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if (d.get("asof") == asof[:10]
                and str(d.get("market", "")).lower() == market.lower()):
                n += 1
    except Exception:
        pass
    return n


def compute(root: Path, market: str, asof: str) -> NewOpportunityDiagnostic:
    """Compute the diagnostic for one market on one date."""
    market = market.lower()
    asof = asof[:10]
    diag = NewOpportunityDiagnostic(
        asof=asof, market=market,
        run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    # Universe + recs
    diag.n_universe   = _universe_size(root, market)
    recs              = _load_recs_today(root, market)
    diag.n_recs_today = len(recs)
    # Registry state
    reg = oreg.load_all(root)
    active_by_mkt = {}
    for opps in reg.values():
        for opp in opps:
            if opp.market.lower() != market: continue
            if opp.is_active():
                active_by_mkt.setdefault(opp.ticker.upper(), []).append(opp)
    diag.n_active_held = sum(len(v) for v in active_by_mkt.values())
    diag.n_cooling_blocked = _count_cooling_blocks_today(root, market, asof)

    # Compute NEW pool § 2: recs - held - cooling-blocked - non-actionable
    _held_tks = set(active_by_mkt.keys())
    _recs_by_tk = {}
    for r in recs:
        tk = str(r.get("ticker", "")).upper().replace(".NS","").replace(".BO","")
        _recs_by_tk[tk] = r
    _overlap = _held_tks & set(_recs_by_tk.keys())
    diag.n_recs_already_held = len(_overlap)

    # NEW candidates today = recs whose ticker has NO active opportunity yet
    # AND whose Registry created_date == today (registry seeds only when
    # opportunity is genuinely fresh · post-cooling rules).
    _new_by_runner = {"R1": [], "R2": [], "R3": []}
    for tk, r in _recs_by_tk.items():
        if tk in _held_tks:
            continue     # already held · not NEW
        # Find registry entry created today for this ticker
        for opps in reg.values():
            for opp in opps:
                if (opp.market.lower() == market
                    and opp.ticker.upper() == tk
                    and opp.created_date == asof
                    and opp.is_active()):
                    _r = (opp.runner or "R?").upper().replace("_NEW","")
                    _new_by_runner.setdefault(_r, []).append({
                        "ticker": tk, "runner": _r,
                        "opportunity_id": opp.opportunity_id,
                        "rank": r.get("rank"),
                        "action": r.get("action") or r.get("recommendation"),
                        "score": r.get("composite_decision_score",
                                          r.get("ensemble_score")),
                        "sector": r.get("sector", ""),
                        "why":    r.get("action_reason", "") or r.get("percentile_reason", ""),
                    })
                    break
    diag.n_new_r1 = len(_new_by_runner.get("R1", []))
    diag.n_new_r2 = len(_new_by_runner.get("R2", []))
    diag.n_new_today = diag.n_new_r1 + diag.n_new_r2

    # Top 5 (across runners)
    _all_new = _new_by_runner.get("R1", []) + _new_by_runner.get("R2", [])
    _all_new.sort(key=lambda x: (x.get("rank") or 99))
    diag.top_new = _all_new[:5]

    # Zero-reason narrative (§ 31)
    if diag.n_new_today == 0:
        _parts = []
        _parts.append(f"{diag.n_recs_today} recs evaluated")
        _parts.append(f"{diag.n_active_held} active positions in Registry")
        if diag.n_recs_already_held:
            _parts.append(f"{diag.n_recs_already_held} recs already held (excluded from NEW pool)")
        if diag.n_cooling_blocked:
            _parts.append(f"{diag.n_cooling_blocked} tickers cooling (< 7d since exit)")
        diag.zero_reason = " · ".join(_parts)

    # Quota shortfall
    _quota = {"R1_target": 3, "R2_target": 3,
                  "R1_actual": diag.n_new_r1, "R2_actual": diag.n_new_r2}
    _quota["R1_shortfall"] = max(0, _quota["R1_target"] - _quota["R1_actual"])
    _quota["R2_shortfall"] = max(0, _quota["R2_target"] - _quota["R2_actual"])
    diag.quota_shortfall = _quota

    return diag


def emit(root: Path, diag: NewOpportunityDiagnostic) -> Path:
    """Write the diagnostic JSON · one file per market (overwrites daily)."""
    p = (root / "reports" / "context"
             / f"new_opportunity_diagnostic_{diag.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(diag), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(diag: NewOpportunityDiagnostic) -> str:
    """One-line summary suitable for the sender's KPI banner."""
    if diag.n_new_today == 0:
        return f"NEW = 0 · {diag.zero_reason or 'no candidates cleared gates'}"
    return (f"NEW today · R1={diag.n_new_r1} · R2={diag.n_new_r2} · "
                f"top: {', '.join(c['ticker'] for c in diag.top_new[:3])}")
