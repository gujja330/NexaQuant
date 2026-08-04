"""R006 · Phase 9 · Profit Protection Engine.

Ships 2026-08-04 per operator's ChatGPT proposal Module B review. Extends
the R006 lifecycle state machine with 5 additional exit/action triggers
beyond the classic stop/T1/T2/horizon set that Phase 2 already covers:

    1. RAPID_APPRECIATION  · +Xpct in <M days · lock 50pct, trail rest
    2. RANK_COLLAPSE       · rank drops N places overnight · re-evaluate
    3. BETTER_REPLACEMENT  · another candidate has +Ypct edge · rotation candidate
    4. SECTOR_LEADERSHIP   · sector rotation shifted away · surface for review
    5. RISK_ESCALATION     · vol doubled OR risk score jumped · reduce/tighten

Each trigger emits a `ProfitProtectionSignal` · the caller (portfolio_manager
or command_center) decides whether to log it as an EXIT event, a REBALANCE
event, or a narrative note. Signals are additive to the state machine's
existing decisions · they never override a stop/target/horizon exit.

Design principles:
    · Deterministic thresholds (config-driven · no ML)
    · Reason strings human-readable · replayable
    · Zero coupling to Runner 1 (SEALED)
    · Additive · never mutates prior events
    · Walk-forward compatible · uses only asof-visible state

Config path: configs/profit_protection.json (auto-created with defaults).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

from .portfolio_ledger import current_portfolio_state, rotation_history
from .rank_history import get_prior_rank
from .market_regime_stability import buffer_state as _regime_buffer_state


# ── Default thresholds · overridable via configs/profit_protection.json ──
DEFAULT_CONFIG = {
    "rapid_appreciation": {
        "min_gain_pct":        15.0,     # +15% or more
        "max_days_held":       10,       # in 10 days or less
        "action":              "TRAIL",  # lock 50% · trail remaining
    },
    "rank_collapse": {
        "min_rank_drop":       5,        # rank fell by 5+ places
        "min_prior_rank":      3,        # only when ticker was top-3 yesterday
        "action":              "REVIEW", # surface · don't auto-exit
    },
    "better_replacement": {
        "min_edge_pp":         12.0,     # +12pp expected alpha vs current
        "action":              "ROTATE_CANDIDATE",
    },
    "sector_leadership": {
        "check_days":          5,        # sector out of top-3 for 5 days
        "action":              "REVIEW",
    },
    "risk_escalation": {
        "vol_multiplier":      2.0,      # realized vol doubled vs entry
        "risk_score_jump":     0.20,     # risk_score up by 0.20
        "action":              "REDUCE", # trim + tighten stop
    },
    "market_regime_buffer": {
        "action":              "BUFFER", # suppress rank-collapse-driven action
    },
}


TRIGGER_NAMES = ("RAPID_APPRECIATION", "RANK_COLLAPSE", "BETTER_REPLACEMENT",
                     "SECTOR_LEADERSHIP", "RISK_ESCALATION", "MARKET_REGIME_BUFFER")


@dataclass
class ProfitProtectionSignal:
    ticker: str
    trigger: str                        # one of TRIGGER_NAMES
    action: str                         # TRAIL · REVIEW · ROTATE_CANDIDATE · REDUCE
    reason: str                         # human-readable
    severity: str = "info"              # info · warning · critical
    metadata: dict = field(default_factory=dict)


def load_config(root: Path) -> dict:
    """Load thresholds from configs/profit_protection.json · create if missing."""
    p = root / "configs" / "profit_protection.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {**DEFAULT_CONFIG, **data}   # user config overrides defaults
    except Exception:
        return DEFAULT_CONFIG


def check_rapid_appreciation(pos: Mapping, current_price: float,
                                    asof: str, cfg: dict) -> ProfitProtectionSignal | None:
    """Trigger #1 · position up N% in <M days."""
    entry = pos.get("entry_price") or 0
    opened_on = pos.get("opened_on") or ""
    if not entry or not opened_on or not current_price:
        return None
    gain_pct = (current_price - entry) / entry * 100.0
    if gain_pct < cfg["min_gain_pct"]:
        return None
    try:
        days_held = (date.fromisoformat(asof) - date.fromisoformat(opened_on)).days
    except (ValueError, TypeError):
        return None
    if days_held > cfg["max_days_held"]:
        return None
    return ProfitProtectionSignal(
        ticker=pos.get("ticker", ""),
        trigger="RAPID_APPRECIATION",
        action=cfg["action"],
        reason=f"+{gain_pct:.1f}% in {days_held}d "
                 f"(≥{cfg['min_gain_pct']:.0f}% in ≤{cfg['max_days_held']}d) · "
                 f"lock 50% · trail remaining",
        severity="warning",
        metadata={"gain_pct": round(gain_pct, 2), "days_held": days_held},
    )


