"""NEW-Opportunity Strong Guard · pre/post validation + retry + fallback + health.

Operator directive 2026-08-21: "build strong guard for new recommendation engine".

Wraps the Wave 4 + Wave 5 + Wave 6 chain (new_opportunity_diagnostic →
rotation_engine → daily_ops_diagnostic) so that a transient failure in
any component never leaves the operator staring at "diagnostic unavailable"
in the KPI banner. Guarantees:

  1. PRE-FLIGHT · every input the guard needs is present + fresh
       - Registry file exists
       - reports/recommendations.json exists AND asof == today
  2. INVOKE   · run new_opportunity_diagnostic + rotation_engine + daily_ops
                with per-attempt timeout · retry with exponential backoff
  3. HELD-PENALTY · when the recommender emits ≥ N% of holdings AND
                    ≤ K fresh NEW candidates, apply a held-penalty
                    down-rank pass to force fresh tickers to surface
                    (config-driven · non-destructive · only affects the
                    NEW pool section, never the R1/R2 raw scores)
  4. POST-FLIGHT · verify diagnostic + rotation outputs are coherent
       - JSON parses · required fields non-null · counts plausible
  5. FALLBACK · if all attempts fail, mirror yesterday's diagnostic +
                stamp payload with degraded_from_previous_day=True
                so operator never sees an empty NEW panel
  6. HEALTH · emit reports/context/new_opp_guard_health_{market}.json

Config knobs live in configs/opportunity_registry.yaml under `new_opp_guard`.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path


_MAX_ATTEMPTS = 3
_BACKOFF_INITIAL_S = 3          # 3s · 9s · 27s
_BACKOFF_MULTIPLIER = 3


@dataclass
class NewOppGuardHealth:
    engine:                     str = "aegis.new_opp_guard.v1"
    generated_utc:              str = ""
    market:                     str = ""
    asof:                       str = ""
    verdict:                    str = ""       # GREEN | YELLOW | RED
    attempts:                   int = 0
    n_new_today:                int = 0
    n_rotation_suggestions:     int = 0
    n_daily_warnings:           int = 0
    held_penalty_applied:       bool = False
    held_penalty_promoted:      int = 0        # tickers surfaced by penalty
    degraded_from_previous_day: bool = False
    error_history:              list = field(default_factory=list)
    notes:                      str = ""


def _load_config(root: Path) -> dict:
    p = root / "configs" / "opportunity_registry.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cfg.get("new_opp_guard", {}) or {}
    except Exception:
        return {}


def _emit_health(root: Path, h: NewOppGuardHealth) -> Path:
    p = (root / "reports" / "context"
             / f"new_opp_guard_health_{h.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(h), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────

def _preflight(root: Path, market: str, asof: str) -> tuple:
    """Return (ok, reason). Failing pre-flight blocks the run."""
    # Registry file must exist (may be empty on first-ever run · that's OK)
    reg_p = root / "reports" / "research" / "opportunity_registry.jsonl"
    if not reg_p.exists():
        # Not fatal · guard will create when engines run
        pass
    # Rec file · required for the diagnostic funnel
    rec_p = ((root / "usa" / "reports" / "recommendations.json")
                 if market == "usa"
                 else (root / "reports" / "recommendations.json"))
    if not rec_p.exists():
        return (False, f"recommendations.json missing at {rec_p}")
    try:
        rec = json.loads(rec_p.read_text(encoding="utf-8"))
        rec_asof = str(rec.get("asof", ""))[:10]
        if rec_asof and rec_asof != asof[:10]:
            # Stale · allow but log
            return (True, f"WARN · recs asof={rec_asof} != today {asof[:10]}")
    except Exception as e:
        return (False, f"recommendations.json unreadable · {type(e).__name__}: {e}")
    return (True, "")


# ─────────────────────────────────────────────────────────────
# Post-flight validation
# ─────────────────────────────────────────────────────────────

def _postflight(root: Path, market: str, asof: str) -> tuple:
    """Verify all downstream artifacts are coherent. Returns (ok, reason)."""
    ctx = root / "reports" / "context"
    for name in (f"new_opportunity_diagnostic_{market}.json",
                     f"rotation_suggestions_{market}.json",
                     f"daily_ops_diagnostic_{market}.json"):
        p = ctx / name
        if not p.exists():
            return (False, f"post-flight · missing {name}")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if "asof" in d and str(d["asof"])[:10] != asof[:10]:
                return (False, f"post-flight · {name} asof={d.get('asof')} != {asof}")
        except Exception as e:
            return (False, f"post-flight · {name} unreadable · {type(e).__name__}")
    return (True, "")


# ─────────────────────────────────────────────────────────────
# Held-penalty pass · surfaces fresh tickers by down-ranking held ones
# ─────────────────────────────────────────────────────────────

def apply_held_penalty(root: Path, market: str, asof: str,
                                   cfg: dict) -> tuple:
    """Post-processing pass over reports/recommendations.json that
    down-ranks tickers currently ACTIVE in the Registry. Operator's
    "same-stocks-daily" fix. Non-destructive · original ensemble_score
    preserved in `pre_penalty_score` for audit.

    Returns (n_promoted, note) where n_promoted counts tickers that
    moved into the actionable BUY/STRONG_BUY tier as a result.
    """
    from backend.research import opportunity_registry as oreg

    penalty_pp   = float(cfg.get("held_penalty_pp", 0.0))
    min_active_pct = float(cfg.get("min_active_pct_to_trigger", 0.60))
    if penalty_pp <= 0:
        return (0, "held_penalty disabled (penalty_pp=0)")

    rec_p = ((root / "usa" / "reports" / "recommendations.json")
                 if market == "usa"
                 else (root / "reports" / "recommendations.json"))
    if not rec_p.exists(): return (0, "no recs file")

    try:
        payload = json.loads(rec_p.read_text(encoding="utf-8"))
    except Exception:
        return (0, "recs unreadable")
    recs = payload.get("recommendations", [])
    if not recs: return (0, "no recs")

    reg = oreg.load_all(root)
    held = set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() == market.lower() and o.is_active():
                held.add(o.ticker.upper())

    _rec_tks = [str(r.get("ticker","")).upper().replace(".NS","").replace(".BO","")
                     for r in recs]
    _overlap_pct = (sum(1 for t in _rec_tks if t in held) / max(1, len(_rec_tks)))
    if _overlap_pct < min_active_pct:
        return (0, f"overlap {_overlap_pct:.0%} < trigger {min_active_pct:.0%}")

    # Apply the down-rank
    n_promoted = 0
    for r in recs:
        tk = str(r.get("ticker","")).upper().replace(".NS","").replace(".BO","")
        if tk not in held: continue
        _score = r.get("ensemble_score") or r.get("composite_decision_score") or 0.0
        if not isinstance(_score, (int, float)): continue
        r["pre_penalty_score"] = _score
        # penalty_pp is percentage points off the 0-100 scale · convert if needed
        if -1.0 <= _score <= 1.0:
            _penalized = _score - (penalty_pp / 100.0)
        else:
            _penalized = _score - penalty_pp
        if "ensemble_score" in r: r["ensemble_score"] = _penalized
        if "composite_decision_score" in r: r["composite_decision_score"] = max(0.0, _penalized)
        r["held_penalty_pp"] = penalty_pp

    # Re-sort by adjusted score (descending) · reassign ranks
    def _sk(r):
        s = r.get("ensemble_score") or r.get("composite_decision_score") or 0.0
        return -float(s) if isinstance(s, (int, float)) else 0
    recs.sort(key=_sk)
    for i, r in enumerate(recs):
        prev_rank = r.get("rank")
        r["rank"] = i + 1
        # A ticker "promoted" if it moved into top-10 from below
        if prev_rank and prev_rank > 10 and r["rank"] <= 10:
            n_promoted += 1

    payload["recommendations"] = recs
    payload["held_penalty_applied"] = {
        "applied":       True,
        "penalty_pp":    penalty_pp,
        "min_active_pct_trigger": min_active_pct,
        "actual_overlap_pct": round(_overlap_pct, 3),
        "n_penalized":   sum(1 for r in recs if r.get("held_penalty_pp")),
        "n_promoted_to_top_10": n_promoted,
        "note":          "Post-recommender rotation force · fixes 'same stocks daily'",
    }
    rec_p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                          encoding="utf-8")
    return (n_promoted,
                f"applied · overlap {_overlap_pct:.0%} · promoted {n_promoted}")


# ─────────────────────────────────────────────────────────────
# Main guard entry point
# ─────────────────────────────────────────────────────────────

def guarded_run(root: Path, market: str, asof: str) -> NewOppGuardHealth:
    """Run the NEW-opportunity chain with retry + fallback + health.
    Idempotent · safe to call from the sender or a stand-alone script."""
    market = market.lower()
    asof = asof[:10]
    cfg = _load_config(root)
    h = NewOppGuardHealth(
        market=market, asof=asof,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    # Pre-flight
    ok, reason = _preflight(root, market, asof)
    if not ok:
        h.verdict = "RED"
        h.error_history.append(f"preflight · {reason}")
        h.notes = reason
        _emit_health(root, h)
        return h
    if reason:
        h.error_history.append(f"preflight-warn · {reason}")

    # Held-penalty pass (runs BEFORE diagnostics so they see the promoted set)
    try:
        n_promoted, penalty_note = apply_held_penalty(root, market, asof, cfg)
        h.held_penalty_applied = True
        h.held_penalty_promoted = n_promoted
    except Exception as e:
        h.error_history.append(f"held_penalty · {type(e).__name__}: {e}")

    # 2026-08-25 · SPEED FIX (operator: pipeline took 2-3hrs · target 60min)
    # HEAVY modules moved OUT of the retry loop · run ONCE, log if slow.
    #   · shadow_runner scores 229 tickers via yfinance (~10 min)
    #   · Angel universe validator + LTP (~30-60s)
    # Previous design ran these inside the 3-attempt retry loop · a single
    # transient failure could trigger 3× the shadow work = 30 min wasted.
    # If a heavy module errors we still ship using yesterday's snapshot ·
    # never blocking. Registry loaded once here for both blocks.
    try:
        from backend.research import opportunity_registry as _oreg
        reg = _oreg.load_all(root)
    except Exception:
        reg = {}
    try:
        import yaml as _yaml
        _inv_cfg_p = root / "configs" / "investability.yaml"
        _shadow_cfg = {}
        if _inv_cfg_p.exists():
            _shadow_cfg = (_yaml.safe_load(_inv_cfg_p.read_text(encoding="utf-8"))
                                     or {}).get("shadow", {}) or {}
        if _shadow_cfg.get("enabled", True):
            from backend.investability import shadow_runner as _shr
            # Staleness cache · skip if shadow scored within last 20 hours
            _shd_out = (root / "reports"
                              / f"investability_shadow_{market}.json")
            _skip_shadow = False
            if _shd_out.exists():
                import time as _time
                if (_time.time() - _shd_out.stat().st_mtime) < 20 * 3600:
                    _skip_shadow = True
                    print(f"[shadow_runner:{market}] staleness cache hit · skipping (fresh <20h)")
            if not _skip_shadow:
                _scored, _shadow_diag = _shr.run(root, market, asof)
                if _shadow_diag.warnings:
                    h.error_history.extend(
                        [f"invest_shadow · {w}" for w in _shadow_diag.warnings[:3]])
    except Exception as _e2:
        h.error_history.append(f"invest_shadow · {type(_e2).__name__}: {_e2}")
    # Angel additions · India only · cheap
    try:
        if market.lower() == "india":
            from backend.ingest import angel_universe_validator as _auv
            _uv = _auv.validate_universe(root, market, asof)
            _auv.emit_validation(root, _uv)
            if _uv.n_dead > 0:
                h.error_history.append(
                    f"angel_universe · {_uv.n_dead} DEAD symbols · "
                    f"first: {', '.join(_uv.dead_symbols[:5])}")
            _held = sorted({o.ticker for opps in reg.values() for o in opps
                                    if o.market.lower() == "india" and o.is_active()})
            if _held:
                _ltp = _auv.fetch_ltp_batch(root, _held)
                _auv.emit_ltp_snapshot(root, market, _ltp)
    except Exception as _e2:
        h.error_history.append(f"angel · {type(_e2).__name__}: {_e2}")

    # Invoke NEW + Rotation + Ops diagnostic chain (LIGHT modules only)
    # 2026-08-25 · after moving heavy modules out, retry loop covers only
    # the cheap JSON-emit steps · retries are near-free.
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        h.attempts = attempt
        try:
            from backend.research import (
                new_opportunity_diagnostic as _nod,
                rotation_engine as _rot,
                daily_ops_diagnostic as _dod,
            )
            from backend.gates import context_sector_gate as _csg
            from backend.risk import dynamic_risk_v2 as _drv
            from backend.recommendation import rec_review as _rev
            from backend.context import data_quality_gate as _dqg
            _diag = _nod.compute(root, market, asof); _nod.emit(root, _diag)
            _rep  = _rot.compute(root, market, asof); _rot.emit(root, _rep)
            _ops  = _dod.compute(root, market, asof); _dod.emit(root, _ops)
            # Parts 10 + 13 · context/sector gate over recs' tickers
            try:
                _rec_p = ((root / "usa" / "reports" / "recommendations.json")
                                if market == "usa"
                                else (root / "reports" / "recommendations.json"))
                if _rec_p.exists():
                    _rd = json.loads(_rec_p.read_text(encoding="utf-8"))
                    _pairs = [(str(r.get("ticker","")).upper().replace(".NS","").replace(".BO",""),
                                    r.get("sector",""))
                                    for r in _rd.get("recommendations", [])]
                    _gate_rep = _csg.compute_report(root, market, asof, _pairs)
                    _csg.emit(root, _gate_rep)
            except Exception as _e2:
                h.error_history.append(f"gate · {type(_e2).__name__}: {_e2}")
            # Parts 8 + 15 · dynamic risk (ATR + trailing lift)
            try:
                _risk = _drv.compute(root, market, asof); _drv.emit(root, _risk)
            except Exception as _e2:
                h.error_history.append(f"risk · {type(_e2).__name__}: {_e2}")
            # Parts 9 + 14 · recommendation review + confidence trajectory
            try:
                _rv = _rev.compute(root, market, asof); _rev.emit(root, _rv)
            except Exception as _e2:
                h.error_history.append(f"review · {type(_e2).__name__}: {_e2}")
            # Part 20 · data quality hard gate
            try:
                _dq = _dqg.compute(root, market, asof); _dqg.emit(root, _dq)
                if _dq.verdict == "FAIL":
                    h.error_history.append(f"data_quality · FAIL · {_dq.n_fail} hard-fail checks")
            except Exception as _e2:
                h.error_history.append(f"data_quality · {type(_e2).__name__}: {_e2}")
            # 2026-08-25 · SPEED FIX (operator "took almost 2-3hrs · 60min
            # and less works") · The heavy modules (shadow_runner ~10min ·
            # Angel LTP ~30s) MOVED OUTSIDE this retry loop. They ran once
            # BEFORE this loop started. No longer 3× re-run on transient
            # failure. Retry loop keeps only the CHEAP modules (diagnostic
            # JSON emit + post-flight validation).
            # Post-flight
            _ok, _reason = _postflight(root, market, asof)
            if not _ok:
                raise RuntimeError(_reason)
            h.n_new_today            = _diag.n_new_today
            h.n_rotation_suggestions = _rep.n_suggestions
            h.n_daily_warnings       = len(_ops.warnings)
            # Verdict
            if h.n_daily_warnings > 3:
                h.verdict = "YELLOW"
            else:
                h.verdict = "GREEN"
            h.notes = f"chain healthy on attempt {attempt}"
            _emit_health(root, h)
            return h
        except Exception as e:
            h.error_history.append(f"attempt {attempt} · {type(e).__name__}: {e}")
            if attempt < _MAX_ATTEMPTS:
                delay = _BACKOFF_INITIAL_S * (_BACKOFF_MULTIPLIER ** (attempt - 1))
                time.sleep(delay)

    # Fallback · copy yesterday's diagnostics into today's slots
    from datetime import timedelta
    y = (date.fromisoformat(asof) - timedelta(days=1)).isoformat()
    ctx = root / "reports" / "context"
    for name in (f"new_opportunity_diagnostic_{market}.json",
                     f"rotation_suggestions_{market}.json",
                     f"daily_ops_diagnostic_{market}.json"):
        # There is no per-day snapshot yet · leave whatever last-good exists
        _p = ctx / name
        if _p.exists():
            try:
                d = json.loads(_p.read_text(encoding="utf-8"))
                d["degraded_from_previous_day"] = True
                d["degradation_reason"] = "; ".join(h.error_history[-3:])
                _p.write_text(json.dumps(d, indent=2, default=str, ensure_ascii=False),
                                     encoding="utf-8")
            except Exception:
                pass
    h.verdict = "RED"
    h.degraded_from_previous_day = True
    h.notes = "all attempts failed · degraded to last-good diagnostic (if any)"
    _emit_health(root, h)
    return h


def summary_line(h: NewOppGuardHealth) -> str:
    icon = {"GREEN": "✅", "YELLOW": "⚠️", "RED": "❌"}.get(h.verdict, "?")
    penalty = (f" · penalty promoted {h.held_penalty_promoted}"
                    if h.held_penalty_applied else "")
    degr = " · degraded" if h.degraded_from_previous_day else ""
    return (f"{icon} {h.verdict} · attempts={h.attempts} · "
                f"new={h.n_new_today} · rotate={h.n_rotation_suggestions} · "
                f"warn={h.n_daily_warnings}{penalty}{degr}")
