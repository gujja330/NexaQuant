"""Sprint 2 regression suite — canonical model + market intelligence + AI agents.

Purely deterministic. All tests exercise the code paths a walk-forward
replay would take (adapters with cutoff, engine reproducibility, agent
determinism)."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.canonical.model import INDIA_PROFILE, USA_PROFILE                          # noqa: E402
from backend.canonical.schemas import KINDS, CanonicalDataset                            # noqa: E402
from backend.canonical.adapters import adapt_all                                          # noqa: E402
from backend.market_intelligence.engine import MarketIntelligenceEngine                   # noqa: E402
from backend.ai import market_analyst, data_quality, evidence_summarizer                  # noqa: E402


# ── Canonical model + adapters ─────────────────────────────────
def test_market_profiles_have_currency():
    assert INDIA_PROFILE.currency == "INR"
    assert USA_PROFILE.currency == "USD"
    assert INDIA_PROFILE.benchmark == "^NSEI"
    assert USA_PROFILE.benchmark == "^GSPC"
    print("  [OK] MarketProfile currency + benchmark set correctly")


def test_kinds_enumeration_complete():
    expected = {"bar", "fundamentals", "news", "flow", "corporate_action",
                 "earnings", "macro", "flow_proxy", "holding"}
    assert set(KINDS) == expected, f"KINDS drifted: {set(KINDS) ^ expected}"
    print(f"  [OK] KINDS enumeration matches ({len(KINDS)} canonical kinds)")


def test_adapt_all_returns_dict_of_canonical_datasets():
    """Every include-key must yield a CanonicalDataset (empty is fine)."""
    canon = adapt_all(_ROOT, INDIA_PROFILE, cutoff=None,
                        include=["bar", "fundamentals", "news", "flow"])
    assert set(canon.keys()) == {"bar", "fundamentals", "news", "flow"}
    for kind, ds in canon.items():
        assert isinstance(ds, CanonicalDataset), f"{kind} returned non-CanonicalDataset"
        assert ds.market == "india"
    print(f"  [OK] adapt_all returns CanonicalDataset per include-kind (4/4)")


def test_walk_forward_cutoff_filters_rows():
    """Adapter with a distant-past cutoff must yield ≤ rows than no-cutoff."""
    canon_now = adapt_all(_ROOT, USA_PROFILE, cutoff=None, include=["news"])
    canon_past = adapt_all(_ROOT, USA_PROFILE, cutoff=date(2020, 1, 1),
                            include=["news"])
    assert canon_past["news"].n_rows <= canon_now["news"].n_rows, \
        "cutoff filter did not reduce or preserve row count"
    print(f"  [OK] walk-forward cutoff filter: now={canon_now['news'].n_rows} past={canon_past['news'].n_rows}")


# ── Market Intelligence Engine ─────────────────────────────────
def test_market_intelligence_deterministic():
    """Same repo state + same cutoff must yield identical composite score."""
    e = MarketIntelligenceEngine(_ROOT, INDIA_PROFILE)
    r1 = e.run(cutoff=None)
    r2 = e.run(cutoff=None)
    assert r1.composite_score == r2.composite_score, \
        f"engine not deterministic: {r1.composite_score} != {r2.composite_score}"
    assert r1.regime == r2.regime
    print(f"  [OK] market intel deterministic: composite={r1.composite_score:.2f} regime={r1.regime}")


def test_market_intelligence_regime_in_valid_set():
    e = MarketIntelligenceEngine(_ROOT, USA_PROFILE)
    r = e.run(cutoff=None)
    assert r.regime in {"bull", "bear", "neutral", "stress", "unknown"}, \
        f"unknown regime: {r.regime}"
    assert 0 <= r.composite_score <= 100
    assert len(r.signals) > 0
    print(f"  [OK] USA market intel: regime={r.regime} composite={r.composite_score:.1f} "
           f"signals={len(r.signals)}")


# ── AI agents ──────────────────────────────────────────────────
def test_data_quality_agent_runs():
    """AI Data Quality Agent must produce a headline and narrative."""
    out = data_quality.run(_ROOT, "india")
    assert out.agent == "data_quality"
    assert out.headline and out.narrative
    assert 0.0 <= out.confidence <= 1.0
    print(f"  [OK] AI DataQuality: {out.headline[:60]}")


def test_market_analyst_agent_runs():
    e = MarketIntelligenceEngine(_ROOT, USA_PROFILE)
    r = e.run(cutoff=None)
    out = market_analyst.run(r)
    assert out.agent == "market_analyst"
    assert out.headline and out.narrative
    assert len(out.findings) == len(r.signals)
    print(f"  [OK] AI MarketAnalyst: {out.headline[:60]}")


def test_evidence_summarizer_agent_runs():
    canon = adapt_all(_ROOT, USA_PROFILE, cutoff=None,
                        include=["news", "fundamentals"])
    out = evidence_summarizer.run(canon, "usa")
    assert out.agent == "evidence_summarizer"
    assert out.headline and out.narrative
    print(f"  [OK] AI EvidenceSummarizer: {out.narrative[:80]}")


def test_agents_have_no_recommendation_output():
    """Contract: AI agents must not produce recommendations (no 'buy'/'sell'/'target' keys)."""
    canon = adapt_all(_ROOT, INDIA_PROFILE, cutoff=None, include=["news", "flow"])
    outs = [
        data_quality.run(_ROOT, "india"),
        market_analyst.run(MarketIntelligenceEngine(_ROOT, INDIA_PROFILE).run(cutoff=None)),
        evidence_summarizer.run(canon, "india"),
    ]
    for o in outs:
        # findings can NOT contain rec-like verbs
        for f in o.findings:
            keys = set(f.keys()) if isinstance(f, dict) else set()
            forbidden = {"buy", "sell", "target_price", "recommendation", "action"}
            leak = keys & forbidden
            assert not leak, f"{o.agent} findings leaked recommendation keys: {leak}"
    print(f"  [OK] all 3 AI agents obey no-recommendation contract")


# ── Integration ─────────────────────────────────────────────────
def test_india_market_intelligence_runner_emits_valid_json():
    r = subprocess.run(
        [sys.executable, "india/market_intelligence/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    intel = json.loads((_ROOT / "reports" / "market_intelligence.json")
                         .read_text(encoding="utf-8"))
    assert intel["market"] == "india"
    assert "composite_score" in intel
    print(f"  [OK] india market intel runner: regime={intel['regime']} "
           f"composite={intel['composite_score']}")


def test_usa_market_intelligence_runner_emits_valid_json():
    r = subprocess.run(
        [sys.executable, "usa/research/market_intelligence/run.py"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stderr[:500]}"
    intel = json.loads((_ROOT / "usa" / "reports" / "market_intelligence.json")
                         .read_text(encoding="utf-8"))
    assert intel["market"] == "usa"
    assert intel["currency"] == "USD"
    print(f"  [OK] usa market intel runner: regime={intel['regime']} "
           f"composite={intel['composite_score']} currency={intel['currency']}")


TESTS = [
    test_market_profiles_have_currency,
    test_kinds_enumeration_complete,
    test_adapt_all_returns_dict_of_canonical_datasets,
    test_walk_forward_cutoff_filters_rows,
    test_market_intelligence_deterministic,
    test_market_intelligence_regime_in_valid_set,
    test_data_quality_agent_runs,
    test_market_analyst_agent_runs,
    test_evidence_summarizer_agent_runs,
    test_agents_have_no_recommendation_output,
    test_india_market_intelligence_runner_emits_valid_json,
    test_usa_market_intelligence_runner_emits_valid_json,
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 70)
    print("  SPRINT 2 · Canonical Model + Market Intel + AI · Regression Tests")
    print("=" * 70)
    n_pass = 0; n_fail = 0
    for t in TESTS:
        try:
            t()
            n_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            n_fail += 1
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}")
            n_fail += 1
    print()
    print(f"  {n_pass} passed, {n_fail} failed of {len(TESTS)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