def check_rank_collapse(ticker: str, today_rank: int,
                              yesterday_rank: int | None,
                              cfg: dict) -> ProfitProtectionSignal | None:
    """Trigger #2 · rank dropped N+ places overnight."""
    if yesterday_rank is None or today_rank is None:
        return None
    if yesterday_rank > cfg["min_prior_rank"]:
        return None
    drop = today_rank - yesterday_rank
    if drop < cfg["min_rank_drop"]:
        return None
    return ProfitProtectionSignal(
        ticker=ticker, trigger="RANK_COLLAPSE",
        action=cfg["action"],
        reason=f"rank {yesterday_rank}→{today_rank} (dropped {drop} places) · "
                 f"re-evaluate conviction · no auto-exit",
        severity="warning",
        metadata={"prior_rank": yesterday_rank, "today_rank": today_rank, "drop": drop},
    )


def check_better_replacement(pos: Mapping, candidates: Sequence[Mapping],
                                    cfg: dict) -> ProfitProtectionSignal | None:
    """Trigger #3 · another candidate has +Ypp edge over this position.

    candidates: list of today's recs with `ensemble_score` (or equivalent)
    that AREN'T currently held. We compare each vs this position's score
    and flag if any exceeds by cfg.min_edge_pp.
    """
    own_score = pos.get("last_score") or pos.get("entry_score")
    if not own_score or not candidates:
        return None
    best = None
    best_edge = 0.0
    for c in candidates:
        c_score = c.get("ensemble_score") or 0
        edge = c_score - own_score
        if edge > best_edge:
            best_edge = edge
            best = c
    if best is None or best_edge < cfg["min_edge_pp"]:
        return None
    return ProfitProtectionSignal(
        ticker=pos.get("ticker", ""),
        trigger="BETTER_REPLACEMENT",
        action=cfg["action"],
        reason=f"{best.get('ticker', '?')} has +{best_edge:.1f}pp expected "
                 f"alpha vs current · rotation candidate (not auto-executed)",
        severity="info",
        metadata={"replacement": best.get("ticker"), "edge_pp": round(best_edge, 2)},
    )


def check_sector_leadership(pos: Mapping, sector: str,
                                  sector_rank_history: list[int],
                                  cfg: dict) -> ProfitProtectionSignal | None:
    """Trigger #4 · sector fell out of top-3 for N consecutive days."""
    if not sector_rank_history or len(sector_rank_history) < cfg["check_days"]:
        return None
    recent = sector_rank_history[-cfg["check_days"]:]
    if all(r > 3 for r in recent):
        return ProfitProtectionSignal(
            ticker=pos.get("ticker", ""),
            trigger="SECTOR_LEADERSHIP",
            action=cfg["action"],
            reason=f"{sector} sector out of top-3 for {cfg['check_days']}d "
                     f"(ranks {recent}) · leadership shift · surface for review",
            severity="info",
            metadata={"sector": sector, "recent_ranks": recent},
        )
    return None


