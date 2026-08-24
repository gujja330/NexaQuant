"""AEGIS Portfolio Rotation Engine · § 26 + § 27 of 2026-08-21 directive.

Operator: "Every day compare BEST NEW OPPORTUNITY vs WORST EXISTING POSITION.
This is the portfolio rotation engine. Is capital better allocated to ABC
than continuing LUPIN? If yes: LUPIN → REDUCE/EXIT · ABC → NEW OPPORTUNITY."

Design principles (no engine changes · pure suggestion layer):
  * Reads today's Registry + today's recommendations
  * Ranks existing by weakness (worst P&L first · lowest score first)
  * Ranks candidate NEW opportunities by strength (best rank first)
  * Emits ROTATE suggestions when the strength-gap exceeds threshold
  * Suggestions are ADVISORY · operator makes the final trade decision
  * Never automatically closes a position · sender surfaces the suggestion
    in a Portfolio KPI panel and (optionally) tags candidate rows

Configuration in configs/opportunity_registry.yaml · block "rotation":
  min_alpha_delta_pp:   minimum score gap for a suggestion (default 5.0)
  min_holding_days:     do not suggest rotation for positions <N days old
                        (default 5 · give a position time to work)
  max_suggestions:      cap on per-day suggestions (default 3)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

from backend.research import opportunity_registry as oreg


SCHEMA_FINGERPRINT = "aegis.rotation_engine.v1.20260821"


@dataclass
class RotationSuggestion:
    existing_ticker:   str = ""
    existing_runner:   str = ""
    existing_pnl_pct:  float | None = None
    existing_days:     int | None = None
    new_ticker:        str = ""
    new_runner:        str = ""
    new_rank:          int | None = None
    new_score:         float | None = None
    alpha_delta_pp:    float | None = None    # new_score - existing_score
    rationale:         str = ""


@dataclass
class RotationReport:
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    asof:               str = ""
    market:             str = ""
    run_utc:            str = ""
    n_existing:         int = 0
    n_new_candidates:   int = 0
    n_suggestions:      int = 0
    suggestions:        list = field(default_factory=list)
    threshold_pp:       float = 5.0
    reason_if_zero:     str = ""


def _load_config(root: Path) -> dict:
    p = root / "configs" / "opportunity_registry.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("rotation", {})
    except Exception:
        return {}


def _load_recs(root: Path, market: str) -> list:
    p = ((root / "usa" / "reports" / "recommendations.json")
             if market == "usa" else (root / "reports" / "recommendations.json"))
    if not p.exists(): return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("recommendations", []) if isinstance(d, dict) else []
    except Exception:
        return []


def _bar_close(root: Path, ticker: str, market: str) -> float | None:
    try:
        import pandas as pd
        d = (root / "usa" / "data" / "raw" / "us" if market == "usa"
                 else root / "data" / "raw" / "india")
        bare = ticker.upper().replace(".NS","").replace(".BO","")
        p = d / f"{bare}_D1.parquet"
        if not p.exists(): return None
        return float(pd.read_parquet(p)["close"].iloc[-1])
    except Exception:
        return None


def compute(root: Path, market: str, asof: str) -> RotationReport:
    """Compute rotation suggestions for one market on one date."""
    from datetime import date
    market = market.lower()
    asof = asof[:10]
    cfg = _load_config(root)
    threshold_pp   = float(cfg.get("min_alpha_delta_pp", 5.0))
    min_hold_days  = int(cfg.get("min_holding_days", 5))
    max_sugs       = int(cfg.get("max_suggestions", 3))
    report = RotationReport(
        asof=asof, market=market, threshold_pp=threshold_pp,
        run_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    reg = oreg.load_all(root)

    # Existing ACTIVE positions with computed P&L
    existing = []
    for opps in reg.values():
        for opp in opps:
            if opp.market.lower() != market: continue
            if not opp.is_active(): continue
            # Skip too-fresh positions (min holding period)
            try:
                age = (date.fromisoformat(asof)
                            - date.fromisoformat(opp.created_date)).days
            except Exception:
                age = 0
            if age < min_hold_days: continue
            # Compute P&L from initial_score vs live bar (best-effort)
            live = _bar_close(root, opp.ticker, market)
            # We do not have entry_price in Registry · use initial_score
            # as a soft proxy for "how highly ranked when entered". Weak
            # existing = low score + low live change. Since we can't join
            # to entry price here, use initial_rank (higher rank = weaker).
            existing.append({
                "ticker":  opp.ticker,
                "runner":  opp.runner,
                "days":    age,
                "initial_rank":  opp.initial_rank,
                "initial_score": opp.initial_score,
                "live":    live,
            })
    report.n_existing = len(existing)

    # NEW candidates · recs whose ticker is NOT in ACTIVE Registry
    held_tks = {e["ticker"].upper() for e in existing}
    recs = _load_recs(root, market)
    new_cands = []
    for r in recs:
        tk = str(r.get("ticker", "")).upper().replace(".NS","").replace(".BO","")
        if not tk or tk in held_tks: continue
        new_cands.append({
            "ticker":  tk,
            "runner":  "R1",   # recs.json is R1-context · R2 would show separately
            "rank":    r.get("rank"),
            "score":   r.get("composite_decision_score") or r.get("ensemble_score"),
            "action":  r.get("action") or r.get("recommendation"),
            "sector":  r.get("sector", ""),
        })
    report.n_new_candidates = len(new_cands)

    # Rank existing by weakness (worst rank first · then oldest)
    existing_sorted = sorted(existing,
                                        key=lambda x: (
                                            -(x.get("initial_rank") or 0),
                                            -(x.get("days") or 0),
                                        ))
    # Rank NEW by strength (lowest rank number = strongest)
    new_sorted = sorted(new_cands,
                                key=lambda x: (x.get("rank") or 99))

    # Pair weakest existing with strongest NEW · propose rotation when
    # the strength gap exceeds threshold
    suggestions = []
    _used_new: set = set()
    for weak in existing_sorted:
        if len(suggestions) >= max_sugs: break
        for strong in new_sorted:
            if strong["ticker"] in _used_new: continue
            # Alpha delta · use composite score if both have it, else
            # fall back to rank delta scaled to points.
            weak_score = weak.get("initial_score")
            strong_score = strong.get("score")
            if (isinstance(weak_score, (int, float))
                and isinstance(strong_score, (int, float))):
                delta_pp = round((strong_score - weak_score) * 100, 2)
            else:
                weak_rank = weak.get("initial_rank") or 15
                strong_rank = strong.get("rank") or 1
                delta_pp = round((weak_rank - strong_rank) * 1.0, 2)
            if delta_pp >= threshold_pp:
                suggestions.append(RotationSuggestion(
                    existing_ticker=weak["ticker"],
                    existing_runner=weak["runner"],
                    existing_days=weak.get("days"),
                    new_ticker=strong["ticker"],
                    new_runner=strong["runner"],
                    new_rank=strong.get("rank"),
                    new_score=strong_score,
                    alpha_delta_pp=delta_pp,
                    rationale=(
                        f"NEW {strong['ticker']} (rank {strong.get('rank') or '?'}) "
                        f"outranks existing {weak['ticker']} "
                        f"(rank {weak.get('initial_rank') or '?'}) "
                        f"by {delta_pp}pp · consider rotating"
                    ),
                ))
                _used_new.add(strong["ticker"])
                break

    report.suggestions = [asdict(s) for s in suggestions]
    report.n_suggestions = len(suggestions)
    if report.n_suggestions == 0:
        if report.n_new_candidates == 0:
            report.reason_if_zero = "no NEW candidates today (see NEW opportunity diagnostic)"
        elif report.n_existing == 0:
            report.reason_if_zero = "no existing holdings meet min_holding_days threshold"
        else:
            report.reason_if_zero = (
                f"no candidate exceeds threshold {threshold_pp}pp over "
                f"weakest existing (existing={report.n_existing} · "
                f"new={report.n_new_candidates})")
    return report


def emit(root: Path, report: RotationReport) -> Path:
    p = (root / "reports" / "context"
             / f"rotation_suggestions_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(report: RotationReport) -> str:
    if report.n_suggestions == 0:
        return f"ROTATE = 0 · {report.reason_if_zero or 'no suggestions'}"
    top = report.suggestions[0]
    if len(report.suggestions) == 1:
        return (f"ROTATE · {top['existing_ticker']} → {top['new_ticker']} "
                    f"(+{top.get('alpha_delta_pp') or 0}pp)")
    return (f"ROTATE · {report.n_suggestions} suggestions · "
                f"lead: {top['existing_ticker']} → {top['new_ticker']} "
                f"(+{top.get('alpha_delta_pp') or 0}pp)")
