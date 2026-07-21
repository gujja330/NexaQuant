"""AEGIS India · Execution Simulator runner (Sprint 7).

Reads:
  reports/portfolio_diff.json         (Sprint 5)
  reports/portfolio_v3.json           (for prior weights + current prices)
  features/india/{latest}.parquet     (mid_price, volatility_20d, volume)
  configs/execution_config.yaml       (starting_aum, slippage, commissions)

Emits:
  reports/execution_ledger.parquet    (append-only fills)
  reports/execution_summary.json      (per-run summary + AI narrative digest)
  reports/equity_curve.parquet        (daily equity points)
  reports/ai_execution_narrative.json (AI Execution Analyst)
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

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd                                                                          # noqa: E402
import yaml                                                                                  # noqa: E402

from backend.canonical.model              import INDIA_PROFILE                              # noqa: E402
from backend.feature_store                 import schema_fingerprint                        # noqa: E402
from backend.feature_store.feature_history import read_snapshot, list_snapshots            # noqa: E402
from backend.execution                    import ExecutionEngine                           # noqa: E402
from backend.model_registry.registry      import stamp, register_model, ModelStatus         # noqa: E402
from backend.ai                          import execution_analyst                          # noqa: E402


OUT_LEDGER    = _ROOT / "reports" / "execution_ledger.parquet"
OUT_SUMMARY   = _ROOT / "reports" / "execution_summary.json"
OUT_CURVE     = _ROOT / "reports" / "equity_curve.parquet"
OUT_NARRATIVE = _ROOT / "reports" / "ai_execution_narrative.json"

PORTFOLIO_DIFF = _ROOT / "reports" / "portfolio_diff.json"
PORTFOLIO_V3   = _ROOT / "reports" / "portfolio_v3.json"
CONFIG_PATH    = _ROOT / "configs" / "execution_config.yaml"


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


class _PriceProvider:
    """Wraps the Feature Store snapshot + prior state for the execution engine."""
    def __init__(self, features_df: pd.DataFrame, prior_weights: dict[str, float]):
        self.features = features_df.set_index("ticker") if "ticker" in features_df.columns else features_df
        self.prior = prior_weights

    def mid_price(self, ticker: str):
        if ticker not in self.features.index: return None
        row = self.features.loc[ticker]
        return float(row["close"]) if pd.notna(row.get("close")) else None

    def adv_20d_shares(self, ticker: str):
        if ticker not in self.features.index: return None
        row = self.features.loc[ticker]
        vol = row.get("volume")
        # Feature Store's `volume` is today's; approximate ADV_20d as today × 1.0 (Sprint 7 baseline)
        # Sprint 8+ can upgrade to true 20-day rolling ADV from raw parquet
        return float(vol) if vol is not None and pd.notna(vol) else None

    def vol_20d(self, ticker: str):
        if ticker not in self.features.index: return None
        row = self.features.loc[ticker]
        v = row.get("volatility_20d")
        if v is None or pd.isna(v): return None
        # Annualise from daily-stdev feature → annualised
        return float(v) * (252 ** 0.5)

    def close_price(self, d: date, ticker: str):
        # Sprint 7 has only today's snapshot — return the feature-store close
        return self.mid_price(ticker)

    def prior_weight(self, ticker: str):
        return float(self.prior.get(ticker, 0.0))


def main() -> int:
    now = datetime.now(timezone.utc)
    print("=" * 70); print("  AEGIS INDIA · Execution Simulator v1 (Sprint 7)"); print("=" * 70)

    if not PORTFOLIO_DIFF.exists():
        print("  FATAL: reports/portfolio_diff.json missing"); return 1
    diff_doc = json.loads(PORTFOLIO_DIFF.read_text(encoding="utf-8"))
    instructions = diff_doc.get("instructions", [])
    n_hold = sum(1 for i in instructions if str(i.get("action") or "") == "HOLD")
    n_executable = len(instructions) - n_hold
    print(f"  trade instructions: {len(instructions)}  ({n_executable} executable · {n_hold} HOLD)")

    # Prior weights from portfolio state
    prior_weights: dict[str, float] = {}
    if PORTFOLIO_V3.exists():
        try:
            pv3 = json.loads(PORTFOLIO_V3.read_text(encoding="utf-8"))
            for p in pv3.get("snapshot", {}).get("positions", []):
                prior_weights[str(p["ticker"])] = float(p.get("weight", 0.0))
        except Exception: pass

    if not CONFIG_PATH.exists():
        print("  FATAL: configs/execution_config.yaml missing"); return 1
    cfg_all = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = (cfg_all.get("market_defaults") or {}).get("india", {})
    print(f"  config: aum={cfg.get('starting_aum')} · commission={cfg.get('commission_bps')}bps"
          f" · min_slip={cfg.get('min_slippage_bps')}bps · max_daily_participation={cfg.get('max_daily_participation')}")

    # Load feature snapshot
    snaps = list_snapshots(_ROOT, "india")
    if not snaps: print("  FATAL: no feature snapshot"); return 1
    latest = snaps[-1]
    df = read_snapshot(_ROOT, "india", latest)
    if df is None or df.empty: print("  FATAL: snapshot empty"); return 1
    print(f"  snapshot: {latest.isoformat()} · rows={len(df)}")

    # Register model
    model_id = "aegis.execution.v1"
    register_model(_ROOT,
        model_id=model_id, engine="execution_simulator",
        market="india", version="1.0.0",
        feature_set_version=schema_fingerprint(),
        schema_version=schema_fingerprint(),
        approval_status=ModelStatus.EXPERIMENTAL,
        notes=f"registered by india/execution_simulator on {now.date().isoformat()}",
    )
    model_stamp = stamp(_ROOT, model_id)

    engine = ExecutionEngine(
        repo_root=_ROOT, market="india",
        starting_aum=float(cfg.get("starting_aum", 10_000_000)),
        min_slippage_bps=float(cfg.get("min_slippage_bps", 2.0)),
        liquidity_impact_bps=float(cfg.get("liquidity_impact_bps", 50.0)),
        vol_impact_bps=float(cfg.get("vol_impact_bps", 15.0)),
        commission_bps=float(cfg.get("commission_bps", 3.0)),
        max_daily_participation=float(cfg.get("max_daily_participation", 0.10)),
        gap_stop_out_threshold_pct=float(cfg.get("gap_stop_out_threshold_pct", 0.03)),
        schema_fingerprint=schema_fingerprint(),
        feature_set_version=schema_fingerprint(),
        model_stamp=model_stamp,
    )
    provider = _PriceProvider(df, prior_weights)
    fills, curve, summary = engine.run(instructions, provider, asof=latest)

    print(f"  fills:   {summary.n_fills_generated}  (partial: {summary.n_fills_partial})")
    print(f"  equity end:    ₹{summary.equity_value_end:,.2f}")
    print(f"  cash end:      ₹{summary.cash_end:,.2f}")
    print(f"  positions:     open={summary.n_open_positions} closed_today={summary.n_closed_positions_today}")
    print(f"  commission:    ₹{summary.total_commission:.2f}")
    print(f"  slippage:      ₹{summary.total_slippage:.2f}")
    print(f"  turnover:      {summary.turnover_today}")
    print(f"  honest_empty:  {summary.honest_empty}")
    if summary.honest_empty:
        print(f"  reason:        {summary.honest_empty_reason}")

    # Emit outputs
    OUT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    # Ledger — append-only parquet on natural key (market, ticker, fill_date, txn_id)
    if fills:
        df_new_fills = pd.DataFrame([_as_dict(f) for f in fills])
    else:
        df_new_fills = pd.DataFrame()
    if OUT_LEDGER.exists() and not df_new_fills.empty:
        try:
            df_old = pd.read_parquet(OUT_LEDGER)
            df_ledger = pd.concat([df_old, df_new_fills], ignore_index=True) \
                          .drop_duplicates(subset=["market", "ticker", "fill_date", "txn_id"],
                                              keep="last") \
                          .sort_values(["fill_date", "ticker"]).reset_index(drop=True)
        except Exception:
            df_ledger = df_new_fills
    else:
        df_ledger = df_new_fills
    if not df_ledger.empty:
        df_ledger.to_parquet(OUT_LEDGER, index=False)
        print(f"  wrote {OUT_LEDGER.relative_to(_ROOT)}  (total_rows={len(df_ledger)})")
    else:
        # Empty-but-valid — create a marker parquet with the schema for downstream consumers
        pd.DataFrame(columns=["market", "ticker", "fill_date", "txn_id", "action", "side",
                                "shares", "fill_price", "slippage_bps", "commission_bps",
                                "commission_amount", "partial_fill", "fill_ratio",
                                "intended_notional", "filled_notional",
                                "prior_weight", "new_weight", "model_stamp"]).to_parquet(OUT_LEDGER, index=False)
        print(f"  wrote {OUT_LEDGER.relative_to(_ROOT)}  (empty-but-valid schema)")

    # Equity curve
    if curve:
        df_curve = pd.DataFrame([_as_dict(p) for p in curve])
        df_curve.to_parquet(OUT_CURVE, index=False)
        print(f"  wrote {OUT_CURVE.relative_to(_ROOT)}  ({len(df_curve)} points)")
    else:
        pd.DataFrame(columns=["date", "equity_value", "cash", "long_notional",
                                "short_notional", "n_positions",
                                "daily_return_pct", "cumulative_return_pct"]).to_parquet(OUT_CURVE, index=False)
        print(f"  wrote {OUT_CURVE.relative_to(_ROOT)}  (empty-but-valid schema)")

    # Summary
    OUT_SUMMARY.write_text(json.dumps({
        "engine":   engine.ENGINE_ID, "version": engine.ENGINE_VERSION,
        "market":   "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof":     latest.isoformat(),
        "currency": INDIA_PROFILE.currency,
        "starting_aum": summary.starting_aum,
        **_as_dict(summary),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_SUMMARY.relative_to(_ROOT)}")

    # Sprint 7.5 · append to permanent history (fail-open)
    try:
        from backend.persistence import append_snapshot_row
        append_snapshot_row(json.loads(OUT_SUMMARY.read_text(encoding="utf-8")),
                             _ROOT / "reports" / "execution_history.parquet")
    except Exception as _hist_err:
        print(f"  history append warning (non-fatal): {_hist_err}")

    # AI narrative
    ai = execution_analyst.run(summary, "india", latest)
    OUT_NARRATIVE.write_text(json.dumps({
        "engine":  "ai_execution_narrative", "version": "v1.0",
        "market":  "india", "run_utc": now.isoformat(timespec="seconds"),
        "asof":    latest.isoformat(),
        "output":  _as_dict(ai),
    }, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {OUT_NARRATIVE.relative_to(_ROOT)}")
    print(f"  ai headline: {ai.headline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