def check_risk_escalation(pos: Mapping, current_vol: float, entry_vol: float,
                                today_risk: float, entry_risk: float,
                                cfg: dict) -> ProfitProtectionSignal | None:
    """Trigger #5 · vol doubled OR risk score jumped."""
    if not entry_vol or entry_vol <= 0:
        return None
    vol_mult = current_vol / entry_vol
    risk_jump = today_risk - entry_risk
    vol_hit = vol_mult >= cfg["vol_multiplier"]
    risk_hit = risk_jump >= cfg["risk_score_jump"]
    if not vol_hit and not risk_hit:
        return None
    parts = []
    if vol_hit:
        parts.append(f"vol {entry_vol:.3f}→{current_vol:.3f} ({vol_mult:.1f}x)")
    if risk_hit:
        parts.append(f"risk_score +{risk_jump:.2f}")
    return ProfitProtectionSignal(
        ticker=pos.get("ticker", ""),
        trigger="RISK_ESCALATION",
        action=cfg["action"],
        reason=" · ".join(parts) + " · reduce position + tighten stop",
        severity="critical",
        metadata={"vol_mult": round(vol_mult, 2), "risk_jump": round(risk_jump, 3)},
    )


def evaluate_position_pp(root: Path, market: str, runner: str,
                              pos: Mapping, asof: str,
                              current_price: float,
                              today_rank: int | None,
                              yesterday_rank: int | None,
                              candidates: Sequence[Mapping],
                              sector: str | None,
                              sector_rank_history: list[int] | None,
                              current_vol: float | None,
                              entry_vol: float | None,
                              today_risk: float | None,
                              entry_risk: float | None,
                              ) -> list[ProfitProtectionSignal]:
    """Run all 5 triggers on one position · return all fired signals.

    Every input can be None if unavailable · corresponding trigger silently
    skips. This lets the engine ship early with sparse inputs and get
    smarter as feature store fills.
    """
    cfg = load_config(root)
    signals: list[ProfitProtectionSignal] = []

    s1 = check_rapid_appreciation(pos, current_price, asof, cfg["rapid_appreciation"])
    if s1: signals.append(s1)

    if today_rank is not None:
        s2 = check_rank_collapse(pos.get("ticker", ""), today_rank,
                                       yesterday_rank, cfg["rank_collapse"])
        if s2: signals.append(s2)

    if candidates:
        s3 = check_better_replacement(pos, candidates, cfg["better_replacement"])
        if s3: signals.append(s3)

    if sector and sector_rank_history:
        s4 = check_sector_leadership(pos, sector, sector_rank_history,
                                            cfg["sector_leadership"])
        if s4: signals.append(s4)

    if current_vol is not None and entry_vol is not None \
       and today_risk is not None and entry_risk is not None:
        s5 = check_risk_escalation(pos, current_vol, entry_vol,
                                          today_risk, entry_risk,
                                          cfg["risk_escalation"])
        if s5: signals.append(s5)

    return signals


def check_market_regime_buffer(pos: Mapping, buffer_info: dict,
                                      cfg: dict) -> ProfitProtectionSignal | None:
    """Trigger #6 · MARKET_REGIME_BUFFER · dampen actions when regime flipped.

    Fires when regime buffer is active AND this position was opened BEFORE
    the flip · signaling that today's rank / signal changes may be macro-
    driven noise · not a real change in this ticker's thesis. Callers should
    demote RANK_COLLAPSE severity from `warning` to `info` and suppress
    rotation candidates when this trigger is present.
    """
    if not buffer_info or not buffer_info.get("active"):
        return None
    opened_on = pos.get("opened_on") or ""
    since_asof = buffer_info.get("since_asof") or ""
    if opened_on and since_asof and opened_on >= since_asof:
        return None
    return ProfitProtectionSignal(
        ticker=pos.get("ticker", ""),
        trigger="MARKET_REGIME_BUFFER",
        action=cfg["action"],
        reason=f"macro regime flipped · {buffer_info.get('reason', '')} · "
                 f"position opened pre-flip ({opened_on}) · "
                 f"preserve entry-time conviction · "
                 f"{buffer_info.get('remaining_days', 0)}d buffer left",
        severity="info",
        metadata={"buffer_reason":   buffer_info.get("reason"),
                     "buffer_since":    buffer_info.get("since_asof"),
                     "remaining_days":  buffer_info.get("remaining_days")},
    )


