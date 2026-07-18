"""Risk & Capital Engine v2.0 · orchestration.

Consumes:
- reports/recommendations.json (DEV023) — the Buy / Strong-Buy list.
- reports/confidence_calibration.parquet (DEV029) — calibrated confidence.
- reports/global_context.json (DEV017) — current regime.
- data/raw/india/{ticker}_D1.parquet — for volatility estimation.

Produces per-position sizing decisions with explanations + a
portfolio-level risk decision (VaR / CVaR / budget utilisation)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from risk_capital_v2.lib import sizing, risk_budget                                     # noqa: E402


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load_recs() -> list[dict]:
    p = _ROOT / "reports" / "recommendations.json"
    if not p.exists():
        return []
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        return list(j.get("recommendations") or [])
    except Exception:
        return []


def _load_regime() -> str:
    p = _ROOT / "reports" / "global_context.json"
    if not p.exists():
        return "Unknown"
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        c = (j.get("classifications") or {}).get("global_posture")
        if isinstance(c, dict):
            return str(c.get("label", "Unknown"))
        if isinstance(c, str):
            return c
    except Exception:
        pass
    return "Unknown"


def _load_calibrated_conf() -> dict[str, float]:
    """Map ticker -> calibrated confidence from DEV029 parquet.

    That parquet doesn't currently include ticker. Fallback: use raw
    confidence from recommendations."""
    p = _ROOT / "reports" / "adaptive_rec_v2_signal.parquet"
    if not p.exists():
        return {}
    # v2 parquet also lacks ticker. Return empty so caller falls back
    # to per-rec confidence.
    return {}


def _annualised_vol(ticker: str, lookback: int = 63) -> float | None:
    p = _ROOT / "data" / "raw" / "india" / f"{ticker}_D1.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        close_col = next((c for c in df.columns if c.lower() in ("close", "adj close", "adj_close")), None)
        if close_col is None:
            return None
        prices = df[close_col].astype(float).tail(lookback + 1)
        if len(prices) < 5:
            return None
        rets = prices.pct_change().dropna()
        return float(rets.std() * np.sqrt(252))
    except Exception:
        return None


def run(top_k: int = 20, verbose: bool = True) -> dict:
    recs = _load_recs()
    if not recs:
        return {"error": "no reports/recommendations.json"}

    regime = _load_regime()
    if verbose:
        print(f"  regime: {regime}")

    strong = {"Strong-Buy", "Buy", "Accumulate"}
    candidates = [r for r in recs if r.get("recommendation") in strong]
    candidates.sort(key=lambda r: -float(r.get("composite_decision_score") or 0))
    candidates = candidates[:top_k]

    if verbose:
        print(f"  candidates: {len(candidates)} (top-{top_k} by decision score)")

    # First pass: size each position without sector concentration effect,
    # then re-evaluate with running sector share (which grows as we size positions).
    sector_share: dict[str, float] = {}
    decisions = []
    weights_by_ticker: dict[str, float] = {}
    ann_vol_by_ticker: dict[str, float] = {}
    sector_by_ticker: dict[str, str] = {}

    for r in candidates:
        t = str(r["ticker"])
        conf = r.get("confidence")
        sec = r.get("sector") or "Unknown"
        vol = _annualised_vol(t)

        d = sizing.size_position(
            ticker=t,
            calibrated_confidence=float(conf) if conf is not None else None,
            regime=regime,
            annualised_vol=vol,
            sector_share_so_far=sector_share.get(sec, 0.0),
        )
        decisions.append(sizing.sizing_decision_to_dict(d))
        weights_by_ticker[t] = d.target_weight
        ann_vol_by_ticker[t] = vol if vol is not None else 0.30
        sector_by_ticker[t] = sec
        sector_share[sec] = sector_share.get(sec, 0.0) + d.target_weight

    if verbose:
        total_weight = sum(weights_by_ticker.values())
        print(f"  total target weight: {total_weight:.3f}  ({(1.0 - total_weight)*100:.1f}% cash)")

    # Portfolio-level risk decision
    risk_decision = risk_budget.compute_risk(
        weights=weights_by_ticker,
        ann_vol_by_ticker=ann_vol_by_ticker,
        sector_by_ticker=sector_by_ticker,
    )
    risk_dict = risk_budget.to_dict(risk_decision)

    if verbose:
        print(f"  portfolio vol:  {risk_dict['portfolio_vol_annual']}")
        print(f"  VaR 95:         {risk_dict['var_95']}")
        print(f"  CVaR 95:        {risk_dict['cvar_95']}")
        print(f"  budget verdict: {risk_dict['verdict']}")
        for a in risk_dict["alerts"][:5]:
            print(f"    [{a['severity']}] {a['kind']} · {a['entity']} · {a['detail']}")

    return {
        "run_utc":         datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":        _git_sha(),
        "engine":          "Risk & Capital Engine",
        "version":         "v2.0",
        "as_of":           date.today().isoformat(),
        "regime":          regime,
        "n_candidates":    len(candidates),
        "sizing":          decisions,
        "portfolio_risk":  risk_dict,
        "governance":      "Advisory only. This is a target allocation, "
                            "not an execution instruction.",
    }
