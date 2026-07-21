"""AEGIS USA · Risk Engine runner (Sprint 4, USD)."""
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

import yaml                                                                                  # noqa: E402

from backend.canonical.model              import USA_PROFILE                                # noqa: E402
from backend.feature_store                 import schema_fingerprint                        # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.risk                         import RiskEngine                                 # noqa: E402
from backend.risk.types                   import RiskBudget                                 # noqa: E402
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai                          import risk_analyst                                # noqa: E402


OUT_SIZED     = _USA / "reports" / "sized_positions.json"
OUT_REPORT    = _USA / "reports" / "risk_report.json"
OUT_NARRATIVE = _USA / "reports" / "ai_risk_narrative.json"

REC_PATH        = _USA / "reports" / "recommendations_v3.json"
MI_SUMMARY      = _USA / "reports" / "market_intelligence_summary.json"
BUDGET_PATH     = _ROOT / "configs" / "risk_budget.yaml"


def _stringify(v):
    if isinstance(v, dict):    return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [_stringify(x) for x in v]
    if isinstance(v, (date, datetime)): return v.isoformat()
    if hasattr(v, "value"):    return v.value
    return v


def _as_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _stringify(v) for k, v in asdict(obj).items()}
    return _stringify(obj)


def _load_budget(path: Path, market: str) -> RiskBudget:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    m = (data.get("market_defaults") or {}).get(market, {})
    return RiskBudget(
        market=market,
        max_kelly_fraction=float(m.get("max_kelly_fraction", 0.30)),
        per_ticker_cap=float(m.get("per_ticker_cap", 0.08)),
        per_sector_cap=float(m.get("per_sector_cap", 0.30)),
        target_portfolio_vol=float(m.get("target_portfolio_vol", 0.14)),
        enable_shorts=bool(m.get("enable_shorts", True)),
        default_stop_loss_pct=float(m.get("default_stop_loss_pct", -0.10)),
        confidence_tier_mult=dict(m.get("confidence_tier_mult", {
            "STRONG_BUY": 1.0, "BUY": 0.6, "HOLD": 0.0,
            "SELL": -0.6, "STRONG_SELL": -1.0,
        })),
    )


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70); print("  AEGIS USA · Risk Engine v1 (Sprint 4, USD)"); print("=" * 70)

    if not REC_PATH.exists():
        print("  FATAL: usa/reports/recommendations_v3.json missing"); return 1
    rec_doc = json.loads(REC_PATH.read_text(encoding="utf-8"))
    recs = rec_doc.get("recommendations", [])
    print(f"  recommendations: {len(recs)}")

    regime = "unknown"; vix = None
    if MI_SUMMARY.exists():
        try:
            mi = json.loads(MI_SUMMARY.read_text(encoding="utf-8"))
            regime = mi.get("regime", "unknown")
            sigs = mi.get("signals", {})
            vix_sig = sigs.get("vix") or {}
            if isinstance(vix_sig, dict):
                v = vix_sig.get("value")
                if v is not None: vix = float(v)
        except Exception: pass
    print(f"  regime: {regime}  vix: {vix}")

    budget = _load_budget(BUDGET_PATH, "usa")
    print(f"  budget: kelly={budget.max_kelly_fraction} · ticker_cap={budget.per_ticker_cap}"
          f" · sector_cap={budget.per_sector_cap} · target_vol={budget.target_portfolio_vol}"
          f" · shorts={budget.enable_shorts}")

    snaps = list_snapshots(_ROOT, "usa")
    if not snaps: print("  FATAL: no feature snapshot"); return 1
    latest = snaps[-1]
    df = read_snapshot(_ROOT, "usa", latest)
    if df is None or df.empty: print("  FATAL: snapshot empty"); return 1
    print(f"  snapshot: {latest.isoformat()} · rows={len(df)}")

    model_id = "aegis.risk.v1"
    register_model(_ROOT,
        model_id=model_id, engine="risk_engine",
        market="usa", version="1.0.0",
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by usa risk_engine on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, model_id)

    engine = RiskEngine(
        repo_root=_ROOT, market="usa", budget=budget,
        regime=regime, vix_level=vix,
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
        model_stamp=model_stamp,
    )
    sized, report = engine.run(recs, df, asof=latest)
    print(f"  sized: {report.n_positions} active (long={report.n_long} · short={report.n_short})")
    print(f"    gross: {report.gross_exposure_pct * 100:.2f}% · cash: {report.cash_pct * 100:.2f}%")
    print(f"    HHI:   {report.hhi_concentration:.4f} · top-5: {report.top_5_concentration_pct * 100:.2f}%")
    print(f"    VaR:   {report.portfolio_var_95_1d_pct * 100:.2f}% · CVaR: {report.portfolio_cvar_95_1d_pct * 100:.2f}%")
    print(f"    verdict: {report.verdict}  breaches: {len(report.breaches)}")

    OUT_SIZED.parent.mkdir(parents=True, exist_ok=True)
    OUT_SIZED.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": latest.isoformat(),
        "currency": USA_PROFILE.currency,
        "regime": regime, "vix_level": vix,
        "n_positions": report.n_positions,
        "positions": [_as_dict(p) for p in sized],
        "model_stamp": model_stamp,
        "budget_snapshot": {
            "max_kelly_fraction":   budget.max_kelly_fraction,
            "per_ticker_cap":       budget.per_ticker_cap,
            "per_sector_cap":       budget.per_sector_cap,
            "target_portfolio_vol": budget.target_portfolio_vol,
            "enable_shorts":        budget.enable_shorts,
        },
    }, indent=2, default=str), encoding="utf-8")

    OUT_REPORT.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": latest.isoformat(),
        **_as_dict(report),
    }, indent=2, default=str), encoding="utf-8")

    ai = risk_analyst.run(report, sized, "usa", latest)
    OUT_NARRATIVE.write_text(json.dumps({
        "engine": "ai_risk_narrative", "version": "v1.0",
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": latest.isoformat(),
        "output": _as_dict(ai),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote 3 files under usa/reports/")
    print(f"  ai: {ai.headline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