def evaluate_all_active(root: Path, market: str, runner: str, asof: str,
                              recs: Sequence[Mapping]) -> list[ProfitProtectionSignal]:
    """Run every trigger against every active position · returns fired signals.

    Reads state from portfolio_ledger · pulls rank/price from today's recs ·
    pulls yesterday's rank from most-recent HOLD/OPEN/ROTATE_IN ledger event.
    Sector / vol / risk inputs fall back to None when feature-store data is
    sparse (early-life gracefully skips those triggers).
    """
    cfg = load_config(root)
    all_signals: list[ProfitProtectionSignal] = []
    state = current_portfolio_state(root, market, runner)
    active = {t: p for t, p in state.items() if p.get("is_active")}

    # Regime buffer state (single call · reused per ticker)
    buffer_info = _regime_buffer_state(root, market, asof)

    today_by_ticker = {r.get("ticker", ""): r for r in recs}
    today_ranks = {r.get("ticker", ""): r.get("rank") for r in recs}
    candidates = [r for r in recs if (r.get("ticker") or "") not in active]

    for ticker, pos in active.items():
        rec = today_by_ticker.get(ticker) or {}
        ez = ((rec.get("position_plan") or {}).get("entry_zone") or {})
        current_price = ez.get("current_price") or pos.get("last_seen_price") or 0
        today_rank = today_ranks.get(ticker)
        # Prefer rank_history (persistent) over pos.last_rank (may be stale)
        yesterday_rank, _ = get_prior_rank(root, market, runner, ticker, asof)
        if yesterday_rank is None:
            yesterday_rank = pos.get("last_rank")
        sector = rec.get("sector")

        signals = evaluate_position_pp(
            root, market, runner,
            {**pos, "ticker": ticker}, asof,
            current_price=float(current_price or 0),
            today_rank=today_rank,
            yesterday_rank=yesterday_rank,
            candidates=candidates,
            sector=sector,
            sector_rank_history=None,      # sparse today · will fill in later
            current_vol=None, entry_vol=None,
            today_risk=None, entry_risk=None,
        )

        # Trigger #6 · MARKET_REGIME_BUFFER (checked per-position because
        # opened_on comparison matters)
        s6 = check_market_regime_buffer(
            {**pos, "ticker": ticker}, buffer_info, cfg["market_regime_buffer"])
        if s6:
            signals.append(s6)
            # When buffer active · demote any RANK_COLLAPSE from warning→info
            # AND suppress BETTER_REPLACEMENT rotation candidates (macro noise)
            signals = [
                (ProfitProtectionSignal(
                    ticker=s.ticker, trigger=s.trigger, action=s.action,
                    reason=s.reason + " · buffered by regime flip",
                    severity="info" if s.trigger == "RANK_COLLAPSE" else s.severity,
                    metadata=s.metadata,
                ) if s.trigger == "RANK_COLLAPSE"
                    else s)
                for s in signals if s.trigger != "BETTER_REPLACEMENT"
            ]
            # Re-add s6 since the filter above may have kept it
            if not any(x.trigger == "MARKET_REGIME_BUFFER" for x in signals):
                signals.append(s6)

        all_signals.extend(signals)

    return all_signals


def emit_signals(root: Path, market: str, runner: str, asof: str,
                    signals: Sequence[ProfitProtectionSignal]) -> Path:
    """Persist signals to reports/research/profit_protection_{market}.json."""
    from datetime import datetime, timezone
    p = root / "reports" / "research" / f"profit_protection_{market}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":         "aegis.portfolio.profit_protection.r006.v1",
        "generated_utc":  datetime.now(timezone.utc).isoformat(),
        "market":         market, "runner": runner, "asof":  asof,
        "n_signals":      len(signals),
        "signals":        [
            {"ticker": s.ticker, "trigger": s.trigger, "action": s.action,
             "reason": s.reason, "severity": s.severity, **s.metadata}
            for s in signals
        ],
    }
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
