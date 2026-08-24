"""AEGIS Daily Ops Diagnostic · § 31 of 2026-08-21 directive.

"Add an internal validation report after every run. Check counts of
NEW, existing, exits, skipped, rejected, same-day NEW→EXIT, duplicate
live tickers, duplicate Position IDs, stale prices, missing P&L,
missing previous close, rank changes, rotation suggestions."

Consumes what other engines already emitted today · zero double-work.
Writes reports/context/daily_ops_diagnostic_{market}.json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

from backend.research import opportunity_registry as oreg


SCHEMA_FINGERPRINT = "aegis.daily_ops_diagnostic.v1.20260821"


@dataclass
class DailyOpsDiagnostic:
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    asof:               str = ""
    market:             str = ""
    run_utc:            str = ""
    counts:             dict = field(default_factory=dict)
    warnings:           list = field(default_factory=list)


def _load_json_or(p: Path, default):
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return default


def _jsonl_count(p: Path, filter_fn=None) -> int:
    if not p.exists(): return 0
    n = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        if filter_fn is None or filter_fn(d): n += 1
    return n


def compute(root: Path, market: str, asof: str) -> DailyOpsDiagnostic:
    market = market.lower()
    asof = asof[:10]
    diag = DailyOpsDiagnostic(
        asof=asof, market=market,
        run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    c: dict = diag.counts

    # Consume other engines' outputs
    _nd = _load_json_or(root / "reports" / "context"
                                 / f"new_opportunity_diagnostic_{market}.json", {})
    _rot = _load_json_or(root / "reports" / "context"
                                  / f"rotation_suggestions_{market}.json", {})
    _reg = oreg.load_all(root)

    # From new opportunity diagnostic
    c["universe_scanned"]   = _nd.get("n_universe", 0)
    c["recs_today"]         = _nd.get("n_recs_today", 0)
    c["active_held"]        = _nd.get("n_active_held", 0)
    c["recs_already_held"]  = _nd.get("n_recs_already_held", 0)
    c["cooling_blocked"]    = _nd.get("n_cooling_blocked", 0)
    c["new_today"]          = _nd.get("n_new_today", 0)
    c["new_r1"]             = _nd.get("n_new_r1", 0)
    c["new_r2"]             = _nd.get("n_new_r2", 0)
    c["rotation_suggestions"] = _rot.get("n_suggestions", 0)

    # From registry: closes, rejections, duplicates
    active = 0; closed = 0; rejected = 0
    ids_seen: Counter = Counter()
    tks_active: Counter = Counter()
    for opps in _reg.values():
        for opp in opps:
            if opp.market.lower() != market: continue
            ids_seen[opp.opportunity_id] += 1
            if opp.status == "ACTIVE":
                active += 1; tks_active[opp.ticker.upper()] += 1
            elif opp.status == "CLOSED": closed += 1
            elif opp.status == "REJECTED": rejected += 1
    c["registry_active"]    = active
    c["registry_closed"]    = closed
    c["registry_rejected"]  = rejected
    c["duplicate_position_ids"] = sum(1 for v in ids_seen.values() if v > 1)
    c["duplicate_live_tickers"] = sum(1 for v in tks_active.values() if v > 1)

    # Closes today · rejections today
    c["exits_today"] = sum(1 for opps in _reg.values() for opp in opps
                                   if opp.market.lower() == market
                                   and opp.closed_date == asof
                                   and opp.status == "CLOSED")
    c["rejections_today"] = sum(1 for opps in _reg.values() for opp in opps
                                          if opp.market.lower() == market
                                          and opp.closed_date == asof
                                          and opp.status == "REJECTED")

    # Skip candidates dataset (research-only · never in portfolio)
    _skip = root / "reports" / "research" / f"skip_candidates_{market}.jsonl"
    c["skip_candidates_lifetime"] = _jsonl_count(_skip)

    # Cooling blocks today
    _cool = root / "reports" / "context" / "opportunity_cooling_blocks.jsonl"
    c["cooling_blocks_today"] = _jsonl_count(_cool,
                                                             filter_fn=lambda d: (
                                                                 d.get("asof") == asof
                                                                 and str(d.get("market","")).lower() == market))

    # ── Warnings ──
    if c["duplicate_position_ids"] > 0:
        diag.warnings.append(f"duplicate position_ids in Registry ({c['duplicate_position_ids']}) · investigate")
    if c["duplicate_live_tickers"] > 0:
        diag.warnings.append(f"same ticker ACTIVE across multiple runners ({c['duplicate_live_tickers']}) · canonical layer should collapse these")
    if c["new_today"] == 0:
        diag.warnings.append(f"NEW = 0 today · see new_opportunity_diagnostic_{market}.json for full funnel")
    if c["rotation_suggestions"] == 0 and c["new_today"] > 0:
        diag.warnings.append("NEW candidates present but ROTATE = 0 · threshold may be too high (see configs/opportunity_registry.yaml)")
    if c["universe_scanned"] < 100:
        diag.warnings.append(f"universe scanned = {c['universe_scanned']} · unusually small · check parquet cache")
    if c["recs_today"] > 0 and c["recs_today"] < 10:
        diag.warnings.append(f"only {c['recs_today']} recs today · recommender may be starved")

    return diag


def emit(root: Path, diag: DailyOpsDiagnostic) -> Path:
    p = (root / "reports" / "context"
             / f"daily_ops_diagnostic_{diag.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(diag), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(diag: DailyOpsDiagnostic) -> str:
    c = diag.counts
    return (f"universe={c.get('universe_scanned',0)} · recs={c.get('recs_today',0)} · "
                f"active={c.get('registry_active',0)} · new={c.get('new_today',0)} · "
                f"exits_today={c.get('exits_today',0)} · rotate={c.get('rotation_suggestions',0)} · "
                f"warnings={len(diag.warnings)}")
