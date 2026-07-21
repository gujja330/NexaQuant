"""Sprint 6.5 regression — Macro & Intermarket Intelligence Engine."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.macro_intel                  import (                                            # noqa: E402
    MacroIntelligenceEngine,
    read_commodities, read_currencies, read_bonds, compute_yield_curve,
    infer_central_bank_state, classify_volatility_regime,
    compute_sector_rotation, classify_macro_regime,
    apply_impact_matrix, build_macro_knowledge_graph,
    COMMODITY_IMPACT_MATRIX,
)
from backend.macro_intel.types           import CommodityReading, BondReading, RegimeLabel   # noqa: E402
from backend.ai                          import macro_analyst                              # noqa: E402


def _sample_macro_summary():
    """Sprint 1B macro_summary.json shape."""
    return {
        "per_symbol": [
            {"symbol": "CL=F",  "label": "WTI Crude",           "last": 82.19,
             "chg_1d_pct": -0.36, "chg_1w_pct": -1.23, "chg_1m_pct": -9.22},
            {"symbol": "BZ=F",  "label": "Brent Crude",          "last": 88.56,
             "chg_1d_pct":  0.52, "chg_1w_pct":  4.87, "chg_1m_pct": -4.87},
            {"symbol": "GC=F",  "label": "Gold",                 "last": 4029.5,
             "chg_1d_pct":  0.42, "chg_1w_pct":  2.10, "chg_1m_pct": -7.09},
            {"symbol": "UUP",   "label": "US Dollar Index",      "last": 28.33,
             "chg_1d_pct": -0.04, "chg_1w_pct":  0.15, "chg_1m_pct":  1.76},
            {"symbol": "^TNX",  "label": "10Y Treasury",         "last": 4.28,
             "chg_1d_pct": -0.30, "chg_1w_pct":  0.90, "chg_1m_pct":  2.03},
            {"symbol": "^FVX",  "label": "5Y Treasury",          "last": 4.27,
             "chg_1d_pct": -0.21, "chg_1w_pct":  0.50, "chg_1m_pct":  2.10},
            {"symbol": "^VIX",  "label": "S&P 500 volatility",   "last": 18.65,
             "chg_1d_pct":  1.20, "chg_1w_pct": -2.30, "chg_1m_pct":  4.50},
        ],
    }


# ── Commodity reader ────────────────────────────────────────────
def test_commodities_extracts_only_commodities():
    coms = read_commodities(_sample_macro_summary())
    syms = {c.symbol for c in coms}
    assert syms == {"CL=F", "BZ=F", "GC=F"}
    assert not any(c.symbol == "UUP" for c in coms)
    print(f"  [OK] commodities filter: {sorted(syms)}")


def test_commodity_trend_labels():
    coms = read_commodities(_sample_macro_summary())
    trends = {c.symbol: c.trend for c in coms}
    assert trends["BZ=F"] == "bull"       # +4.87 > 2
    assert trends["CL=F"] == "sideways"   # -1.23 within band
    print(f"  [OK] commodity trends: {trends}")


# ── Currency reader ─────────────────────────────────────────────
def test_currencies_extracts_only_currencies():
    curs = read_currencies(_sample_macro_summary())
    assert {c.symbol for c in curs} == {"UUP"}
    print(f"  [OK] currency filter: UUP")


# ── Bond reader + yield curve ───────────────────────────────────
def test_bonds_extracts_yields():
    bonds = read_bonds(_sample_macro_summary())
    syms = {b.symbol for b in bonds}
    assert syms == {"^TNX", "^FVX"}
    print(f"  [OK] bonds: {sorted(syms)}")


def test_yield_curve_slope():
    bonds = [BondReading(symbol="^TNX", label="10Y", yield_pct=4.5),
              BondReading(symbol="^FVX", label="5Y",  yield_pct=4.0)]
    slope, inversion = compute_yield_curve(bonds)
    assert slope == 50.0 and not inversion    # +50 bps, normal curve
    print(f"  [OK] curve slope 10Y-5Y = 50 bps, no inversion")


def test_yield_curve_inversion():
    bonds = [BondReading(symbol="^TNX", label="10Y", yield_pct=4.0),
              BondReading(symbol="^FVX", label="5Y",  yield_pct=4.5)]
    slope, inversion = compute_yield_curve(bonds)
    assert slope == -50.0 and inversion
    print(f"  [OK] inversion detected: 10Y < 5Y")


# ── Central bank ────────────────────────────────────────────────
def test_central_bank_state_shape():
    bonds = read_bonds(_sample_macro_summary())
    slope, inversion = compute_yield_curve(bonds)
    cb = infer_central_bank_state("usa", bonds, slope, inversion)
    assert cb.bank == "Fed"
    assert cb.rate_cycle in {"tightening", "easing", "neutral", "unknown"}
    print(f"  [OK] central bank state: {cb.bank} · cycle={cb.rate_cycle} · liquidity={cb.liquidity_score}")


# ── Volatility regime ───────────────────────────────────────────
def test_volatility_regime_bands():
    assert classify_volatility_regime("usa", 12).regime == "calm"
    assert classify_volatility_regime("usa", 20).regime == "normal"
    assert classify_volatility_regime("usa", 25).regime == "elevated"
    assert classify_volatility_regime("usa", 35).regime == "stress"
    assert classify_volatility_regime("usa", 45).regime == "panic"
    print(f"  [OK] volatility regime bands: calm/normal/elevated/stress/panic")


# ── Sector rotation ─────────────────────────────────────────────
def test_sector_rotation_from_etf_flows():
    etf_flows = {"per_etf": [
        {"ticker": "XLF", "return_pct":  7.80},   # Financials
        {"ticker": "XLK", "return_pct": -2.10},   # Tech
        {"ticker": "XLV", "return_pct":  3.20},   # Healthcare
    ]}
    r = compute_sector_rotation("usa", date(2026, 7, 21), etf_flows_summary=etf_flows)
    assert r.leaders[0]["sector"] == "Financials"
    assert r.laggards[0]["sector"] == "Technology"
    print(f"  [OK] sector rotation from ETF flows: leader={r.leaders[0]['sector']} laggard={r.laggards[0]['sector']}")


# ── Macro regime classifier ─────────────────────────────────────
def test_macro_regime_stress_flags_risk_off():
    coms = [CommodityReading(symbol="CL=F", label="WTI", last=100.0, chg_1w_pct=+10.0, trend="bull")]
    vol = classify_volatility_regime("usa", 42.0)   # panic
    r = classify_macro_regime("usa", date(2026, 7, 21),
                                 commodities=coms, currencies=[], bonds=[],
                                 volatility=vol, yield_curve_inversion=False)
    # score = panic(-0.8) + oil spike(-0.2) = -1.0 → risk_off
    assert r.primary_regime == RegimeLabel.RISK_OFF.value
    print(f"  [OK] macro regime: panic VIX + oil spike → risk_off (score={r.macro_score})")


def test_macro_regime_inversion_flags_recession_warning():
    coms = []; vol = classify_volatility_regime("usa", 15.0)   # calm
    r = classify_macro_regime("usa", date(2026, 7, 21),
                                 commodities=coms, currencies=[], bonds=[],
                                 volatility=vol, yield_curve_inversion=True)
    # score = calm(0.4) + inversion(-0.3) = 0.1 → not risk_on, not risk_off → recession_warning
    assert r.primary_regime == RegimeLabel.RECESSION_WARNING.value
    print(f"  [OK] macro regime: yield curve inversion → recession_warning")


# ── Impact matrix ───────────────────────────────────────────────
def test_impact_matrix_covers_key_commodities():
    assert ("CL=F", "up") in COMMODITY_IMPACT_MATRIX
    assert ("GC=F", "up") in COMMODITY_IMPACT_MATRIX
    assert ("HG=F", "up") in COMMODITY_IMPACT_MATRIX
    print(f"  [OK] impact matrix covers WTI + Gold + Copper (up direction)")


def test_impact_matrix_activates_on_material_moves():
    coms = [
        CommodityReading(symbol="CL=F", label="WTI", last=100, chg_1w_pct=+5.0),   # material up
        CommodityReading(symbol="GC=F", label="Gold", last=2000, chg_1w_pct=+0.5),  # not material
    ]
    active = apply_impact_matrix(coms, threshold_pct=3.0)
    assert len(active) == 1
    assert active[0].commodity == "WTI Crude"
    assert "Airlines" in active[0].negative_sectors
    print(f"  [OK] impact matrix: only material moves activate ({active[0].commodity} · airlines flagged)")


def test_impact_matrix_positive_and_negative():
    imp = COMMODITY_IMPACT_MATRIX[("CL=F", "up")]
    # Oil up: positive for Energy/Oil producers, negative for Airlines/Auto/FMCG
    assert "Energy" in imp.positive_sectors
    assert any("Air" in s for s in imp.negative_sectors)
    assert imp.confidence >= 0.85
    print(f"  [OK] impact matrix rationale correct for oil up: +{imp.positive_sectors[:2]} -{imp.negative_sectors[:2]}")


# ── Knowledge graph ─────────────────────────────────────────────
def test_knowledge_graph_builds_entries():
    coms = [CommodityReading(symbol="CL=F", label="WTI", last=100, chg_1w_pct=+5.0)]
    active = apply_impact_matrix(coms, threshold_pct=3.0)
    kg = build_macro_knowledge_graph(commodities=coms, currencies=[], bonds=[],
                                          volatility=None, active_impacts=active)
    assert len(kg) >= 1
    assert kg[0].factor_kind == "commodity"
    print(f"  [OK] knowledge graph built {len(kg)} entries")


# ── Engine end-to-end ───────────────────────────────────────────
def test_engine_end_to_end_runs():
    engine = MacroIntelligenceEngine(_ROOT, "usa")
    r = engine.run(asof=date(2026, 7, 21))
    assert r.market == "usa"
    assert r.macro_regime is not None
    assert r.volatility is not None
    assert r.central_bank is not None
    print(f"  [OK] engine end-to-end · regime={r.macro_regime.primary_regime} vol={r.volatility.regime}")


def test_engine_deterministic():
    e = MacroIntelligenceEngine(_ROOT, "usa")
    r1 = e.run(asof=date(2026, 7, 21))
    r2 = e.run(asof=date(2026, 7, 21))
    assert r1.macro_regime.macro_score == r2.macro_regime.macro_score
    assert len(r1.active_impacts) == len(r2.active_impacts)
    print(f"  [OK] engine deterministic across calls (score={r1.macro_regime.macro_score})")


def test_engine_accepts_cutoff():
    e = MacroIntelligenceEngine(_ROOT, "usa")
    past = date(2020, 1, 1)
    r = e.run(asof=past)
    assert r.asof == past
    print(f"  [OK] engine accepts historical cutoff (walk-forward ready)")


# ── AI Macro Analyst ────────────────────────────────────────────
def test_ai_macro_analyst_runs():
    e = MacroIntelligenceEngine(_ROOT, "usa")
    r = e.run(asof=date(2026, 7, 21))
    out = macro_analyst.run(r, "usa", date(2026, 7, 21))
    assert out.agent == "macro_analyst"
    assert out.headline and out.narrative
    print(f"  [OK] AI Macro Analyst: {out.headline[:80]}")


def test_ai_macro_analyst_never_promotes():
    e = MacroIntelligenceEngine(_ROOT, "usa")
    r = e.run(asof=date(2026, 7, 21))
    out = macro_analyst.run(r, "usa", date(2026, 7, 21))
    forbidden = {"buy", "sell", "target_price", "recommendation",
                  "action", "promoted", "approved"}
    for f in out.findings:
        keys = set(f.keys()) if isinstance(f, dict) else set()
        leak = keys & forbidden
        assert not leak, f"AI Macro Analyst leaked: {leak}"
    print(f"  [OK] AI Macro Analyst obeys no-promotion contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_runner():
    r = subprocess.run(
        [sys.executable, "india/macro_intel/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "reports" / "macro_regime.json").read_text(encoding="utf-8"))
    assert d["market"] == "india"
    print(f"  [OK] india runner: regime={d.get('primary_regime', '?')}")


def test_usa_runner():
    r = subprocess.run(
        [sys.executable, "usa/research/macro_intel/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    d = json.loads((_ROOT / "usa" / "reports" / "macro_regime.json").read_text(encoding="utf-8"))
    assert d["market"] == "usa"
    assert d["currency"] == "USD"
    print(f"  [OK] usa runner: regime={d.get('primary_regime', '?')} · currency={d['currency']}")


TESTS = [
    test_commodities_extracts_only_commodities, test_commodity_trend_labels,
    test_currencies_extracts_only_currencies,
    test_bonds_extracts_yields, test_yield_curve_slope, test_yield_curve_inversion,
    test_central_bank_state_shape,
    test_volatility_regime_bands,
    test_sector_rotation_from_etf_flows,
    test_macro_regime_stress_flags_risk_off, test_macro_regime_inversion_flags_recession_warning,
    test_impact_matrix_covers_key_commodities, test_impact_matrix_activates_on_material_moves,
    test_impact_matrix_positive_and_negative,
    test_knowledge_graph_builds_entries,
    test_engine_end_to_end_runs, test_engine_deterministic, test_engine_accepts_cutoff,
    test_ai_macro_analyst_runs, test_ai_macro_analyst_never_promotes,
    test_india_runner, test_usa_runner,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 6.5 · Macro & Intermarket Intelligence · Regression Tests")
    print("=" * 70)
    n_pass = 0; n_fail = 0
    for t in TESTS:
        try:
            t(); n_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}"); n_fail += 1
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}"); n_fail += 1
    print()
    print(f"  {n_pass} passed, {n_fail} failed of {len(TESTS)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
