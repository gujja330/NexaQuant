"""AEGIS-X1 V2 · Full-stack FX/Crypto research runner.

Operator directive · "do complete setup use everything and test man ·
Regime classifier · Macro overlay · Cross-market · 6+ months · Cost model
· Crypto microstructure · technicals + fundamentals + smart money"

This version delivers what's ACHIEVABLE with free/available data:
  ✓ Regime classifier (4-state · ADX + ATR)
  ✓ Macro/cross-market overlay (DXY · US 10Y · VIX · S&P via yfinance)
  ✓ 6 months of hourly data (2y daily for regime context)
  ✓ Realistic cost model (spread + commission + slippage per asset class)
  ✓ Regime-adaptive strategy (trend-follow vs mean-revert)
  ✓ Walk-forward valid (higher-TF lookup strictly before entry bar)
  ✓ Per-regime metrics breakdown
  ✓ After-cost expectancy · Sharpe · max DD

NOT included (would need paid data sources):
  · Crypto funding rates (needs CoinGlass/Coinbase API)
  · On-chain flows (Glassnode/Nansen paid tier)
  · SMC order blocks (algorithmic detection · V3)
  · Fed/ECB/BOJ policy expectations (FRED needs pandas_datareader)
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(_ROOT))

    import yaml
    from backend.markets.engine import (
        build_cross_market, backtest_pair, summarize_trades,
    )

    cfg = yaml.safe_load((_ROOT / "configs" / "fx_v2_experiment.yaml").read_text(encoding="utf-8"))

    print(f"[fx_v2] AEGIS-X1 V2 · full-stack research")
    print(f"[fx_v2] {len(cfg['pairs'])} pairs · 1h/{cfg['data']['primary_lookback_days']}d "
              f"+ 1d/{cfg['data']['daily_lookback_days']}d")
    print(f"[fx_v2] regime: 4-state (TRENDING_UP/DOWN · RANGING · HIGH_VOL)")
    print(f"[fx_v2] context: DXY + US 10Y + VIX + S&P (risk-on/off filter)")
    print(f"[fx_v2] strategy: regime-adaptive · trend-follow OR mean-revert")
    print(f"[fx_v2] costs: spread + commission + slippage per asset class")
    print()

    print(f"[fx_v2] fetching cross-market context...")
    xm = build_cross_market(cfg)
    print(f"[fx_v2] cross-market loaded: {list(xm.keys())}")
    print()

    all_summaries = []
    for spec in cfg["pairs"]:
        try:
            trades, meta = backtest_pair(spec, cfg, xm) or ([], {})
            summary = summarize_trades(trades, spec)
            summary["meta"] = meta
            summary["sample_trades"] = [asdict(t) for t in trades[:3]]
            summary["last_5_trades"] = [asdict(t) for t in trades[-5:]]
            all_summaries.append(summary)
        except Exception as e:
            import traceback
            print(f"[{spec['symbol']}] FAIL · {type(e).__name__}: {e}")
            traceback.print_exc(limit=3)

    # Aggregate
    total_trades = sum(s.get("n_trades", 0) for s in all_summaries)
    total_wins = sum(s.get("n_wins", 0) for s in all_summaries)
    total_net = sum(s.get("net_total_pct", 0) for s in all_summaries)
    total_gross = sum(s.get("gross_total_pct", 0) for s in all_summaries)

    aggregate = {
        "n_pairs":                len(all_summaries),
        "n_trades_total":         total_trades,
        "n_wins_total":           total_wins,
        "portfolio_win_rate_pct": round(total_wins / max(1, total_trades) * 100, 1),
        "portfolio_gross_pct":    round(total_gross, 2),
        "portfolio_net_pct":      round(total_net, 2),
        "portfolio_cost_drag":    round(total_gross - total_net, 2),
        "portfolio_avg_net":      round(total_net / max(1, total_trades), 3),
    }

    out = _ROOT / "reports" / "research" / "fx_experiment_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":       "aegis_x1_v2_fx_full_stack.v2",
        "run_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_version": cfg.get("version"),
        "components": {
            "regime_classifier":  "4-state (TRENDING_UP · TRENDING_DOWN · RANGING · HIGH_VOL)",
            "cross_market":       ["DXY", "US_10Y", "VIX", "SP500"],
            "cost_model":         "spread + commission + slippage per asset class",
            "regime_adaptive":    "trend-follow (TRENDING) · mean-revert (RANGING) · no trade (HIGH_VOL)",
            "walk_forward":       "higher-TF lookup strictly before entry bar",
        },
        "aggregate":    aggregate,
        "per_pair":     all_summaries,
        "guardrails":   cfg["guardrails"],
    }
    out.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                       encoding="utf-8")
    print(f"\n[fx_v2] wrote {out}")

    # Print summary
    print()
    print("=" * 100)
    print(f"AGGREGATE (all {len(all_summaries)} pairs · {total_trades} trades · 6mo hourly · realistic costs)")
    print("=" * 100)
    print(f"Portfolio win rate:    {aggregate['portfolio_win_rate_pct']}%")
    print(f"Portfolio GROSS:       {aggregate['portfolio_gross_pct']:+.2f}%")
    print(f"Portfolio NET:         {aggregate['portfolio_net_pct']:+.2f}%")
    print(f"Cost drag:             {aggregate['portfolio_cost_drag']:.2f}%")
    print(f"Avg NET per trade:     {aggregate['portfolio_avg_net']:+.3f}%")
    print()
    print("PER PAIR (NET after all costs):")
    print(f"{'Symbol':10} {'Class':10} {'N':>5} {'WR%':>5} {'Gross%':>8} {'Net%':>8} {'AvgNet%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
    print("-" * 100)
    for s in all_summaries:
        if s.get("n_trades", 0) == 0:
            print(f"{s.get('symbol','?'):10} {'':10} {'0':>5} {'NO TRADES':>40}")
            continue
        print(f"{s['symbol']:10} {s.get('class','?'):10} {s['n_trades']:>5} "
                  f"{s['win_rate_pct']:>5.1f} {s['gross_total_pct']:>+8.2f} "
                  f"{s['net_total_pct']:>+8.2f} {s['avg_net_per_trade']:>+8.3f} "
                  f"{s['sharpe_annualized']:>7.2f} {s['max_drawdown_pct']:>+8.2f}")

    # Per-regime aggregate
    print()
    print("=" * 100)
    print("PER-REGIME BREAKDOWN (aggregate across all pairs)")
    print("=" * 100)
    regime_agg = {}
    for s in all_summaries:
        for regime, d in (s.get("by_regime") or {}).items():
            r = regime_agg.setdefault(regime, {"n": 0, "wins": 0, "net": 0})
            r["n"] += d["n"]
            r["wins"] += int(d["win_rate_pct"] / 100 * d["n"])
            r["net"] += d["net_total"]
    for regime, r in regime_agg.items():
        wr = r["wins"] / max(1, r["n"]) * 100
        avg = r["net"] / max(1, r["n"])
        print(f"  {regime:15} n={r['n']:>4} · win {wr:5.1f}% · net {r['net']:>+8.2f}% · avg {avg:>+6.3f}%")

    # Per-strategy aggregate
    print()
    print("PER-STRATEGY BREAKDOWN:")
    strat_agg = {}
    for s in all_summaries:
        for strat, d in (s.get("by_strategy") or {}).items():
            st = strat_agg.setdefault(strat, {"n": 0, "wins": 0, "net": 0})
            st["n"] += d["n"]
            st["wins"] += int(d["win_rate_pct"] / 100 * d["n"])
            st["net"] += d["net_total"]
    for strat, st in strat_agg.items():
        wr = st["wins"] / max(1, st["n"]) * 100
        avg = st["net"] / max(1, st["n"])
        print(f"  {strat:15} n={st['n']:>4} · win {wr:5.1f}% · net {st['net']:>+8.2f}% · avg {avg:>+6.3f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
