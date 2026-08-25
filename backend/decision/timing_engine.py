# backend/decision/timing_engine.py
"""AEGIS · Sprint M.1 · Timing Engine (M10).

CEO directive 2026-08-25: "integrate short-term momentum as a Timing/
Opportunity layer, not as another raw score · Investability = WHAT ·
Timing = WHEN".

Architecture:

    Investability Engine  (WHAT stock is good)
              +
    Short-Term Momentum   (research/data provider)
              +
    Entry Quality         (MA distance · RSI · volume · breakout)
              +
    Sector / Market Regime
              ↓
    ═══════════════════════
       TIMING ENGINE
    ═══════════════════════
              ↓
    Decision Matrix:
      HIGH Investability + CONFIRMED Momentum + GOOD Entry → BUY
      HIGH Investability + DEVELOPING            → WATCH
      HIGH Investability + DETERIORATING          → HOLD/PROTECT
      LOW  Investability + strong momentum       → CHASE_RISK
      QUALITY DIP + oversold + improving mom     → REBOUND_WATCH
      QUICK_RISE + extreme RSI + poor volume    → CHASE_RISK

Momentum states operator-facing:
      MOMENTUM_CONFIRMED
      MOMENTUM_DEVELOPING
      MOMENTUM_DETERIORATING
      EXTENDED / CHASE_RISK
      NO_SIGNAL

R1 vs R2 usage:
  R1 · momentum is CONFIRMATION overlay only · NEVER trigger exit
       on 1D move alone · thesis + quality + medium-term-trend drive
  R2 · momentum can materially influence TIMING · react to 1D/3D/5D
       shifts · still bounded by risk + investability

Constitutional invariants:
  · LOCK 1 Excel format · READ ONLY
  · LOCK 2 Lifecycle · unchanged
  · Never mutates R1/R2 automatically
  · Every promotion needs Research Ticket → walk-forward → CEO approval

Recommendation output per candidate:
  NO_EVIDENCE       · insufficient data
  RESEARCH_CANDIDATE · signal detected · needs walk-forward
  PRODUCTION_CANDIDATE · signal validated · CEO promotion decision
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.timing_engine.v1.20260825"


# Operator-facing momentum states (derived from short_term_momentum categories)
MOMENTUM_CONFIRMED     = "MOMENTUM_CONFIRMED"
MOMENTUM_DEVELOPING    = "MOMENTUM_DEVELOPING"
MOMENTUM_DETERIORATING = "MOMENTUM_DETERIORATING"
CHASE_RISK             = "CHASE_RISK"
NO_SIGNAL              = "NO_SIGNAL"

# Decision Matrix outcomes
DECISION_BUY           = "BUY"
DECISION_WATCH         = "WATCH"
DECISION_HOLD          = "HOLD"
DECISION_PROTECT       = "PROTECT"
DECISION_REBOUND_WATCH = "REBOUND_WATCH"
DECISION_CHASE_RISK    = "CHASE_RISK"
DECISION_SKIP          = "SKIP"
DECISION_NO_ACTION     = "NO_ACTION"


@dataclass
class TimingScore:
    ticker: str
    market: str
    runner: str                     # R1 or R2 (or empty for research)
    investability_score: Optional[float] = None
    investability_band: str = "UNKNOWN"        # QUALITY/OK/MARGINAL/AVOID
    momentum_category: str = "IGNORE"          # from short_term_momentum
    momentum_state: str = NO_SIGNAL            # operator-facing
    entry_quality: str = "UNKNOWN"             # GOOD / EXTENDED / POOR
    sector_regime: str = "UNKNOWN"             # LEADER / NEUTRAL / LAGGARD
    market_regime: str = "UNKNOWN"             # BULL / BEAR / NEUTRAL
    volume_confirmed: bool = False
    rsi_14: Optional[float] = None
    return_1d_pct: Optional[float] = None
    return_5d_pct: Optional[float] = None
    return_20d_pct: Optional[float] = None
    # Output
    decision: str = DECISION_NO_ACTION
    reason: str = ""
    signals_fired: list = field(default_factory=list)
    recommendation_level: str = "NO_EVIDENCE"  # NO_EVIDENCE/RESEARCH_CANDIDATE/PRODUCTION_CANDIDATE


@dataclass
class TimingReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_evaluated: int = 0
    n_buy: int = 0
    n_watch: int = 0
    n_hold: int = 0
    n_rebound_watch: int = 0
    n_chase_risk: int = 0
    n_skip: int = 0
    scores: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Momentum category → operator-facing state
# ─────────────────────────────────────────────────────────────────
def _momentum_state(category: str, rsi: Optional[float],
                    volume_confirmed: bool,
                    r5: Optional[float], r20: Optional[float]) -> str:
    if category == "IGNORE":
        return NO_SIGNAL
    if category in ("QUICK_RISE", "SUSTAINED_UP"):
        # Extended · RSI overbought AND volume weak · CHASE_RISK
        if rsi is not None and rsi >= 75 and not volume_confirmed:
            return CHASE_RISK
        # Confirmed · volume + 20d agree + not overbought
        if (volume_confirmed and rsi is not None and rsi < 70
            and r20 is not None and r20 > 0):
            return MOMENTUM_CONFIRMED
        # Developing · signal exists but confirmation partial
        return MOMENTUM_DEVELOPING
    if category in ("QUICK_FALL", "SUSTAINED_DOWN"):
        if rsi is not None and rsi < 30:
            # Oversold · potential DEVELOPING for rebound
            return MOMENTUM_DEVELOPING
        return MOMENTUM_DETERIORATING
    if category == "REVERSAL_UP":
        return MOMENTUM_DEVELOPING
    if category == "REVERSAL_DOWN":
        return MOMENTUM_DETERIORATING
    return NO_SIGNAL


# ─────────────────────────────────────────────────────────────────
# Entry quality assessment
# ─────────────────────────────────────────────────────────────────
def _entry_quality(rsi: Optional[float], r5: Optional[float],
                   r20: Optional[float]) -> str:
    if rsi is None: return "UNKNOWN"
    # EXTENDED · RSI > 75 OR 5d already up big
    if rsi > 75 or (r5 is not None and r5 > 10):
        return "EXTENDED"
    # POOR · RSI < 25 OR 20d down big (falling knife)
    if rsi < 25 or (r20 is not None and r20 < -15):
        return "POOR"
    # GOOD · normal RSI · no extremes
    return "GOOD"


# ─────────────────────────────────────────────────────────────────
# Decision Matrix · CEO's own table verbatim
# ─────────────────────────────────────────────────────────────────
def decide(*, investability_band: str, momentum_state: str,
           entry_quality: str, sector_regime: str,
           market_regime: str, runner: str = "") -> tuple:
    """Returns (decision, reason, signals_list, recommendation_level).

    CEO's decision matrix:
      HIGH Invest + CONFIRMED + GOOD  → BUY
      HIGH Invest + DEVELOPING        → WATCH
      HIGH Invest + DETERIORATING     → HOLD/PROTECT (position dependent)
      LOW  Invest + strong momentum   → CHASE_RISK/SKIP
      QUALITY DIP + oversold + REBOUND setup → REBOUND_WATCH
    """
    signals = []
    q_high = investability_band in ("QUALITY", "OK")
    q_low  = investability_band in ("MARGINAL", "AVOID")
    q_unknown = investability_band == "UNKNOWN"
    if q_high: signals.append(f"quality={investability_band}")
    if q_low:  signals.append(f"quality={investability_band}·low")
    if momentum_state != NO_SIGNAL:
        signals.append(f"momentum={momentum_state}")
    if entry_quality != "UNKNOWN":
        signals.append(f"entry={entry_quality}")
    if sector_regime != "UNKNOWN":
        signals.append(f"sector={sector_regime}")

    # PRIORITY 1 · Quality dip rebound setup
    if q_high and momentum_state == MOMENTUM_DEVELOPING and entry_quality == "POOR":
        # High quality + developing + POOR (oversold) entry = REBOUND
        return (DECISION_REBOUND_WATCH,
                "quality name in oversold zone with developing momentum",
                signals, "RESEARCH_CANDIDATE")

    # PRIORITY 2 · Buy setup (CEO's happy path)
    if q_high and momentum_state == MOMENTUM_CONFIRMED and entry_quality == "GOOD":
        _rec = "PRODUCTION_CANDIDATE" if sector_regime != "LAGGARD" else "RESEARCH_CANDIDATE"
        return (DECISION_BUY,
                "quality + confirmed momentum + good entry" +
                (" · sector supportive" if sector_regime == "LEADER" else ""),
                signals, _rec)

    # PRIORITY 3 · Extended · wait for pullback
    if q_high and momentum_state == MOMENTUM_CONFIRMED and entry_quality == "EXTENDED":
        return (DECISION_WATCH,
                "quality + confirmed momentum but entry extended · wait",
                signals, "RESEARCH_CANDIDATE")

    # PRIORITY 4 · Developing · watch for confirmation
    if q_high and momentum_state == MOMENTUM_DEVELOPING:
        return (DECISION_WATCH,
                "quality name · momentum developing · watch for confirmation",
                signals, "RESEARCH_CANDIDATE")

    # PRIORITY 5 · Deteriorating on quality name · R1 hold · R2 protect
    if q_high and momentum_state == MOMENTUM_DETERIORATING:
        _d = DECISION_HOLD if runner.upper() == "R1" else DECISION_PROTECT
        return (_d, "quality name · momentum deteriorating · defensive action",
                signals, "RESEARCH_CANDIDATE")

    # PRIORITY 6 · Chase risk · low quality + strong move
    if q_low and momentum_state in (MOMENTUM_CONFIRMED, MOMENTUM_DEVELOPING):
        return (DECISION_CHASE_RISK,
                "low quality + strong momentum · pump/chase risk",
                signals, "NO_EVIDENCE")

    # PRIORITY 7 · Extreme extension
    if momentum_state == CHASE_RISK:
        return (DECISION_CHASE_RISK,
                "extreme move + weak volume · likely pump/late",
                signals, "NO_EVIDENCE")

    # PRIORITY 8 · Low quality · falling · avoid
    if q_low and momentum_state == MOMENTUM_DETERIORATING:
        return (DECISION_SKIP,
                "low quality + falling · structural failure",
                signals, "NO_EVIDENCE")

    # Default · no signal · no action
    return (DECISION_NO_ACTION,
            "no clear signal · insufficient conviction",
            signals, "NO_EVIDENCE")


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute per market · consumes short_term_momentum output
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str) -> TimingReport:
    """Read short_term_momentum JSON · convert to Timing Scores.
    Constitutional · READ ONLY · never writes to Registry or R1/R2."""
    rep = TimingReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    # Load market regime
    market_regime = "UNKNOWN"
    _mr_p = root / "reports" / "context" / f"macro_regime_{market.lower()}.json"
    if _mr_p.exists():
        try:
            _mr = json.loads(_mr_p.read_text(encoding="utf-8"))
            _label = str(_mr.get("regime") or _mr.get("label") or "").upper()
            if "BULL" in _label: market_regime = "BULL"
            elif "BEAR" in _label: market_regime = "BEAR"
            else: market_regime = "NEUTRAL"
        except Exception:
            pass

    # Load short_term_momentum output
    _sm_p = (root / "reports" / "research"
             / f"short_term_momentum_{market.lower()}.json")
    if not _sm_p.exists():
        return rep
    try:
        _sm = json.loads(_sm_p.read_text(encoding="utf-8"))
    except Exception:
        return rep

    for c in _sm.get("candidates", []):
        state = _momentum_state(
            category=c.get("category", "IGNORE"),
            rsi=c.get("rsi_14"),
            volume_confirmed=bool(c.get("volume_confirmed")),
            r5=c.get("return_5d_pct"), r20=c.get("return_20d_pct"),
        )
        entry_q = _entry_quality(
            rsi=c.get("rsi_14"),
            r5=c.get("return_5d_pct"), r20=c.get("return_20d_pct"),
        )
        _band = str(c.get("quality_band", "UNKNOWN")).upper()
        decision, reason, signals, rec_level = decide(
            investability_band=_band,
            momentum_state=state,
            entry_quality=entry_q,
            sector_regime=str(c.get("sector_status", "UNKNOWN")),
            market_regime=market_regime,
        )
        ts = TimingScore(
            ticker=c.get("ticker",""), market=market.lower(),
            runner="",   # research view · not runner-specific
            investability_band=_band,
            momentum_category=c.get("category",""),
            momentum_state=state,
            entry_quality=entry_q,
            sector_regime=str(c.get("sector_status", "UNKNOWN")),
            market_regime=market_regime,
            volume_confirmed=bool(c.get("volume_confirmed")),
            rsi_14=c.get("rsi_14"),
            return_1d_pct=c.get("return_1d_pct"),
            return_5d_pct=c.get("return_5d_pct"),
            return_20d_pct=c.get("return_20d_pct"),
            decision=decision, reason=reason,
            signals_fired=signals,
            recommendation_level=rec_level,
        )
        rep.scores.append(asdict(ts))
        # Tally
        _tally_map = {
            DECISION_BUY: "n_buy", DECISION_WATCH: "n_watch",
            DECISION_HOLD: "n_hold", DECISION_PROTECT: "n_hold",
            DECISION_REBOUND_WATCH: "n_rebound_watch",
            DECISION_CHASE_RISK: "n_chase_risk",
            DECISION_SKIP: "n_skip",
        }
        _attr = _tally_map.get(decision)
        if _attr: setattr(rep, _attr, getattr(rep, _attr) + 1)
    rep.n_evaluated = len(rep.scores)
    # Sort · BUY first · then REBOUND_WATCH · then WATCH · rest last
    _priority = {DECISION_BUY: 0, DECISION_REBOUND_WATCH: 1,
                 DECISION_WATCH: 2, DECISION_HOLD: 3, DECISION_PROTECT: 3,
                 DECISION_CHASE_RISK: 4, DECISION_SKIP: 5,
                 DECISION_NO_ACTION: 6}
    rep.scores.sort(key=lambda s: _priority.get(s["decision"], 9))
    return rep


def emit(root: Path, rep: TimingReport) -> Path:
    p = (root / "reports" / "context"
         / f"timing_engine_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: TimingReport) -> str:
    return (f"timing_engine · {rep.n_evaluated} evaluated · "
            f"BUY {rep.n_buy} · WATCH {rep.n_watch} · "
            f"REBOUND {rep.n_rebound_watch} · HOLD {rep.n_hold} · "
            f"CHASE_RISK {rep.n_chase_risk} · SKIP {rep.n_skip}")
