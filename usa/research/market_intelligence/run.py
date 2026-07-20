"""AEGIS USA · Market Intelligence + AI narratives (Sprint 2).

Mirror of india/market_intelligence/run.py using USA_PROFILE. USD.
Emits:
  usa/reports/market_intelligence.json
  usa/reports/market_intelligence_summary.json
  usa/reports/ai_market_narrative.json
"""
from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.canonical.model import USA_PROFILE                                          # noqa: E402
from backend.canonical.adapters import adapt_all                                          # noqa: E402
from backend.market_intelligence.engine import MarketIntelligenceEngine                   # noqa: E402
from backend.ai import market_analyst, data_quality, evidence_summarizer                  # noqa: E402


OUT_INTEL     = _USA / "reports" / "market_intelligence.json"
OUT_SUMMARY   = _USA / "reports" / "market_intelligence_summary.json"
OUT_NARRATIVE = _USA / "reports" / "ai_market_narrative.json"


def _stringify(v):
    if isinstance(v, dict):
        return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_stringify(x) for x in v]
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _as_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _stringify(v) for k, v in asdict(obj).items()}
    return _stringify(obj)


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70); print("  AEGIS USA · Market Intelligence + AI (Sprint 2 · USD)"); print("=" * 70)

    engine = MarketIntelligenceEngine(_ROOT, USA_PROFILE)
    result = engine.run(cutoff=None)

    intel_dict = {
        "engine":          "market_intelligence",
        "version":         result.engine_version,
        "market":          result.market,
        "currency":        USA_PROFILE.currency,
        "currency_symbol": USA_PROFILE.currency_symbol,
        "benchmark":       USA_PROFILE.benchmark,
        "run_utc":         now.isoformat(timespec="seconds"),
        "asof":            result.asof.isoformat(),
        "n_inputs":        result.n_inputs,
        "composite_score": result.composite_score,
        "regime":          result.regime,
        "regime_label":    result.regime_label,
        "signals":         {k: _as_dict(v) for k, v in result.signals.items()},
        "notes":           result.notes,
    }
    OUT_INTEL.parent.mkdir(parents=True, exist_ok=True)
    OUT_INTEL.write_text(json.dumps(intel_dict, indent=2), encoding="utf-8")
    print(f"  regime: {result.regime_label}  (composite {result.composite_score:.1f}/100)")
    print(f"  signals: {len(result.signals)}")
    print(f"  wrote {OUT_INTEL.relative_to(_ROOT)}")

    summary = {
        "engine":          "market_intelligence",
        "version":         result.engine_version,
        "market":          result.market,
        "asof":            result.asof.isoformat(),
        "composite_score": result.composite_score,
        "regime":          result.regime,
        "regime_label":    result.regime_label,
        "signals":         {k: {"value": _stringify(v.value), "label": v.label}
                              for k, v in result.signals.items()},
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_SUMMARY.relative_to(_ROOT)}")

    canon = adapt_all(_ROOT, USA_PROFILE, cutoff=None,
                        include=["news", "fundamentals", "flow", "corporate_action",
                                   "earnings", "macro", "flow_proxy", "holding"])

    analyst_out = market_analyst.run(result)
    dq_out      = data_quality.run(_ROOT, "usa")
    ev_out      = evidence_summarizer.run(canon, "usa")

    narrative_bundle = {
        "engine":      "ai_market_narrative",
        "version":     "v1.0",
        "market":      "usa",
        "run_utc":     now.isoformat(timespec="seconds"),
        "asof":        result.asof.isoformat(),
        "agents": {
            "market_analyst":      _as_dict(analyst_out),
            "data_quality":        _as_dict(dq_out),
            "evidence_summarizer": _as_dict(ev_out),
        },
    }
    OUT_NARRATIVE.write_text(json.dumps(narrative_bundle, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_NARRATIVE.relative_to(_ROOT)}")
    print(f"  AI headlines:")
    print(f"    · analyst: {analyst_out.headline[:100]}")
    print(f"    · dq     : {dq_out.headline[:100]}")
    print(f"    · ev     : {ev_out.headline[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
