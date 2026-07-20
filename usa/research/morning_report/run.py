"""AEGIS USA · Morning Research Report v1.0.

Consolidated daily briefing for USA — mirrors India's morning report
but with USD formatting and USA-specific benchmarks (S&P 500).
Emits usa/reports/morning_latest.{md,html}.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]
REPORTS = _USA / "reports"


def _load(name: str) -> dict | None:
    p = REPORTS / name
    if not p.exists(): return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _usd(x) -> str:
    if x is None: return "—"
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "—"


def _pct(x, places=2, sign=False) -> str:
    if x is None: return "—"
    try:
        v = float(x) * 100
    except Exception:
        return "—"
    return f"{v:{'+' if sign else ''}.{places}f}%"


def build_report() -> dict:
    recs   = _load("recommendations.json")            or {}
    intel  = _load("investment_intelligence.json")    or {}
    prices = _load("price_context.json")              or {}
    risk   = _load("risk_latest.json")                or {}
    lc     = _load("recommendation_lifecycle.json")   or {}
    bm     = _load("benchmark.json")                  or {}
    da     = _load("decision_attribution.json")       or {}

    intel_by = {str(r.get("ticker")): r for r in (intel.get("reports") or [])}
    price_by = prices.get("tickers") or {}
    da_by    = da.get("per_recommendation") or {}

    all_recs = recs.get("recommendations") or []
    buys = [r for r in all_recs if r.get("recommendation") in ("Strong-Buy", "Buy", "Accumulate")]
    buys.sort(key=lambda r: r.get("composite_decision_score") or 0, reverse=True)
    top10 = buys[:10]

    # Enrich top10 with helper fields for the template
    for r in top10:
        t = str(r.get("ticker"))
        ii = intel_by.get(t) or {}
        pc = price_by.get(t) or {}
        ee = r.get("entry_exit") or {}
        r["_intel"]  = ii.get("intelligence_score") or r.get("composite_decision_score")
        r["_cmp"]    = pc.get("cmp") or ee.get("latest_close")
        r["_target"] = ee.get("target_1")
        r["_stop"]   = ee.get("stop_loss")
        r["_hold"]   = ee.get("expected_holding_days")
        r["_da"]     = da_by.get(t)

    return {
        "date_ist":  (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST"),
        "date_ny":   (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M EDT"),
        "date_short": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "top10":     top10,
        "portfolio": {
            "n_recommendations": len(all_recs),
            "action_counts":     recs.get("action_counts", {}),
        },
        "risk":      risk.get("portfolio_risk", {}),
        "benchmark": bm.get("portfolio", {}),
        "lifecycle": lc,
        "n_days_archived": (lc.get("coverage") or {}).get("n_days_archived", 0),
        "days_remaining":  max(0, 30 - (lc.get("coverage") or {}).get("n_days_archived", 0)),
    }


def render_markdown(ctx: dict) -> str:
    L = []
    L.append(f"# AEGIS USA · Morning Research · {ctx['date_ny']}")
    L.append("")
    L.append(f"_Currency: USD ($) · Benchmark: S&P 500_")
    L.append("")

    ps = ctx["portfolio"]
    L.append("## Portfolio Summary")
    L.append(f"- **Total recommendations:** {ps['n_recommendations']}")
    ac = ps.get("action_counts") or {}
    L.append(f"- **Actions:** " + " · ".join(f"{k} {v}" for k, v in ac.items()))
    L.append("")

    r = ctx["risk"]
    L.append("## Risk & Capital")
    L.append(f"- **Positions:** {r.get('n_positions', 0)}  ·  "
             f"**Total deployment:** {(r.get('total_weight') or 0) * 100:.2f}%  ·  "
             f"**Cash:** {(r.get('cash_pct') or 0) * 100:.2f}%")
    L.append(f"- **Portfolio vol:** {(r.get('portfolio_vol_annual') or 0) * 100:.2f}% annualised  ·  "
             f"**Verdict:** {r.get('verdict', '—')}")
    L.append("")

    b = ctx["benchmark"]
    L.append("## Alpha vs S&P 500")
    L.append(f"- Trades benchmarked: {b.get('n_trades_benchmarked', 0)}")
    L.append(f"- Verdict: {b.get('verdict', 'insufficient_evidence')}")
    L.append("")

    L.append("## Top 10 Opportunities & Lifecycle  🟢 Live")
    L.append("| # | Ticker | Sector | Action | Score | CMP | Target | Stop | Hold |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ctx["top10"], 1):
        L.append(f"| {i} | **{r['ticker']}** | {r.get('sector', '—')} | "
                 f"{r.get('recommendation')} | {int(r.get('_intel') or 0)} | "
                 f"{_usd(r.get('_cmp'))} | {_usd(r.get('_target'))} | "
                 f"{_usd(r.get('_stop'))} | {r.get('_hold', '—')}d |")
    L.append("")

    L.append("## Archive Maturation")
    L.append(f"- **{ctx['n_days_archived']} / 30** archive days accumulated")
    L.append(f"- **{ctx['days_remaining']}** trading days until Winner Genome activates")
    L.append("")

    L.append("---")
    L.append(f"_Generated {ctx['date_ny']} · AEGIS USA v1.0 · USD_")
    return "\n".join(L) + "\n"


_HTML_CSS = """
:root { --bg: #fafaf8; --panel: #fff; --type-1: #1a1a1a; --type-2: #555; --type-3: #888;
        --rule: #e5e5e5; --pos: #1b7a3e; --neg: #b71c1c; --warn: #b76a02;
        --accent: #345c9c; --accent-hi: #1e3e75; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #14161a; --panel: #1c1f24; --type-1: #f0f0f0; --type-2: #b0b0b0;
    --type-3: #757575; --rule: #2a2d34; --pos: #4caf50; --neg: #ef5350;
    --warn: #ffb74d; --accent: #7ea1d1; --accent-hi: #b0c9e8; }
}
body { font: 14px ui-serif, Georgia, serif; margin: 0 auto; padding: 24px; max-width: 900px;
       background: var(--bg); color: var(--type-1); line-height: 1.55; }
