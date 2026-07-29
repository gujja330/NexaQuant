"""Investor-Actionable enrichment engine · pure deterministic mapper.

Consumes existing rec fields (percentile_action, ensemble_score,
calibrated_confidence, bull_case, bear_case, key_risks,
suggested_holding_period_days, entry_zone.current, signal_quality) and
optional context artifacts (rotation_plan, lifecycle_records,
dynamic_holding_decisions) to emit these investor-facing sub-objects:

  investor_action        = {entry, if_holding, user_facing_label, is_actionable}
  position_plan          = {suggested_allocation_pct, risk_level,
                            max_capital_exposure_pct, time_horizon_days,
                            time_horizon_bucket, entry_zone{...},
                            dynamic_holding_reason?}
  why                    = {top_reasons[], top_risks[]}
  rotation_intelligence  = {should_rotate, replacement_ticker, edge,
                            expected_alpha_delta, keep_score,
                            candidate_score, reason} · CEO cycle 3
  lifecycle_state        = {current_state, previous_state,
                            ts_last_transition, n_events} · CEO cycle 3

All context artifacts are OPTIONAL · missing artifacts degrade gracefully:
the enricher never crashes because a downstream engine hasn't run yet.

CEO cycle 3 · Article 101.2 · pure enrichment · surfaces existing engine
outputs into the operator-facing rec view. No new analytics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Mapping, MutableMapping

SCHEMA_FINGERPRINT = "aegis.recommendation.investor_actionable.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.investor_actionable.v1"


# ── Dual-decision mapping ────────────────────────────────────
# Entry Decision (someone who does NOT own the stock)
#   STRONG_BUY  → BUY   (enter aggressively)
#   BUY         → BUY   (enter)
#   HOLD        → WAIT  (watchlist · not enough conviction to enter)
#   SELL        → AVOID (don't enter now)
#   STRONG_SELL → AVOID (don't enter · negative outlook)
ENTRY_MAP = {
    "STRONG_BUY":  "BUY",
    "BUY":         "BUY",
    "HOLD":        "WAIT",
    "SELL":        "AVOID",
    "STRONG_SELL": "AVOID",
    "INSUFFICIENT_DATA": "WAIT",
}

# Existing-Position Decision (someone who ALREADY owns the stock)
#   STRONG_BUY  → ADD    (accumulate more)
#   BUY         → HOLD   (stay put · maybe add on dips)
#   HOLD        → HOLD   (keep holding)
#   SELL        → REDUCE (trim exposure · don't fully exit)
#   STRONG_SELL → EXIT   (close position)
IF_HOLDING_MAP = {
    "STRONG_BUY":  "ADD",
    "BUY":         "HOLD",
    "HOLD":        "HOLD",
    "SELL":        "REDUCE",
    "STRONG_SELL": "EXIT",
    "INSUFFICIENT_DATA": "HOLD",
}

# Human-readable one-liner combining both decisions
LABEL_MAP = {
    "STRONG_BUY":  "🟢 Strong Buy · Add if already holding",
    "BUY":         "🟢 Buy · Hold if already holding",
    "HOLD":        "🟡 Watchlist · Keep holding if you own it",
    "SELL":        "🔴 Avoid new entry · Reduce if you own it",
    "STRONG_SELL": "⛔ Avoid new entry · Exit if you own it",
    "INSUFFICIENT_DATA": "⚪ No signal · Wait for better evidence",
}

# is_actionable: does the operator need to do anything today?
ACTIONABLE_ENTRY = {"BUY"}                  # entry-side action needed
ACTIONABLE_IF_HOLDING = {"ADD", "REDUCE", "EXIT"}  # position-side action needed

# ── Time-horizon buckets (from suggested_holding_period_days) ─
HORIZON_BUCKETS = [
    (1,  20,  "swing",     "Days-to-weeks · exit near target or on stop"),
    (21, 90,  "position",  "Weeks-to-months · trend-following"),
    (91, 999, "long_term", "Months+ · compounding thesis"),
]

# ── Position sizing table (preview % · real sizing in risk engine) ──
# Values are % of TOTAL capital · capped at per-ticker budget (6%).
DEFAULT_ALLOC_PCT = {
    "STRONG_BUY":  5.0,
    "BUY":         3.0,
    "HOLD":        0.0,
    "SELL":        0.0,
    "STRONG_SELL": 0.0,
    "INSUFFICIENT_DATA": 0.0,
}
PER_TICKER_CAP_PCT = 6.0   # matches budget_snapshot.per_ticker_cap

# ── Risk level from signal_quality + confidence ─────────────
def _risk_level(signal_quality: str, calibrated_confidence: float) -> str:
    sq = (signal_quality or "").upper()
    if sq == "STRONG" and calibrated_confidence >= 0.02:
        return "moderate"
    if sq == "MODERATE":
        return "moderate"
    if sq == "WEAK":
        return "elevated"
    return "moderate"


# ── Entry zone / stop / target math (ATR-flavoured, %-based fallback) ──
# Stop is 6% by default (retail-friendly · calibrated to weekly ATR).
# Targets are 1:2 and 1:4 risk-reward.
DEFAULT_STOP_PCT   = 0.06
BUY_ZONE_WIDTH_PCT = 0.01   # ideal buy zone = current ±1%


def _horizon_bucket(days: int | float | None) -> tuple[str, str]:
    """Return (bucket_name, description). Defaults to position if unknown."""
    try:
        d = int(days) if days is not None else 45
    except (TypeError, ValueError):
        d = 45
    d = max(1, d)
    for lo, hi, name, desc in HORIZON_BUCKETS:
        if lo <= d <= hi:
            return name, desc
    return "position", "Weeks-to-months · trend-following"


def _entry_zone(current_price: float | None,
                    action: str,
                    stop_pct: float = DEFAULT_STOP_PCT,
                    zone_pct: float = BUY_ZONE_WIDTH_PCT) -> dict:
    """Derive entry zone / stop / two targets.

    Long positions (BUY/STRONG_BUY): buy zone below current, stop below,
    targets above. Exit signals (SELL/STRONG_SELL): no entry zone.
    WAIT/HOLD: minimal zone (only current price + note).
    """
    try:
        cp = float(current_price) if current_price is not None else None
    except (TypeError, ValueError):
        cp = None
    if cp is None or cp <= 0:
        return {"current_price": None, "note": "current price unavailable"}
    if action in ("STRONG_BUY", "BUY"):
        stop = round(cp * (1.0 - stop_pct), 2)
        target_1 = round(cp * (1.0 + 2.0 * stop_pct), 2)  # 1:2 R:R
        target_2 = round(cp * (1.0 + 4.0 * stop_pct), 2)  # 1:4 R:R
        return {
            "current_price":      round(cp, 2),
            "ideal_buy_low":      round(cp * (1.0 - zone_pct), 2),
            "ideal_buy_high":     round(cp * (1.0 + zone_pct), 2),
            "stop_loss":          stop,
            "target_1":           target_1,
            "target_2":           target_2,
            "risk_reward_ratio":  "1:2 (T1) · 1:4 (T2)",
            "risk_per_share_pct": round(stop_pct * 100, 2),
        }
    if action in ("SELL", "STRONG_SELL"):
        # For exit signals: show current price + suggested exit range
        return {
            "current_price": round(cp, 2),
            "exit_range_low":  round(cp * 0.99, 2),
            "exit_range_high": round(cp * 1.01, 2),
            "note":            "exit if holding · no new entry recommended",
        }
    # HOLD / WAIT / INSUFFICIENT_DATA: neutral
    return {
        "current_price": round(cp, 2),
        "note":          "watchlist · re-check when signal strengthens",
    }


def _top_reasons(bull_case: str | None, ensemble_score: float,
                    top_features: list | None) -> list[str]:
    """Extract top reasons from bull_case (semicolon-separated) + score band."""
    reasons: list[str] = []
    if bull_case and isinstance(bull_case, str):
        for chunk in bull_case.split(";"):
            c = chunk.strip().rstrip(".").strip()
            if c:
                reasons.append(c)
    # Append score-derived context
    try:
        s = float(ensemble_score)
        if abs(s) >= 0.04:
            reasons.append(f"ensemble score {s:+.4f} (top-percentile signal)")
    except (TypeError, ValueError):
        pass
    # Include top predictive feature names if provided
    if top_features and isinstance(top_features, list):
        names = [str(f.get("name") or f.get("feature") or "").strip()
                  for f in top_features[:2] if isinstance(f, dict)]
        names = [n for n in names if n]
        if names:
            reasons.append("driven by " + ", ".join(names))
    return reasons[:5]   # cap at 5


def _top_risks(bear_case: str | None, key_risks: list | None,
                  disagreement: bool) -> list[str]:
    """Extract top risks from bear_case + key_risks + disagreement flag."""
    risks: list[str] = []
    if bear_case and isinstance(bear_case, str):
        for chunk in bear_case.split(";"):
            c = chunk.strip().rstrip(".").strip()
            if c:
                risks.append(c)
    if key_risks and isinstance(key_risks, list):
        for r in key_risks[:3]:
            rs = str(r).strip()
            if rs and rs not in risks:
                risks.append(rs)
    if disagreement:
        risks.append("model disagreement · signal not unanimous")
    return risks[:5]


# ── Rotation Intelligence (CEO cycle 3 · Phase 8 · HIGHEST priority) ──
# Per-rec hypothetical rotation: treat every rec as "if you owned this today"
# and compute the rotation decision against the best BUY candidate on the
# board. This makes every HOLD/WATCH actionable — never "just hold blindly".

# Institutional thresholds (mirror capital_rotation.engine constants where
# feasible; local copy here to keep enricher a self-contained pure mapper).
ROTATION_EDGE_THRESHOLD = 0.05   # ensemble-score delta above which rotation is recommended
ROTATION_ALPHA_MULTIPLIER = 100.0   # convert score delta → % expected alpha proxy


def _rotation_for_rec(rec: Mapping,
                          all_recs: Sequence[Mapping] | None) -> dict:
    """Compute hypothetical rotation for a single rec.

    Ask: "if the operator owned this ticker today, would rotating to the
    best BUY candidate improve expected alpha meaningfully?"

    Comparison is score-based (ensemble_score) with confidence gate. We do
    NOT re-implement capital_rotation.engine — we use its principle
    (best-alternative − current) with a small threshold. If the engine
    output (rotation_plan.json) is passed via `all_recs` context, we prefer
    that; otherwise we derive from the rec cross-section directly.
    """
    ticker = str(rec.get("ticker") or "")
    my_score = float(rec.get("ensemble_score") or 0.0)
    my_conf = float(rec.get("calibrated_confidence") or 0.0)
    my_action = str(rec.get("percentile_action") or rec.get("action") or "HOLD").upper()

    # Find best BUY-side alternative across the batch, excluding self.
    best_ticker = None
    best_score = None
    if all_recs:
        for other in all_recs:
            ot = str(other.get("ticker") or "")
            if not ot or ot == ticker:
                continue
            oa = str(other.get("percentile_action") or other.get("action") or "").upper()
            if oa not in ("STRONG_BUY", "BUY"):
                continue
            osc = float(other.get("ensemble_score") or 0.0)
            if best_score is None or osc > best_score:
                best_score = osc
                best_ticker = ot

    # No candidate universe → cannot rotate
    if best_ticker is None or best_score is None:
        return {
            "should_rotate":         False,
            "replacement_ticker":    None,
            "edge":                  None,
            "expected_alpha_delta_pct": None,
            "keep_score":            round(my_score, 4),
            "candidate_score":       None,
            "reason":                "no BUY/STRONG_BUY alternative on current board",
        }

    edge = best_score - my_score
    should_rotate = edge > ROTATION_EDGE_THRESHOLD

    # Never recommend rotating out of a STRONG_BUY into another STRONG_BUY
    # (would create churn without signal). Only recommend rotation when
    # the current position is NOT already actionable-entry.
    if my_action in ("STRONG_BUY", "BUY") and should_rotate:
        # If we're already in the highest-conviction bucket and the
        # candidate is only marginally better, hold instead of churning.
        should_rotate = edge > 2 * ROTATION_EDGE_THRESHOLD

    # Expected alpha delta (proxy · score-magnitude scaled to %). For a
    # long-only advisory platform this is directional guidance, not a
    # precise return estimate.
    alpha_delta_pct = round(edge * ROTATION_ALPHA_MULTIPLIER, 2)

    if should_rotate:
        reason = (f"rotate → {best_ticker} · candidate_score {best_score:+.4f} "
                    f"vs current {my_score:+.4f} · edge {edge:+.4f} > "
                    f"threshold {ROTATION_EDGE_THRESHOLD} · expected alpha +{alpha_delta_pct:.2f}%")
    else:
        if my_action in ("STRONG_BUY", "BUY"):
            reason = (f"keep · already in top bucket · candidate edge {edge:+.4f} "
                        f"insufficient to justify churn")
        else:
            reason = (f"keep · candidate edge {edge:+.4f} ≤ threshold "
                        f"{ROTATION_EDGE_THRESHOLD} · rotation would not add expected alpha")

    return {
        "should_rotate":               bool(should_rotate),
        "replacement_ticker":          best_ticker if should_rotate else None,
        "edge":                        round(edge, 4),
        "expected_alpha_delta_pct":    alpha_delta_pct if should_rotate else 0.0,
        "keep_score":                  round(my_score, 4),
        "candidate_score":             round(best_score, 4),
        "reason":                      reason,
    }


# ── Lifecycle state surface (CEO cycle 3 · Phase 13 · Recommendation Lifecycle) ─
# Maps existing 9-state RecommendationState from state_machine.py to a
# per-rec block. Context artifact `lifecycle_records` is
# {ticker: {current_state, events[...]}} from recommendation_lifecycle.json.
def _lifecycle_for_rec(rec: Mapping,
                          lifecycle_records: Mapping | None) -> dict:
    ticker = str(rec.get("ticker") or "")
    if not lifecycle_records or ticker not in lifecycle_records:
        return {
            "current_state":       "UNTRACKED",
            "previous_state":      None,
            "ts_last_transition":  None,
            "n_events":            0,
            "reason":              "no lifecycle record · rec is fresh or lifecycle engine has not run",
        }
    rec_lc = lifecycle_records[ticker] or {}
    events = rec_lc.get("events", []) or []
    current = str(rec_lc.get("current_state") or "UNTRACKED")
    previous = None
    ts_last = None
    if len(events) >= 1:
        ts_last = events[-1].get("ts_utc")
    if len(events) >= 2:
        previous = events[-2].get("state")
    return {
        "current_state":       current,
        "previous_state":      previous,
        "ts_last_transition":  ts_last,
        "n_events":            len(events),
    }


# ── Dynamic Holding surface (CEO cycle 3 · Phase 7) ─────────
# Reads composite output from reports/dynamic_holding.json instead of
# using the fixed rec.suggested_holding_period_days.
def _dynamic_holding_days(ticker: str,
                             dynamic_holding_decisions: Mapping | None,
                             fallback_days: int) -> tuple[int, str | None]:
    """Return (holding_days, reason_or_None) preferring the dynamic engine."""
    if not dynamic_holding_decisions or ticker not in dynamic_holding_decisions:
        return fallback_days, None
    d = dynamic_holding_decisions[ticker] or {}
    days = d.get("holding_days")
    reason = d.get("reason")
    try:
        di = int(days) if days is not None else fallback_days
    except (TypeError, ValueError):
        di = fallback_days
    return max(1, di), reason


# ── Evolution surface (CEO cycle 4 · Recommendation Performance & Evolution) ─
# Compares today's rec against the previous snapshot to answer the
# operator's "how has this recommendation changed since previous run?"
# question. Depends on backend.recommendation.snapshot.store persisting
# yesterday's payload. First-ever run → all deltas are None (fresh rec).
def _evolution_for_rec(rec: Mapping,
                          previous_ticker_map: Mapping | None,
                          asof: str | None,
                          history_asof_map: Mapping | None = None) -> dict:
    ticker = str(rec.get("ticker") or "")
    prev = (previous_ticker_map or {}).get(ticker)
    if not prev:
        return {
            "is_new":                    True,
            "days_recommended":          1,
            "previous_asof":             None,
            "rank_change":               None,
            "score_change":              None,
            "action_change":             None,
            "confidence_change":         None,
            "lifecycle_change":          None,
            "allocation_change_pct":     None,
            "narrative":                 "NEW recommendation · no prior snapshot",
        }
    prev_asof = prev.get("asof") or (previous_ticker_map or {}).get("__asof__")
    # Days recommended: use history_asof_map (ticker → first-seen date) if
    # provided; else conservatively return 2 (yesterday + today).
    days_rec = 2
    if history_asof_map and ticker in history_asof_map:
        try:
            from datetime import date as _date
            first = _date.fromisoformat(str(history_asof_map[ticker])[:10])
            today = _date.fromisoformat(str(asof)[:10]) if asof else _date.today()
            days_rec = max(1, (today - first).days + 1)
        except (ValueError, TypeError):
            days_rec = 2

    def _delta(now, was, ndigits=4):
        try:
            n = float(now) if now is not None else None
            w = float(was) if was is not None else None
        except (TypeError, ValueError):
            return None
        if n is None or w is None:
            return None
        return round(n - w, ndigits)

    prev_action = prev.get("percentile_action") or prev.get("action") or "HOLD"
    curr_action = rec.get("percentile_action") or rec.get("action") or "HOLD"
    action_changed = str(prev_action).upper() != str(curr_action).upper()

    prev_lc = ((prev.get("lifecycle_state") or {}).get("current_state")
                or prev.get("lifecycle_current_state"))
    curr_lc = (rec.get("lifecycle_state") or {}).get("current_state")
    # Normalize: None/missing/UNTRACKED are all equivalent (no lifecycle yet).
    def _norm_lc(v):
        u = str(v or "").upper()
        return "" if u in ("", "UNTRACKED", "NONE") else u
    lifecycle_changed = _norm_lc(prev_lc) != _norm_lc(curr_lc) and (
        _norm_lc(prev_lc) != "" or _norm_lc(curr_lc) != ""
    )

    prev_alloc = ((prev.get("position_plan") or {}).get("suggested_allocation_pct"))
    curr_alloc = ((rec.get("position_plan") or {}).get("suggested_allocation_pct"))

    parts: list[str] = []
    if action_changed:
        parts.append(f"action {prev_action} → {curr_action}")
    if lifecycle_changed:
        parts.append(f"lifecycle {prev_lc} → {curr_lc}")
    rank_d = _delta(rec.get("rank"), prev.get("rank"), 0)
    if rank_d not in (None, 0.0):
        arrow = "↑" if rank_d < 0 else "↓"   # lower rank number = better
        parts.append(f"rank {arrow}{abs(int(rank_d))}")
    alloc_d = _delta(curr_alloc, prev_alloc, 2)
    if alloc_d not in (None, 0.0):
        parts.append(f"allocation {prev_alloc}% → {curr_alloc}% ({alloc_d:+.2f}pp)")
    conf_d = _delta(rec.get("calibrated_confidence"), prev.get("calibrated_confidence"))
    if conf_d not in (None, 0.0):
        parts.append(f"confidence {conf_d:+.4f}")
    score_d = _delta(rec.get("ensemble_score"), prev.get("ensemble_score"))
    if score_d not in (None, 0.0):
        parts.append(f"score {score_d:+.4f}")

    narrative = " · ".join(parts) if parts else "no material change since previous snapshot"

    return {
        "is_new":                False,
        "days_recommended":      days_rec,
        "previous_asof":         prev_asof,
        "rank_change":           _delta(rec.get("rank"), prev.get("rank"), 0),
        "score_change":          _delta(rec.get("ensemble_score"), prev.get("ensemble_score")),
        "confidence_change":     _delta(rec.get("calibrated_confidence"), prev.get("calibrated_confidence")),
        "allocation_change_pct": _delta(curr_alloc, prev_alloc, 2),
        "action_change":         f"{prev_action} → {curr_action}" if action_changed else None,
        "lifecycle_change":      f"{prev_lc} → {curr_lc}" if lifecycle_changed else None,
        "narrative":             narrative,
    }


# ── CEO Executive Summary block (CEO cycle 4) ────────────────
def build_ceo_summary(recs: Sequence[Mapping],
                         market: str,
                         macro_regime: str | None = None,
                         portfolio_cash_pct: float | None = None,
                         portfolio_health_score: int | None = None) -> dict:
    """One-glance operator summary · rendered at top of recommendations.json.

    Consumes already-enriched recs (needs investor_action + rotation
    + position_plan). Missing macro/portfolio inputs degrade gracefully.
    """
    if not recs:
        return {
            "engine":              ENGINE_ID,
            "market":              market,
            "market_regime":       macro_regime or "unknown",
            "portfolio_health":    portfolio_health_score,
            "cash_pct":            portfolio_cash_pct,
            "top_opportunity":     None,
            "top_risk":            None,
            "recommended_action":  "no recommendations available today",
            "actionable_count":    0,
        }
    from collections import Counter
    actionable_entries = [r for r in recs
                            if (r.get("investor_action") or {}).get("is_actionable_entry")]
    actionable_exits = [r for r in recs
                          if (r.get("investor_action") or {}).get("if_holding") in ("REDUCE", "EXIT")]
    rotations = [r for r in recs
                   if (r.get("rotation_intelligence") or {}).get("should_rotate")]
    # Top opportunity = highest ensemble_score among actionable entries
    top_opp = None
    if actionable_entries:
        top = max(actionable_entries, key=lambda r: r.get("ensemble_score") or 0.0)
        top_opp = {
            "ticker": top.get("ticker"),
            "action": (top.get("investor_action") or {}).get("entry"),
            "allocation_pct": (top.get("position_plan") or {}).get("suggested_allocation_pct"),
            "expected_alpha_note": (top.get("why") or {}).get("signal_quality"),
        }
    # Top risk = lowest ensemble_score among actionable exits
    top_risk = None
    if actionable_exits:
        worst = min(actionable_exits, key=lambda r: r.get("ensemble_score") or 0.0)
        top_risk = {
            "ticker": worst.get("ticker"),
            "if_holding": (worst.get("investor_action") or {}).get("if_holding"),
            "reason": (worst.get("why") or {}).get("top_risks") or [],
        }
    # Recommended one-line action
    # ASCII-safe strings · terminals + CI logs (Windows cp1252) cannot
    # encode → / · reliably. Emojis stay in Telegram output layer only.
    if rotations:
        best_rot = max(rotations,
                          key=lambda r: (r.get("rotation_intelligence") or {}).get("expected_alpha_delta_pct") or 0)
        ri = best_rot.get("rotation_intelligence") or {}
        recommended = (f"Rotate {best_rot.get('ticker')} -> {ri.get('replacement_ticker')} "
                        f"(expected alpha +{ri.get('expected_alpha_delta_pct')}%)")
    elif actionable_entries:
        recommended = f"Deploy capital: {top_opp['ticker']} {top_opp['action']} / {top_opp['allocation_pct']}%"
    elif actionable_exits:
        recommended = f"Trim/exit: {top_risk['ticker']} -> {top_risk['if_holding']}"
    else:
        recommended = "Hold cash - no actionable signals today"

    entry_dist = Counter((r.get("investor_action") or {}).get("entry", "?") for r in recs)
    return {
        "engine":              ENGINE_ID,
        "market":              market,
        "market_regime":       macro_regime or "unknown",
        "portfolio_health":    portfolio_health_score,
        "cash_pct":            portfolio_cash_pct,
        "top_opportunity":     top_opp,
        "top_risk":            top_risk,
        "recommended_action":  recommended,
        "actionable_count":    len(actionable_entries) + len(actionable_exits),
        "rotations_count":     len(rotations),
        "entry_decision_dist": dict(entry_dist),
    }


# ── Main entry point ─────────────────────────────────────────
def enrich_recommendation(rec: MutableMapping,
                             all_recs: Sequence[Mapping] | None = None,
                             lifecycle_records: Mapping | None = None,
                             dynamic_holding_decisions: Mapping | None = None,
                             previous_ticker_map: Mapping | None = None,
                             asof: str | None = None,
                             history_asof_map: Mapping | None = None) -> MutableMapping:
    """Enrich a single rec dict in-place · returns the same dict.

    Reads: percentile_action (preferred) OR action, ensemble_score,
           calibrated_confidence, bull_case, bear_case, key_risks,
           suggested_holding_period_days, entry_zone.current,
           signal_quality, disagreement_flag, top_features.
    Writes: investor_action, position_plan, why.
    """
    # Prefer the percentile-derived action (institutional pattern), else fall
    # back to the legacy absolute-threshold action.
    action = str(rec.get("percentile_action") or rec.get("action") or "HOLD").upper()
    entry = ENTRY_MAP.get(action, "WAIT")
    if_holding = IF_HOLDING_MAP.get(action, "HOLD")

    is_actionable_entry = entry in ACTIONABLE_ENTRY
    is_actionable_if_holding = if_holding in ACTIONABLE_IF_HOLDING

    # Investor-action block
    rec["investor_action"] = {
        "entry":                    entry,
        "if_holding":               if_holding,
        "user_facing_label":        LABEL_MAP.get(action, LABEL_MAP["HOLD"]),
        "is_actionable_entry":      is_actionable_entry,
        "is_actionable_if_holding": is_actionable_if_holding,
        "source_action":            action,
    }

    # Position plan block · dynamic_holding surface (CEO cycle 3)
    ticker = str(rec.get("ticker") or "")
    fallback_horizon = rec.get("suggested_holding_period_days") or 45
    horizon_days, dh_reason = _dynamic_holding_days(
        ticker, dynamic_holding_decisions, int(fallback_horizon)
    )
    bucket, bucket_desc = _horizon_bucket(horizon_days)
    ez_in = rec.get("entry_zone") or {}
    current_price = ez_in.get("current") if isinstance(ez_in, Mapping) else None
    zone = _entry_zone(current_price, action)

    alloc = float(DEFAULT_ALLOC_PCT.get(action, 0.0))
    alloc = min(alloc, PER_TICKER_CAP_PCT)
    signal_quality = str(rec.get("signal_quality") or "")
    calibrated_conf = float(rec.get("calibrated_confidence") or 0.0)

    # Damp allocation when signal_quality is WEAK regardless of action
    if signal_quality.upper() == "WEAK" and alloc > 0:
        alloc = round(alloc * 0.5, 2)

    position_plan = {
        "suggested_allocation_pct":  round(alloc, 2),
        "risk_level":                _risk_level(signal_quality, calibrated_conf),
        "max_capital_exposure_pct":  PER_TICKER_CAP_PCT,
        "time_horizon_days":         int(horizon_days),
        "time_horizon_bucket":       bucket,
        "time_horizon_desc":         bucket_desc,
        "entry_zone":                zone,
        "sizing_note":               (
            "preview allocation · real position size determined by risk engine "
            "(fractional Kelly · half-Kelly cap · per-sector cap · VIX-adjusted)"
        ),
    }
    if dh_reason:
        position_plan["dynamic_holding_reason"] = dh_reason
    rec["position_plan"] = position_plan

    # Why block
    rec["why"] = {
        "top_reasons": _top_reasons(
            rec.get("bull_case"),
            rec.get("ensemble_score") or 0.0,
            rec.get("top_features"),
        ),
        "top_risks": _top_risks(
            rec.get("bear_case"),
            rec.get("key_risks"),
            bool(rec.get("disagreement_flag")),
        ),
        "signal_quality": signal_quality or "unknown",
    }

    # Rotation intelligence block (CEO cycle 3 · Phase 8 HIGHEST priority)
    rec["rotation_intelligence"] = _rotation_for_rec(rec, all_recs)

    # Lifecycle state block (CEO cycle 3 · Phase 13 + Lifecycle)
    rec["lifecycle_state"] = _lifecycle_for_rec(rec, lifecycle_records)

    # Evolution block (CEO cycle 4 · Performance & Evolution)
    rec["evolution"] = _evolution_for_rec(rec, previous_ticker_map, asof, history_asof_map)

    return rec


def enrich_batch(recs: Sequence[MutableMapping],
                    lifecycle_records: Mapping | None = None,
                    dynamic_holding_decisions: Mapping | None = None,
                    previous_ticker_map: Mapping | None = None,
                    asof: str | None = None,
                    history_asof_map: Mapping | None = None) -> list[MutableMapping]:
    """Enrich a list of recs in-place · returns the same list.

    Context artifacts (lifecycle_records, dynamic_holding_decisions,
    previous_ticker_map for evolution deltas, history_asof_map for
    days_recommended) are optional · when absent the enricher falls back
    gracefully.
    """
    recs_list = list(recs)
    for r in recs_list:
        enrich_recommendation(r,
                                 all_recs=recs_list,
                                 lifecycle_records=lifecycle_records,
                                 dynamic_holding_decisions=dynamic_holding_decisions,
                                 previous_ticker_map=previous_ticker_map,
                                 asof=asof,
                                 history_asof_map=history_asof_map)
    return recs_list


def summarize_batch(recs: Sequence[Mapping]) -> dict:
    """Emit a compact summary of the enriched batch for dashboards."""
    entry_dist: dict[str, int] = {}
    hold_dist: dict[str, int] = {}
    actionable_entries: list[str] = []
    actionable_exits: list[str] = []
    for r in recs:
        ia = r.get("investor_action") or {}
        e = ia.get("entry", "WAIT")
        h = ia.get("if_holding", "HOLD")
        entry_dist[e] = entry_dist.get(e, 0) + 1
        hold_dist[h] = hold_dist.get(h, 0) + 1
        if ia.get("is_actionable_entry"):
            actionable_entries.append(str(r.get("ticker") or "?"))
        if h in ACTIONABLE_IF_HOLDING:
            actionable_exits.append(f"{r.get('ticker','?')}:{h}")
    # Rotation intelligence rollup (CEO cycle 3)
    n_rotate = 0
    rotations: list[dict] = []
    lifecycle_dist: dict[str, int] = {}
    for r in recs:
        ri = r.get("rotation_intelligence") or {}
        if ri.get("should_rotate"):
            n_rotate += 1
            rotations.append({
                "from":                     r.get("ticker"),
                "to":                       ri.get("replacement_ticker"),
                "edge":                     ri.get("edge"),
                "expected_alpha_delta_pct": ri.get("expected_alpha_delta_pct"),
            })
        lc = (r.get("lifecycle_state") or {}).get("current_state", "UNTRACKED")
        lifecycle_dist[lc] = lifecycle_dist.get(lc, 0) + 1
    return {
        "engine":                    ENGINE_ID,
        "schema_fingerprint":        SCHEMA_FINGERPRINT,
        "n_recs":                    len(recs),
        "entry_decision_dist":       entry_dist,
        "if_holding_decision_dist":  hold_dist,
        "actionable_entries":        actionable_entries,
        "actionable_exits":          actionable_exits,
        "n_rotation_suggestions":    n_rotate,
        "rotations":                 rotations,
        "lifecycle_state_dist":      lifecycle_dist,
    }
