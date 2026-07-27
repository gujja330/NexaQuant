"""Capital Rotation Engine · Constitution-compliant implementation.

Deterministic · walk-forward safe · schema-fingerprinted · replayable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from enum import Enum
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.capital_rotation.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.capital_rotation.v1"

MACRO_GATE_MULTIPLIERS = {
    "risk_on":           1.0,
    "neutral":           0.9,
    "risk_off":          0.5,
    "stress":            0.3,
    "recession_warning": 0.5,
    "unknown":           0.85,
}

EXIT_THRESHOLD  = -0.20
TRIM_THRESHOLD  = +0.10
ROTATE_EDGE     = +0.25

_KEEP_WEIGHTS = {"upside": 0.35, "conf_delta": 0.20, "rank_delta": 0.15,
                  "sector":  0.15, "pnl":        0.15}
_CAND_WEIGHTS = {"upside": 0.40, "conf": 0.25, "rank": 0.20, "sector": 0.15}


class RotationAction(str, Enum):
    KEEP   = "KEEP"
    ADD    = "ADD"
    TRIM   = "TRIM"
    EXIT   = "EXIT"
    ROTATE = "ROTATE"


@dataclass(frozen=True)
class Position:
    ticker: str
    entry_score: float           # score at entry-time (0-100 or -1..+1 · caller-normalized)
    current_score: float
    entry_confidence: float      # [0, 1]
    current_confidence: float    # [0, 1]
    entry_rank: int
    current_rank: int
    entry_price: float
    current_price: float
    sector: str
    upside_remaining_pct: float  # from target / mean-reversion / analyst
    pnl_pct: float               # (current_price / entry_price - 1) * 100


@dataclass(frozen=True)
class Candidate:
    ticker: str
    score: float                 # normalized to [-1, +1]
    confidence: float
    rank: int
    sector: str
    upside_pct: float


@dataclass(frozen=True)
class RotationDecision:
    ticker: str
    action: RotationAction
    keep_score: float | None
    candidate_ticker: str | None
    candidate_score: float | None
    edge: float | None
    trim_fraction: float | None
    reason: str


@dataclass
class RotationPlan:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    market: str = ""
    asof: str = ""
    run_utc: str = ""
    macro_regime: str = "unknown"
    macro_gate: float = 1.0
    n_positions: int = 0
    n_candidates: int = 0
    n_exit: int = 0
    n_trim: int = 0
    n_keep: int = 0
    n_add: int = 0
    n_rotate: int = 0
    decisions: list[dict] = field(default_factory=list)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _norm_delta(current: float, entry: float) -> float:
    """Normalize a delta to a [-1, +1] contribution."""
    if entry <= 0:
        return 0.0
    return max(-1.0, min(1.0, (current - entry) / max(abs(entry), 1e-9)))


def macro_gate_multiplier(regime: str) -> float:
    return MACRO_GATE_MULTIPLIERS.get(regime, MACRO_GATE_MULTIPLIERS["unknown"])


def keep_score(p: Position, sector_strength: float = 0.0) -> float:
    """Composite keep-score in [-1, +1].
    Higher = stronger reason to keep the position."""
    upside     = _clip01(p.upside_remaining_pct / 20.0)      # 20% upside -> 1.0
    conf_delta = _norm_delta(p.current_confidence, p.entry_confidence)
    rank_delta = _norm_delta(float(p.entry_rank), float(p.current_rank))  # improved rank (smaller number) -> positive
    sector     = max(-1.0, min(1.0, sector_strength / 20.0))
    pnl        = max(-1.0, min(1.0, p.pnl_pct / 20.0))
    score = (_KEEP_WEIGHTS["upside"]     * upside
              + _KEEP_WEIGHTS["conf_delta"] * conf_delta
              + _KEEP_WEIGHTS["rank_delta"] * rank_delta
              + _KEEP_WEIGHTS["sector"]     * sector
              + _KEEP_WEIGHTS["pnl"]        * pnl)
    return round(max(-1.0, min(1.0, score)), 6)


def candidate_score(c: Candidate, sector_strength: float, macro_gate: float) -> float:
    """Composite candidate score in [-1, +1] after macro gating."""
    upside = _clip01(c.upside_pct / 20.0)
    conf   = _clip01(c.confidence)
    rank   = _clip01(1.0 - min(1.0, (c.rank - 1) / 50.0))  # top-50 → [1..0]
    sector = max(-1.0, min(1.0, sector_strength / 20.0))
    raw    = (_CAND_WEIGHTS["upside"] * upside
              + _CAND_WEIGHTS["conf"]   * conf
              + _CAND_WEIGHTS["rank"]   * rank
              + _CAND_WEIGHTS["sector"] * sector)
    return round(max(-1.0, min(1.0, raw * macro_gate)), 6)


def decide_action(keep: float, best_cand_score: float | None) -> tuple[RotationAction, float | None, float | None]:
    """Return (action, edge, trim_fraction)."""
    if keep < EXIT_THRESHOLD:
        return RotationAction.EXIT, None, 1.0
    if keep < TRIM_THRESHOLD:
        return RotationAction.TRIM, None, 0.5
    if best_cand_score is not None:
        edge = best_cand_score - keep
        if edge > ROTATE_EDGE:
            return RotationAction.ROTATE, round(edge, 6), 1.0
    return RotationAction.KEEP, None, None


class CapitalRotationEngine:
    """Deterministic Capital Rotation Engine."""

    def __init__(self, market: str) -> None:
        if not market:
            raise ValueError("market required")
        self.market = market

    def run(self,
             positions: Sequence[Position],
             candidates: Sequence[Candidate],
             sector_strengths: Mapping[str, float],
             macro_regime: str,
             asof: date | str,
             run_utc: str | None = None) -> RotationPlan:
        """Compute rotation plan · deterministic given identical inputs."""
        gate = macro_gate_multiplier(macro_regime)
        asof_str = asof.isoformat() if isinstance(asof, date) else str(asof)
        plan = RotationPlan(
            market=self.market,
            asof=asof_str,
            run_utc=run_utc or datetime.now(timezone.utc).isoformat(),
            macro_regime=macro_regime,
            macro_gate=gate,
            n_positions=len(positions),
            n_candidates=len(candidates),
        )
        # Score candidates once
        scored_cands = sorted(
            [(c, candidate_score(c, sector_strengths.get(c.sector, 0.0), gate)) for c in candidates],
            key=lambda kv: -kv[1],
        )
        cand_tickers_held = {p.ticker for p in positions}
        # Best candidate excluding tickers already held
        best_cand = next(((c, s) for c, s in scored_cands if c.ticker not in cand_tickers_held), None)

        for p in positions:
            k = keep_score(p, sector_strengths.get(p.sector, 0.0))
            best_score = best_cand[1] if best_cand else None
            action, edge, trim = decide_action(k, best_score)
            reason = _build_reason(p, k, action, best_cand, edge)
            plan.decisions.append(asdict(RotationDecision(
                ticker=p.ticker,
                action=action,
                keep_score=k,
                candidate_ticker=best_cand[0].ticker if (action == RotationAction.ROTATE and best_cand) else None,
                candidate_score=best_score if action == RotationAction.ROTATE else None,
                edge=edge,
                trim_fraction=trim,
                reason=reason,
            )))
            if action == RotationAction.EXIT:   plan.n_exit += 1
            elif action == RotationAction.TRIM:  plan.n_trim += 1
            elif action == RotationAction.ROTATE: plan.n_rotate += 1
            else: plan.n_keep += 1

        return plan


def _build_reason(p: Position, k: float, action: RotationAction,
                   best_cand: tuple[Candidate, float] | None, edge: float | None) -> str:
    if action == RotationAction.EXIT:
        return (f"keep_score {k} below EXIT threshold {EXIT_THRESHOLD} "
                f"(upside_remaining {p.upside_remaining_pct:.2f}%, "
                f"pnl {p.pnl_pct:.2f}%, conf {p.entry_confidence:.2f}→{p.current_confidence:.2f})")
    if action == RotationAction.TRIM:
        return (f"keep_score {k} below TRIM threshold {TRIM_THRESHOLD} — reduce 50%")
    if action == RotationAction.ROTATE and best_cand is not None:
        c, s = best_cand
        return (f"rotate to {c.ticker} · candidate_score {s} vs keep_score {k} "
                f"(edge {edge}, exceeds ROTATE {ROTATE_EDGE})")
    return f"keep · keep_score {k} above thresholds"


def compute_rotation_plan(market: str,
                            positions: Sequence[Position],
                            candidates: Sequence[Candidate],
                            sector_strengths: Mapping[str, float],
                            macro_regime: str,
                            asof: date | str,
                            run_utc: str | None = None) -> RotationPlan:
    """Convenience one-shot API."""
    return CapitalRotationEngine(market).run(
        positions, candidates, sector_strengths, macro_regime, asof, run_utc)