h1 { font-size: 26px; }
h2 { font: 15px ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase;
     color: var(--type-2); border-bottom: 1px solid var(--rule); padding: 20px 0 6px;
     margin: 20px 0 12px; }
table { width: 100%; border-collapse: collapse; font: 12px ui-monospace, monospace; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--rule); }
th { color: var(--type-3); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
.kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;
       margin: 12px 0; }
.kpi > div { background: var(--panel); border: 1px solid var(--rule); padding: 10px 12px;
             border-radius: 4px; }
.kpi .k { font: 9px ui-monospace, monospace; color: var(--type-3); letter-spacing: 0.14em;
          text-transform: uppercase; }
.kpi .v { font: 18px ui-serif, Georgia, serif; margin-top: 4px; }
footer { color: var(--type-3); font: 10px ui-monospace, monospace; padding: 20px 0;
         border-top: 1px solid var(--rule); margin-top: 24px; }
"""


def render_html(ctx: dict) -> str:
    p = ctx["portfolio"]; r = ctx["risk"]; b = ctx["benchmark"]
    ac = p.get("action_counts") or {}

    parts = ["<!doctype html><html><head><meta charset='utf-8'>",
             f"<title>AEGIS USA · Morning · {ctx['date_short']}</title>",
             f"<style>{_HTML_CSS}</style></head><body>",
             f"<h1>AEGIS USA · Morning Research</h1>",
             f"<div style='color:var(--type-2);font-family:ui-monospace,monospace;font-size:11px;'>"
             f"{ctx['date_ny']} &nbsp;·&nbsp; USD ($) &nbsp;·&nbsp; Benchmark: S&amp;P 500</div>",
             "<h2>Portfolio Summary</h2>",
             "<div class='kpi'>",
             f"<div><div class='k'>Total Recs</div><div class='v'>{p['n_recommendations']}</div></div>"]
    for k, v in ac.items():
        parts.append(f"<div><div class='k'>{k}</div><div class='v'>{v}</div></div>")
    parts.append("</div>")

    parts.append("<h2>Risk &amp; Capital</h2>")
    parts.append("<div class='kpi'>")
    parts.append(f"<div><div class='k'>Positions</div><div class='v'>{r.get('n_positions', 0)}</div></div>")
    parts.append(f"<div><div class='k'>Deployed</div><div class='v'>{(r.get('total_weight') or 0) * 100:.2f}%</div></div>")
    parts.append(f"<div><div class='k'>Cash</div><div class='v'>{(r.get('cash_pct') or 0) * 100:.2f}%</div></div>")
    parts.append(f"<div><div class='k'>Port Vol</div><div class='v'>{(r.get('portfolio_vol_annual') or 0) * 100:.2f}%</div></div>")
    parts.append(f"<div><div class='k'>Verdict</div><div class='v' style='font-family:ui-monospace,monospace;font-size:14px;'>{r.get('verdict', '—')}</div></div>")
    parts.append("</div>")

    parts.append("<h2>Alpha vs S&amp;P 500</h2>")
    parts.append("<div class='kpi'>")
    parts.append(f"<div><div class='k'>Trades Benchmarked</div><div class='v'>{b.get('n_trades_benchmarked', 0)}</div></div>")
    parts.append(f"<div><div class='k'>Verdict</div><div class='v' style='font-family:ui-monospace,monospace;font-size:14px;'>{b.get('verdict', 'insufficient_evidence')}</div></div>")
    parts.append("</div>")

    parts.append("<h2>Top 10 Opportunities</h2>")
    parts.append("<div style='overflow-x:auto;'><table style='min-width:900px;'><thead><tr>"
                 "<th>#</th><th>Ticker</th><th>Sector</th><th>Action</th><th>Score</th>"
                 "<th>CMP</th><th>Target</th><th>Stop</th><th>Hold</th></tr></thead><tbody>")
    for i, r in enumerate(ctx["top10"], 1):
        parts.append(f"<tr><td>{i}</td><td><b>{r['ticker']}</b></td>"
                     f"<td>{r.get('sector', '—')}</td>"
                     f"<td>{r.get('recommendation')}</td>"
                     f"<td>{int(r.get('_intel') or 0)}</td>"
                     f"<td>{_usd(r.get('_cmp'))}</td>"
                     f"<td style='color:var(--pos)'>{_usd(r.get('_target'))}</td>"
                     f"<td style='color:var(--neg)'>{_usd(r.get('_stop'))}</td>"
                     f"<td>{r.get('_hold', '—')}d</td></tr>")
    parts.append("</tbody></table></div>")

    parts.append("<h2>Archive Maturation</h2>")
    pct = min(100, int((ctx["n_days_archived"] / 30) * 100))
    parts.append(f"<div style='height:8px;background:var(--rule);border-radius:4px;overflow:hidden;'>"
                 f"<div style='height:100%;width:{pct}%;background:var(--accent);'></div></div>")
    parts.append(f"<div style='font:11px ui-monospace,monospace;color:var(--type-3);margin-top:6px;'>"
                 f"<b>{ctx['n_days_archived']} / 30</b> archive days · "
                 f"<b>{ctx['days_remaining']}</b> trading days until Winner Genome activates</div>")

    parts.append(f"<footer>Generated {ctx['date_ny']} · AEGIS USA v1.0 · USD</footer>")
    parts.append("</body></html>")
    return "\n".join(parts)


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Morning Research Report v1.0")
    print("=" * 70)

    ctx = build_report()
    md = render_markdown(ctx); html = render_html(ctx)
    date = ctx["date_short"]

    (REPORTS / f"morning_{date}.md").write_text(md, encoding="utf-8")
    (REPORTS / f"morning_{date}.html").write_text(html, encoding="utf-8")
    (REPORTS / "morning_latest.md").write_text(md, encoding="utf-8")
    (REPORTS / "morning_latest.html").write_text(html, encoding="utf-8")

    print(f"  recommendations:  {ctx['portfolio']['n_recommendations']}")
    print(f"  top 10:           {len(ctx['top10'])}")
    print(f"  archive days:     {ctx['n_days_archived']}/30")
    print(f"  MD:               usa/reports/morning_latest.md ({(REPORTS / 'morning_latest.md').stat().st_size / 1024:.1f} KB)")
    print(f"  HTML:             usa/reports/morning_latest.html ({(REPORTS / 'morning_latest.html').stat().st_size / 1024:.1f} KB)")
    print(f"  elapsed:          {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
