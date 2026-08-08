"""Macro sub-engine · 5% weight of Investability Score.

Wave 1.5: consumes existing reports/macro_regime.json +
central_bank_state.json + currency_intelligence.json + bond_intelligence.json.

Signals:
    Regime state           · bull/neutral/bear · bull favors risk assets
    Bond yield direction   · falling supports valuations · rising pressures
    Currency stability     · USD/INR calm favors quality names
    Central bank stance    · dovish supports risk · hawkish tightens
    Vol regime             · low VIX allows risk-on · high demands caution

Ticker-independent: this is a MARKET-WIDE score · same for all tickers on
same day. Represents "how favorable is the macro backdrop for THIS stock's
asset class right now?"
"""
from __future__ import annotations

import json
from pathlib import Path


def _load(root: Path, name: str) -> dict:
    p = root / "reports" / f"{name}.json"
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def score(ticker: str, market: str, root: Path) -> tuple[float, dict]:
    """Ticker parameter unused · macro is market-wide. Kept for API symmetry."""
    signals = {}
    hits = 0
    total = 0

    def check(name, ok, weight=1.0, extra=None):
        nonlocal hits, total
        total += weight
        signals[name] = {"ok": bool(ok), "weight": weight, "extra": extra}
        if ok: hits += weight

    regime = _load(root, "macro_regime")
    cb = _load(root, "central_bank_state")
    curr = _load(root, "currency_intelligence")
    bond = _load(root, "bond_intelligence")
    vol = _load(root, "volatility_intelligence")

    # Regime state
    if regime:
        state = (regime.get("regime") or regime.get("state") or "").lower()
        check("regime_not_bearish", state not in ("bear", "risk_off", "bearish"),
                  weight=2.0, extra={"regime": state})
        check("regime_bullish", state in ("bull", "risk_on", "bullish"),
                  weight=1.0, extra={"regime": state})

    # Central bank stance
    if cb:
        stance = (cb.get("stance") or cb.get("current_stance") or "").lower()
        check("cb_not_hawkish", stance not in ("hawkish", "tightening"),
                  weight=1.0, extra={"stance": stance})

    # Currency stability (low volatility = good)
    if curr:
        curr_vol = curr.get("volatility") or curr.get("vol_30d")
        if isinstance(curr_vol, (int, float)):
            check("currency_stable", curr_vol < 0.15, weight=1.0,
                      extra={"currency_vol": curr_vol})

    # Bond yield direction
    if bond:
        direction = (bond.get("direction") or bond.get("yield_direction") or "").lower()
        check("yields_not_rising", direction not in ("rising", "up"),
                  weight=1.0, extra={"direction": direction})

    # Vol regime
    if vol:
        vix = vol.get("vix") or vol.get("current_vix")
        if isinstance(vix, (int, float)):
            check("vix_calm", vix < 20, weight=1.5, extra={"vix": vix})

    # If no macro data · neutral
    if total < 1.0:
        return 50.0, {"engine": "macro.v1", "score": 50.0,
                              "signals": signals, "note": "no macro reports found · neutral"}

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "macro.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
    }
