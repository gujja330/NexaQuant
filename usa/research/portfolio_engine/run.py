"""AEGIS USA · Portfolio Engine runner (Sprint 5, USD)."""
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
from backend.portfolio                    import (                                            # noqa: E402
    PortfolioEngine, save_current_state, append_state_history,
)
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai                          import portfolio_analyst                          # noqa: E402


OUT_FULL      = _USA / "reports" / "portfolio_v3.json"
OUT_DIFF      = _USA / "reports" / "portfolio_diff.json"
OUT_NARRATIVE = _USA / "reports" / "ai_portfolio_narrative.json"

SIZED_PATH   = _USA / "reports" / "sized_positions.json"
MI_SUMMARY   = _USA / "reports" / "market_intelligence_summary.json"
CONFIG_PATH  = _ROOT / "configs" / "portfolio_config.yaml"


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


def _ticker_sector_map(sized_positions: list[dict]) -> dict[str, str]:
    m: dict[str, str] = {}
    for p in sized_positions:
        t = str(p.get("ticker") or "")
        s = str(p.get("sector") or "")
        if t and s:
            m[t] = s
    return m


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70); print("  AEGIS USA · Portfolio Engine v1 (Sprint 5, USD)"); print("=" * 70)

    if not SIZED_PATH.exists():
        print("  FATAL: usa/reports/sized_positions.json missing"); return 1
    sized_doc = json.loads(SIZED_PATH.read_text(encoding="utf-8"))
    positions_in = sized_doc.get("positions", [])
    print(f"  sized_positions input: {len(positions_in)}")

    regime = "unknown"
    if MI_SUMMARY.exists():
        try:
            regime = json.loads(MI_SUMMARY.read_text(encoding="utf-8")).get("regime", "unknown")
        except Exception: pass
    print(f"  regime: {regime}")

    cfg_all = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = (cfg_all.get("market_defaults") or {}).get("usa", {})
    g = cfg_all.get("global") or {}
    effective_n_min          = float(g.get("effective_n_min", 8.0))
    turnover_warning_threshold = float(g.get("turnover_warning_threshold", 0.30))
    print(f"  config: target_n={cfg.get('target_n_positions')} · min={cfg.get('min_position_size')}"
          f" · cash_min={cfg.get('cash_reserve_min')} · cash_stress={cfg.get('cash_reserve_stress')}"
          f" · rebal_bps={cfg.get('rebalance_threshold_bps')}")

    model_id = "aegis.portfolio.v1"
    register_model(_ROOT,
        model_id=model_id, engine="portfolio_engine",
        market="usa", version="1.0.0",
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by usa/portfolio_engine on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, model_id)

    engine = PortfolioEngine(
        repo_root=_ROOT, market="usa",
        target_n_positions=int(cfg.get("target_n_positions", 15)),
        min_position_size=float(cfg.get("min_position_size", 0.01)),
        cash_reserve_min=float(cfg.get("cash_reserve_min", 0.05)),
        cash_reserve_stress=float(cfg.get("cash_reserve_stress", 0.20)),
        rebalance_threshold_bps=int(cfg.get("rebalance_threshold_bps", 30)),
        regime=regime,
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
        model_stamp=model_stamp,
    )

    ts_map = _ticker_sector_map(positions_in)
    asof = date.fromisoformat(sized_doc.get("asof")) if sized_doc.get("asof") else date.today()
    snap, diff = engine.run(positions_in, ticker_sector=ts_map, asof=asof)

    print(f"  portfolio: {snap.n_positions} positions · "
          f"total_wgt={snap.total_weight:.4f} · cash={snap.cash_pct * 100:.2f}%")
    print(f"    HHI={snap.hhi:.4f} · effN={snap.effective_n:.2f} · top5={snap.top_5_pct * 100:.2f}%")
    print(f"    n_sectors={snap.n_sectors} · per_sector={snap.per_sector_pct}")
    print(f"  diff:  OPEN={diff.n_open} CLOSE={diff.n_close} INC={diff.n_increase} "
          f"DEC={diff.n_decrease} HOLD={diff.n_hold} · turnover={diff.turnover_pct * 100:.2f}%"
          f" · prior={diff.prior_asof}")

    OUT_FULL.parent.mkdir(parents=True, exist_ok=True)
    OUT_FULL.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": asof.isoformat(),
        "currency": USA_PROFILE.currency,
        "regime": regime,
        "config_snapshot": {
            "target_n_positions":      cfg.get("target_n_positions"),
            "min_position_size":       cfg.get("min_position_size"),
            "cash_reserve_min":        cfg.get("cash_reserve_min"),
            "cash_reserve_stress":     cfg.get("cash_reserve_stress"),
            "rebalance_threshold_bps": cfg.get("rebalance_threshold_bps"),
        },
        "snapshot": _as_dict(snap),
        "model_stamp": model_stamp,
    }, indent=2, default=str), encoding="utf-8")

    # Sprint 7.5 · append to standardized portfolio history (fail-open)
    try:
        from backend.persistence import append_snapshot_row
        append_snapshot_row(json.loads(OUT_FULL.read_text(encoding="utf-8")),
                             _ROOT / "usa" / "reports" / "portfolio_history.parquet")
    except Exception as _hist_err:
        print(f"  history append warning (non-fatal): {_hist_err}")

    OUT_DIFF.write_text(json.dumps({
        "engine": engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": asof.isoformat(),
        **_as_dict(diff),
    }, indent=2, default=str), encoding="utf-8")

    p_state = save_current_state(_ROOT, snap)
    p_hist  = append_state_history(_ROOT, snap)

    ai = portfolio_analyst.run(snap, diff, effective_n_min,
                                  turnover_warning_threshold, "usa", asof)
    OUT_NARRATIVE.write_text(json.dumps({
        "engine": "ai_portfolio_narrative", "version": "v1.0",
        "market": "usa", "run_utc": now.isoformat(timespec="seconds"),
        "asof": asof.isoformat(),
        "output": _as_dict(ai),
    }, indent=2, default=str), encoding="utf-8")

    print(f"  wrote 4 files under usa/reports/ (portfolio_v3, portfolio_diff, portfolio_state, ai_portfolio_narrative)")
    print(f"  appended {p_hist.relative_to(_ROOT)}")
    print(f"  ai headline: {ai.headline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
