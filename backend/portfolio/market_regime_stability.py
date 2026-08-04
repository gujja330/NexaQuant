"""R006 · Phase 9b · Market Regime Stability Engine.

Operator 2026-08-04: *"if other global markets are red, so india is red this
type of behaviours should distract recommendations. what we purchased when
market was green and all of the sudden market is red due to xyz impacts
shouldn't disturb rank or rechange stocks. we should create an engine for
finding such things."*

This engine implements a **buffered rank-stability policy**:

    1. Track macro regime day-over-day (bull · neutral · bear · unknown)
    2. Classify today's shift vs yesterday:
         · STABLE       (no change in classification)
         · SOFT_SHIFT   (adjacent flip · bull↔neutral · neutral↔bear)
         · HARD_FLIP    (opposite corners · bull↔bear · high-vol event)
    3. When HARD_FLIP is detected · engine emits a BUFFER decision:
         · Dampen rank-change alerts for N days (default 3)
         · Suppress rank-collapse-triggered rotations during buffer
         · Preserve entry-time conviction for positions opened pre-flip

Regime source: `reports/macro_regime.json` (Sprint 6.5 · Macro Intel) if
available · falls back to `neutral` when file absent. History persisted at
`reports/research/regime_history.jsonl` — one append per pipeline run.

Zero coupling to Runner 1 (SEALED). Consumed by profit_protection.py
trigger #6 (MARKET_REGIME_BUFFER) and by the XLSX renderer via Alert column.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path


REGIME_LADDER = {"bull": 2, "neutral": 1, "bear": 0, "unknown": 1}


DEFAULT_CONFIG = {
    "buffer_days_after_hard_flip": 3,
    "buffer_days_after_soft_shift": 1,
    "hard_flip_min_ladder_delta": 2,   # |ladder(today) - ladder(yesterday)|
}


@dataclass
class RegimeSnapshot:
    ts_utc: str
    asof: str
    market: str
    regime: str
    ladder_score: int
    source: str        # "macro_regime.json" · "fallback:neutral" · "override"


def _hist_path(root: Path) -> Path:
    p = root / "reports" / "research" / "regime_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_current_regime(root: Path, market: str) -> tuple[str, str]:
    """Return (regime, source)."""
    if market == "usa":
        p = root / "usa" / "reports" / "macro_regime.json"
    else:
        p = root / "reports" / "macro_regime.json"
    if not p.exists():
        return "neutral", "fallback:no-macro-regime-file"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        r = str(d.get("primary_regime") or d.get("regime") or "neutral").lower()
        if r not in REGIME_LADDER:
            r = "unknown"
        return r, "macro_regime.json"
    except Exception:
        return "neutral", "fallback:parse-error"


def stamp_today(root: Path, asof: str, market: str) -> RegimeSnapshot:
    """Append today's regime to history · idempotent per (asof, market)."""
    regime, source = _read_current_regime(root, market)
    snap = RegimeSnapshot(
        ts_utc=datetime.now(timezone.utc).isoformat(),
        asof=asof, market=market, regime=regime,
        ladder_score=REGIME_LADDER.get(regime, 1),
        source=source,
    )
    hist = load_history(root, market)
    if any(h.get("asof") == asof for h in hist):
        return snap
    with _hist_path(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(snap), default=str, ensure_ascii=False) + "\n")
    return snap


def load_history(root: Path, market: str) -> list[dict]:
    p = _hist_path(root)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("market") != market: continue
        rows.append(d)
    rows.sort(key=lambda r: r.get("asof") or "")
    return rows


def classify_shift(today_regime: str, yesterday_regime: str | None,
                       cfg: dict = DEFAULT_CONFIG) -> str:
    """Return one of STABLE · SOFT_SHIFT · HARD_FLIP."""
    if yesterday_regime is None or yesterday_regime == today_regime:
        return "STABLE"
    delta = abs(REGIME_LADDER.get(today_regime, 1) -
                    REGIME_LADDER.get(yesterday_regime, 1))
    if delta >= cfg["hard_flip_min_ladder_delta"]:
        return "HARD_FLIP"
    return "SOFT_SHIFT"


def buffer_state(root: Path, market: str, asof: str,
                    cfg: dict = DEFAULT_CONFIG) -> dict:
    """Return current buffer state:
        {active: bool, remaining_days: int, reason: str, since_asof: str|None}"""
    hist = load_history(root, market)
    if len(hist) < 2:
        return {"active": False, "remaining_days": 0, "reason": "insufficient history",
                    "since_asof": None}
    today = next((h for h in hist if h["asof"] == asof), hist[-1])
    prior = None
    for h in reversed(hist):
        if h["asof"] < today["asof"]:
            prior = h
            break
    if prior is None:
        return {"active": False, "remaining_days": 0, "reason": "no prior regime",
                    "since_asof": None}
    shift = classify_shift(today["regime"], prior["regime"], cfg)
    if shift == "STABLE":
        return {"active": False, "remaining_days": 0,
                    "reason": f"stable · {today['regime']} · no shift",
                    "since_asof": None}
    days_since = (date.fromisoformat(today["asof"]) -
                       date.fromisoformat(prior["asof"])).days
    if shift == "HARD_FLIP":
        remaining = cfg["buffer_days_after_hard_flip"] - days_since
        return {"active": remaining > 0, "remaining_days": max(0, remaining),
                    "reason": f"HARD_FLIP {prior['regime']}→{today['regime']} "
                                f"{days_since}d ago · buffer {cfg['buffer_days_after_hard_flip']}d",
                    "since_asof": prior["asof"]}
    remaining = cfg["buffer_days_after_soft_shift"] - days_since
    return {"active": remaining > 0, "remaining_days": max(0, remaining),
                "reason": f"SOFT_SHIFT {prior['regime']}→{today['regime']} "
                            f"{days_since}d ago · buffer {cfg['buffer_days_after_soft_shift']}d",
                "since_asof": prior["asof"]}


def load_config(root: Path) -> dict:
    p = root / "configs" / "market_regime_stability.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG
    try:
        return {**DEFAULT_CONFIG, **json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return DEFAULT_CONFIG
