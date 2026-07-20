"""India vs USA · Cross-Market Comparison Report.

Reads India (reports/*.json) and USA (usa/reports/*.json) side by
side, emits compare/reports/comparison_latest.{md,html}. Pure
aggregation — no new engine. Read-only.

Currency-aware: India in ₹, USA in $. Never mixes them.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
INDIA = _ROOT / "reports"
USA   = _ROOT / "usa" / "reports"
OUT   = Path(__file__).resolve().parent / "reports"


def _load(base: Path, name: str) -> dict:
    p = base / name
    if not p.exists(): return {}
    try:    return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _count_action(recs: list[dict], action: str) -> int:
    return sum(1 for r in recs if r.get("recommendation") == action)


def build() -> dict:
    i_recs = _load(INDIA, "recommendations.json").get("recommendations") or []
    u_recs = _load(USA,   "recommendations.json").get("recommendations") or []
    i_risk = _load(INDIA, "risk_capital_v2_latest.json").get("portfolio_risk") or {}
    u_risk = _load(USA,   "risk_latest.json").get("portfolio_risk") or {}
    i_bm   = _load(INDIA, "benchmark.json").get("portfolio") or {}
    u_bm   = _load(USA,   "benchmark.json").get("portfolio") or {}
    i_lc   = _load(INDIA, "recommendation_lifecycle.json") or {}
    u_lc   = _load(USA,   "recommendation_lifecycle.json") or {}
    i_ops  = _load(INDIA, "ops_check.json")
    u_ops  = _load(USA,   "ops_check.json")

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "india": {
            "market":            "India",
            "currency":          "INR (₹)",
            "benchmark":         "NIFTY 50",
            "universe_size":     len(i_recs),
            "strong_buy":        _count_action(i_recs, "Strong-Buy"),
            "buy":               _count_action(i_recs, "Buy"),
            "accumulate":        _count_action(i_recs, "Accumulate"),
            "hold":              _count_action(i_recs, "Hold"),
            "reduce":            _count_action(i_recs, "Reduce"),
            "sell":              _count_action(i_recs, "Sell"),
            "n_positions":       i_risk.get("n_positions"),
            "deployed_pct":      (i_risk.get("total_weight") or 0) * 100,
            "cash_pct":          (i_risk.get("cash_pct") or 0) * 100,
            "portfolio_vol":     (i_risk.get("portfolio_vol_annual") or 0) * 100,
            "risk_verdict":      i_risk.get("verdict"),
            "trades_benchmarked": i_bm.get("n_trades_benchmarked"),
            "excess_alpha":      i_bm.get("excess_alpha_avg"),
            "pct_beat_benchmark": i_bm.get("pct_beat_nifty"),
            "benchmark_verdict": i_bm.get("verdict"),
            "archive_days":      (i_lc.get("coverage") or {}).get("n_days_archived", 0),
            "ops_verdict":       i_ops.get("verdict"),
            "artifacts":         f"{(i_ops.get('artifacts') or {}).get('n_present', '?')}/{(i_ops.get('artifacts') or {}).get('n_required', '?')}",
        },
        "usa": {
            "market":            "USA",
            "currency":          "USD ($)",
            "benchmark":         "S&P 500",
            "universe_size":     len(u_recs),
            "strong_buy":        _count_action(u_recs, "Strong-Buy"),
            "buy":               _count_action(u_recs, "Buy"),
            "accumulate":        _count_action(u_recs, "Accumulate"),
            "hold":              _count_action(u_recs, "Hold"),
            "reduce":            _count_action(u_recs, "Reduce"),
            "sell":              _count_action(u_recs, "Sell"),
            "n_positions":       u_risk.get("n_positions"),
            "deployed_pct":      (u_risk.get("total_weight") or 0) * 100,
            "cash_pct":          (u_risk.get("cash_pct") or 0) * 100,
            "portfolio_vol":     (u_risk.get("portfolio_vol_annual") or 0) * 100,
            "risk_verdict":      u_risk.get("verdict"),
            "trades_benchmarked": u_bm.get("n_trades_benchmarked"),
            "excess_alpha":      u_bm.get("excess_alpha_avg"),
            "pct_beat_benchmark": u_bm.get("pct_beat_spx"),
            "benchmark_verdict": u_bm.get("verdict"),
            "archive_days":      (u_lc.get("coverage") or {}).get("n_days_archived", 0),
            "ops_verdict":       u_ops.get("verdict"),
            "artifacts":         f"{(u_ops.get('artifacts') or {}).get('n_present', '?')}/{(u_ops.get('artifacts') or {}).get('n_required', '?')}",
        },
    }


def _pct(v, sign=True) -> str:
    if v is None: return "—"
    try:    x = float(v) * 100
    except Exception: return "—"
    return f"{x:{'+' if sign else ''}.2f}%"


def render_markdown(ctx: dict) -> str:
    i, u = ctx["india"], ctx["usa"]
    L = []
    L.append(f"# 🇮🇳 India vs 🇺🇸 USA · Cross-Market Comparison")
    L.append(f"_Generated {ctx['generated_utc']}_\n")

    def row(k, iv, uv): return f"| {k} | {iv} | {uv} |"

    L.append("| Metric | 🇮🇳 India | 🇺🇸 USA |")
    L.append("|---|---|---|")
    L.append(row("Currency",          i["currency"],          u["currency"]))
    L.append(row("Benchmark",         i["benchmark"],         u["benchmark"]))
    L.append(row("Universe size",     i["universe_size"],     u["universe_size"]))
    L.append(row("Strong-Buy",        i["strong_buy"],        u["strong_buy"]))
    L.append(row("Buy",               i["buy"],               u["buy"]))
    L.append(row("Accumulate",        i["accumulate"],        u["accumulate"]))
    L.append(row("Hold",              i["hold"],              u["hold"]))
    L.append(row("Reduce",            i["reduce"],            u["reduce"]))
    L.append(row("Sell",              i["sell"],              u["sell"]))
    L.append(row("Positions sized",   i["n_positions"] or "—", u["n_positions"] or "—"))
    L.append(row("Deployed %",        f"{i['deployed_pct']:.2f}%", f"{u['deployed_pct']:.2f}%"))
    L.append(row("Cash %",            f"{i['cash_pct']:.2f}%",     f"{u['cash_pct']:.2f}%"))
    L.append(row("Portfolio vol %",   f"{i['portfolio_vol']:.2f}%", f"{u['portfolio_vol']:.2f}%"))
    L.append(row("Risk verdict",      i["risk_verdict"] or "—",    u["risk_verdict"] or "—"))
    L.append(row("Trades benchmarked", i["trades_benchmarked"] if i["trades_benchmarked"] is not None else "—",
                                        u["trades_benchmarked"] if u["trades_benchmarked"] is not None else "—"))
    L.append(row("Historical alpha vs benchmark", _pct(i["excess_alpha"]), _pct(u["excess_alpha"])))
    L.append(row("% beat benchmark",  _pct(i["pct_beat_benchmark"], sign=False), _pct(u["pct_beat_benchmark"], sign=False)))
    L.append(row("Benchmark verdict", i["benchmark_verdict"] or "—", u["benchmark_verdict"] or "—"))
    L.append(row("Archive days",      f"{i['archive_days']}/30",  f"{u['archive_days']}/30"))
    L.append(row("Ops verdict",       i["ops_verdict"] or "—",    u["ops_verdict"] or "—"))
    L.append(row("Artifacts present", i["artifacts"],             u["artifacts"]))

    L.append("")
    L.append("## Independence")
    L.append("")
    L.append("India and USA are **fully independent deployments**. They share the repo but nothing else:")
    L.append("")
    L.append("- Different currencies (INR ₹ vs USD $)")
    L.append("- Different universes (Nifty vs Dow 30)")
    L.append("- Different benchmarks (NIFTY vs S&P 500)")
    L.append("- Different archives (`data/archive/` vs `usa/data/archive/`)")
    L.append("- Different Constitutions (`AEGIS_CONSTITUTION.md` vs `usa/AEGIS_USA_CONSTITUTION.md`)")
    L.append("- Different CI workflows (`aegis-ci.yml` vs `aegis-usa.yml`)")
    L.append("")
    L.append("Breaking one never affects the other.")
    return "\n".join(L) + "\n"


_HTML_CSS = """
:root { --bg:#fafaf8; --panel:#fff; --type-1:#1a1a1a; --type-2:#555; --type-3:#888;
        --rule:#e5e5e5; --pos:#1b7a3e; --neg:#b71c1c; --warn:#b76a02; --accent:#345c9c; }
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--panel:#1c1f24;--type-1:#f0f0f0;
  --type-2:#b0b0b0;--type-3:#757575;--rule:#2a2d34;--pos:#4caf50;--neg:#ef5350;
  --warn:#ffb74d;--accent:#7ea1d1;}}
body { font: 14px ui-serif, Georgia, serif; margin: 0 auto; padding: 24px; max-width: 1100px;
       background: var(--bg); color: var(--type-1); line-height: 1.55; }
h1 { font-size: 26px; margin-bottom: 4px; }
h2 { font: 14px ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase;
     color: var(--type-2); border-bottom: 1px solid var(--rule); padding: 20px 0 6px; }
table { width: 100%; border-collapse: collapse; font: 12px ui-monospace, monospace; }
th, td { padding: 8px 12px; border-bottom: 1px solid var(--rule); }
th { color: var(--type-3); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; text-align: center; }
td:first-child { color: var(--type-2); font-weight: 500; }
td:nth-child(2), td:nth-child(3) { text-align: center; color: var(--type-1); }
footer { color: var(--type-3); font: 10px ui-monospace, monospace; padding: 20px 0;
         border-top: 1px solid var(--rule); margin-top: 24px; }
"""


def render_html(ctx: dict) -> str:
    i, u = ctx["india"], ctx["usa"]
    def row(k, iv, uv):
        return f"<tr><td>{k}</td><td>{iv}</td><td>{uv}</td></tr>"
    parts = ["<!doctype html><html><head><meta charset='utf-8'>",
             "<title>India vs USA · Comparison</title>",
             f"<style>{_HTML_CSS}</style></head><body>",
             "<h1>🇮🇳 India vs 🇺🇸 USA · Cross-Market Comparison</h1>",
             f"<div style='color:var(--type-3);font:11px ui-monospace,monospace;'>Generated {ctx['generated_utc']}</div>",
             "<h2>Side-by-Side</h2>",
             "<table><thead><tr><th>Metric</th><th>🇮🇳 India</th><th>🇺🇸 USA</th></tr></thead><tbody>",
             row("Currency",           i["currency"],           u["currency"]),
             row("Benchmark",          i["benchmark"],          u["benchmark"]),
             row("Universe size",      i["universe_size"],      u["universe_size"]),
             row("Strong-Buy",         i["strong_buy"],         u["strong_buy"]),
             row("Buy",                i["buy"],                u["buy"]),
             row("Accumulate",         i["accumulate"],         u["accumulate"]),
             row("Hold",               i["hold"],               u["hold"]),
             row("Reduce",             i["reduce"],             u["reduce"]),
             row("Sell",               i["sell"],               u["sell"]),
             row("Positions sized",    i["n_positions"] or "—", u["n_positions"] or "—"),
             row("Deployed %",         f"{i['deployed_pct']:.2f}%", f"{u['deployed_pct']:.2f}%"),
             row("Cash %",             f"{i['cash_pct']:.2f}%",     f"{u['cash_pct']:.2f}%"),
             row("Portfolio vol %",    f"{i['portfolio_vol']:.2f}%", f"{u['portfolio_vol']:.2f}%"),
             row("Risk verdict",       i["risk_verdict"] or "—",    u["risk_verdict"] or "—"),
             row("Trades benchmarked", i["trades_benchmarked"] if i["trades_benchmarked"] is not None else "—",
                                        u["trades_benchmarked"] if u["trades_benchmarked"] is not None else "—"),
             row("Historical alpha",   _pct(i["excess_alpha"]),      _pct(u["excess_alpha"])),
             row("% beat benchmark",   _pct(i["pct_beat_benchmark"], sign=False), _pct(u["pct_beat_benchmark"], sign=False)),
             row("Benchmark verdict",  i["benchmark_verdict"] or "—", u["benchmark_verdict"] or "—"),
             row("Archive days",       f"{i['archive_days']}/30",  f"{u['archive_days']}/30"),
             row("Ops verdict",        i["ops_verdict"] or "—",     u["ops_verdict"] or "—"),
             row("Artifacts",          i["artifacts"],              u["artifacts"]),
             "</tbody></table>",
             "<h2>Independence</h2>",
             "<p>India and USA are <b>fully independent deployments</b>. Different currencies, "
             "different universes, different benchmarks, different archives, different Constitutions, "
             "different CI workflows. Breaking one never affects the other.</p>",
             f"<footer>Generated {ctx['generated_utc']} · AEGIS Cross-Market Comparison</footer>",
             "</body></html>"]
    return "\n".join(parts)


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  🇮🇳 India vs 🇺🇸 USA · Comparison Report")
    print("=" * 70)

    OUT.mkdir(parents=True, exist_ok=True)
    ctx = build()
    md = render_markdown(ctx); html = render_html(ctx)

    (OUT / "comparison_latest.md").write_text(md, encoding="utf-8")
    (OUT / "comparison_latest.html").write_text(html, encoding="utf-8")
    (OUT / "comparison_data.json").write_text(json.dumps(ctx, indent=2, default=str), encoding="utf-8")

    print(f"  India recs:   {ctx['india']['universe_size']}")
    print(f"  USA recs:     {ctx['usa']['universe_size']}")
    print(f"  Currencies:   {ctx['india']['currency']} · {ctx['usa']['currency']}")
    print(f"  Benchmarks:   {ctx['india']['benchmark']} · {ctx['usa']['benchmark']}")
    print(f"  MD:   compare/reports/comparison_latest.md")
    print(f"  HTML: compare/reports/comparison_latest.html")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
