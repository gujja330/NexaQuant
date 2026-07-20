"""Morning Research Report v1.0 · daily HTML + Markdown digest.

Produced at the tail of every daily orchestrator run. Reads whatever
artifacts already exist in reports/ and templates them into two static
files:

  reports/morning_YYYY-MM-DD.md    ← human-readable, LLM/email-friendly
  reports/morning_YYYY-MM-DD.html  ← standalone (no external CSS/JS)

No new engine. No new pipeline step other than this one. Pure
aggregation + templating.
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


_ROOT = Path(__file__).resolve().parents[2]
REPORTS = _ROOT / "reports"

# Import scoreboard aggregator (extension of the Morning Report per Constitution)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import scoreboard as _scoreboard          # noqa: E402


def _load(name: str) -> dict | None:
    p = REPORTS / name
    if not p.exists(): return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pct(x, places: int = 2, sign: bool = False) -> str:
    if x is None: return "—"
    try:
        v = float(x) * 100
    except Exception:
        return "—"
    s = f"{v:{'+' if sign else ''}.{places}f}%"
    return s


def _price(x) -> str:
    if x is None: return "—"
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return "—"


def _ids(rec: dict) -> int | None:
    """Investment Decision Score — same formula as the SPA."""
    parts: list[tuple[float, float]] = []
    ii = rec.get("_intel")
    if ii is not None:                              parts.append((ii, 0.55))
    else:
        score = rec.get("composite_decision_score")
        if score is not None:                        parts.append((score, 0.55))
    wr = rec.get("_hist_wr"); nh = rec.get("_n_hist") or 0
    if wr is not None and nh >= 3:                   parts.append((wr * 100, 0.20))
    conf = rec.get("confidence")
    if conf is not None:                             parts.append((conf * 100, 0.15))
    rel = rec.get("_reliability_stars")
    if rel is not None:                              parts.append((rel * 20, 0.10))
    if not parts: return None
    total_w = sum(w for _, w in parts)
    return max(0, min(100, round(sum(v * w for v, w in parts) / total_w)))


def build_report() -> dict:
    recs   = _load("recommendations.json")            or {}
    intel  = _load("investment_intelligence.json")    or {}
    prices = _load("price_context.json")              or {}
    risk   = _load("risk_capital_v2_latest.json")     or {}
    dc     = _load("decision_center_today.json")      or {}
    sv     = _load("stock_validation.json")           or {}
    lc     = _load("recommendation_lifecycle.json")   or {}
    mo     = _load("missed_opportunities.json")       or {}
    da     = _load("decision_attribution.json")       or {}
    bm     = _load("benchmark.json")                  or {}
    wg     = _load("winner_genome.json")              or {}
    gc     = _load("global_context.json")             or {}
    champ  = _load("champion_strategy.json")          or {}

    intel_by_ticker = {str(r.get("ticker")): r for r in (intel.get("reports") or [])}
    sv_tickers = sv.get("tickers") or {}
    price_tickers = prices.get("tickers") or {}
    da_per_rec = (da.get("per_recommendation") or {})
    bm_per_ticker = bm.get("per_ticker") or {}
    wg_matches = wg.get("matches") or {}

    # Enrich recs with everything needed to compute IDS + surface metrics
    enriched: list[dict] = []
    for r in (recs.get("recommendations") or []):
        t = str(r.get("ticker") or "")
        if not t: continue
        ii = intel_by_ticker.get(t) or {}
        svr = sv_tickers.get(t) or {}
        pc  = price_tickers.get(t) or {}
        ee  = r.get("entry_exit") or {}
        rec = dict(r)
        rec["_intel"] = ii.get("intelligence_score")
        rec["_hist_wr"] = svr.get("win_rate")
        rec["_n_hist"] = svr.get("n_trades") or 0
        rec["_reliability_stars"] = svr.get("reliability_stars")
        rec["_cmp"] = pc.get("cmp") if pc.get("available") else ee.get("latest_close")
        rec["_target_1"] = ee.get("target_1")
        rec["_stop"] = ee.get("stop_loss")
        rec["_buy_low"] = ee.get("ideal_entry_low")
        rec["_buy_high"] = ee.get("ideal_entry_high")
        rec["_hold_days"] = ee.get("expected_holding_days")
        rec["_ids"] = _ids(rec)
        rec["_bm"] = bm_per_ticker.get(t)
        rec["_wg"] = wg_matches.get(t)
        rec["_da"] = da_per_rec.get(t)
        enriched.append(rec)

    # Sort by IDS desc
    enriched.sort(key=lambda r: r.get("_ids") or -1, reverse=True)

    # Top 10 opportunities (Buy variants only)
    buys = [r for r in enriched if r.get("recommendation") in ("Strong-Buy", "Buy", "Accumulate")]
    top10 = buys[:10]

    # Portfolio metrics
    holdings = [r for r in enriched if r.get("currently_held")]
    portfolio_summary = {
        "n_recommendations": len(enriched),
        "n_holdings":        len(holdings),
        "n_strong_buy":      sum(1 for r in enriched if r.get("recommendation") == "Strong-Buy"),
        "n_buy":             sum(1 for r in enriched if r.get("recommendation") == "Buy"),
        "n_accumulate":      sum(1 for r in enriched if r.get("recommendation") == "Accumulate"),
        "n_hold":            sum(1 for r in enriched if r.get("recommendation") == "Hold"),
        "n_reduce":          sum(1 for r in enriched if r.get("recommendation") == "Reduce"),
        "n_sell":            sum(1 for r in enriched if r.get("recommendation") == "Sell"),
    }

    # Benchmark headline (backtester)
    bm_portfolio = bm.get("portfolio") or {}

    # Decision Attribution headline
    top_creator = (da.get("top_alpha_creators") or [None])[0]
    top_destroyer = (da.get("top_alpha_destroyers") or [None])[0]

    # Archive progress
    n_days = (lc.get("coverage") or {}).get("n_days_archived") or 0
    days_remaining = max(0, 30 - n_days)

    # Risk alerts
    risk_alerts = []
    exit_center = dc.get("exit_center") or []
    for x in exit_center[:8]:
        risk_alerts.append({
            "severity": x.get("severity"),
            "ticker":   x.get("ticker"),
            "reason":   " · ".join(x.get("reasons") or []),
        })
    port_risk = risk.get("portfolio_risk") or {}
    port_verdict = port_risk.get("verdict")
    if port_verdict in ("BLOCK", "WARNING"):
        risk_alerts.append({
            "severity": "PORTFOLIO_" + port_verdict,
            "ticker":   "PORTFOLIO",
            "reason":   f"vol {_pct(port_risk.get('portfolio_vol_annual'))} · "
                          f"{len(port_risk.get('alerts') or [])} budget alerts",
        })

    # Overnight changes
    changes = dc.get("changes") or []
    priority = ["NEW", "UPGRADED", "TARGET_HIT", "STOP_HIT",
                  "DOWNGRADED", "EXITED", "REMOVED"]
    changes = sorted(changes, key=lambda c: (priority.index(c["kind"])
                                                 if c.get("kind") in priority else 99,
                                                 c.get("ticker") or ""))[:15]

    # Missed opportunities headline
    n_missed = mo.get("n_events") or 0
    missed_examples = (mo.get("top_missed") or [])[:5]

    # Lifecycle scoreboard — day-by-day trajectory of today's Top-10 recs
    lifecycle_scoreboard = _scoreboard.build_scoreboard(top_n=10)

    return {
        "scoreboard":          lifecycle_scoreboard,
        "date_ist":            (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST"),
        "date_short":          datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "portfolio_summary":   portfolio_summary,
        "top10":               top10,
        "bm_portfolio":        bm_portfolio,
        "top_creator":         top_creator,
        "top_destroyer":       top_destroyer,
        "n_archive_days":      n_days,
        "days_remaining":      days_remaining,
        "risk_alerts":         risk_alerts,
        "changes":             changes,
        "n_missed":            n_missed,
        "missed_examples":     missed_examples,
        "champion":            champ.get("champion") or {},
        "global_context":      gc,
        "dc_overnight_summary": dc.get("overnight_summary"),
    }


# ─── Markdown template ─────────────────────────────────────────────

def render_markdown(ctx: dict) -> str:
    L: list[str] = []
    L.append(f"# AEGIS Morning Research · {ctx['date_ist']}")
    L.append("")
    L.append(f"> {ctx.get('dc_overnight_summary') or 'Overnight summary not available.'}")
    L.append("")

    # Portfolio Summary
    ps = ctx["portfolio_summary"]
    L.append("## Portfolio Summary")
    L.append("")
    L.append(f"- **Total recommendations:** {ps['n_recommendations']}  ·  **Held:** {ps['n_holdings']}")
    L.append(f"- **Strong-Buy:** {ps['n_strong_buy']}  ·  **Buy:** {ps['n_buy']}  ·  "
             f"**Accumulate:** {ps['n_accumulate']}  ·  **Hold:** {ps['n_hold']}  ·  "
             f"**Reduce:** {ps['n_reduce']}  ·  **Sell:** {ps['n_sell']}")
    L.append("")

    # Alpha vs NIFTY (backtester)
    L.append("## Alpha vs NIFTY  🔵 Backtester")
    L.append("")
    p = ctx["bm_portfolio"]
    if p:
        L.append(f"- **AEGIS avg return:** {_pct(p.get('aegis_avg_return'), sign=True)}  ·  "
                 f"**NIFTY:** {_pct(p.get('nifty_avg_return'), sign=True)}")
        L.append(f"- **Excess α:** {_pct(p.get('excess_alpha_avg'), sign=True)}  ·  "
                 f"**Beat NIFTY:** {p.get('n_beat_nifty')}/{p.get('n_trades_benchmarked')} "
                 f"({_pct(p.get('pct_beat_nifty'))})")
        L.append(f"- **Verdict:** {p.get('verdict', '—')}")
    else:
        L.append("- No benchmark data yet.")
    L.append("")

    # Top 10 Opportunities
    L.append("## Top 10 Opportunities  🟢 Live")
    L.append("")
    L.append("| # | Ticker | Action | Score | CMP | Target | Stop | Hold | α vs NIFTY (hist) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ctx["top10"], 1):
        alpha = None
        if r.get("_bm"):
            alpha = r["_bm"].get("excess_alpha_avg")
        L.append(f"| {i} | **{r['ticker']}** | {r.get('recommendation')} | "
                 f"{r.get('_ids') or '—'} | {_price(r.get('_cmp'))} | "
                 f"{_price(r.get('_target_1'))} | {_price(r.get('_stop'))} | "
                 f"{r.get('_hold_days') or '—'}d | "
                 f"{_pct(alpha, sign=True) if alpha is not None else '—'} |")
    L.append("")

    # Recommendation Lifecycle Scoreboard — day-by-day trajectory
    L.append("## Recommendation Lifecycle Scoreboard  🟢 Live")
    L.append("")
    L.append("| # | Ticker | Sector | Age | Entry | Day+1 | Day+3 | Day+5 | Day+10 | Current | MaxGain | MaxDD | Status |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ctx.get("scoreboard") or [], 1):
        age = f"{r.get('age_days')}/{r.get('expected_hold') or '—'}d" if r.get('age_days') is not None else "—"
        L.append(f"| {i} | **{r['ticker']}** | {r.get('sector', '—')} | {age} | "
                 f"{_price(r.get('entry_price'))} | "
                 f"{_pct(r.get('d1'), sign=True) if r.get('d1') is not None else '—'} | "
                 f"{_pct(r.get('d3'), sign=True) if r.get('d3') is not None else '—'} | "
                 f"{_pct(r.get('d5'), sign=True) if r.get('d5') is not None else '—'} | "
                 f"{_pct(r.get('d10'), sign=True) if r.get('d10') is not None else '—'} | "
                 f"{_pct(r.get('current_return'), sign=True) if r.get('current_return') is not None else '—'} | "
                 f"{_pct(r.get('max_gain'), sign=True) if r.get('max_gain') is not None else '—'} | "
                 f"{_pct(r.get('max_dd'), sign=True) if r.get('max_dd') is not None else '—'} | "
                 f"{r.get('status', '—')} |")
    L.append("")
    L.append("_Day+N columns are trading-day forward returns from first_seen_date. "
             "Populate as archive matures — expect empty until Day 10 of live operation._")
    L.append("")

    # Overnight Changes
    if ctx["changes"]:
        L.append("## Overnight Changes")
        L.append("")
        L.append("| Ticker | Kind | Yesterday → Today | Reason |")
        L.append("|---|---|---|---|")
        for c in ctx["changes"]:
            L.append(f"| **{c.get('ticker')}** | {c.get('kind', '').replace('_', ' ')} | "
                     f"{c.get('yesterday_action') or '—'} → {c.get('today_action') or '—'} | "
                     f"{(c.get('reason') or '').replace('|', '/')} |")
        L.append("")
    else:
        L.append("## Overnight Changes")
        L.append("")
        L.append("_No material changes overnight — recommendation set is stable._")
        L.append("")

    # Risk Alerts
    if ctx["risk_alerts"]:
        L.append("## Risk Alerts")
        L.append("")
        for a in ctx["risk_alerts"]:
            L.append(f"- **{a['severity']}** · `{a['ticker']}` — {a['reason']}")
        L.append("")

    # Subsystem Attribution
    L.append("## Subsystem Attribution  🔵 Backtester")
    L.append("")
    tc = ctx.get("top_creator")
    td = ctx.get("top_destroyer")
    if tc:
        L.append(f"- **Alpha Creator:** `{tc['subsystem']}` · α {_pct(tc['alpha_created'], sign=True)} · "
                 f"lift {tc['lift']:.2f} · WR high {_pct(tc['wr_high'])} vs low {_pct(tc['wr_low'])}")
    if td:
        L.append(f"- **Alpha Destroyer:** `{td['subsystem']}` · α {_pct(td['alpha_created'], sign=True)} · "
                 f"lift {td['lift']:.2f} · WR high {_pct(td['wr_high'])} vs low {_pct(td['wr_low'])}")
    L.append("")

    # Missed opportunities
    if ctx["n_missed"]:
        L.append(f"## Missed Opportunities  🟢 Live")
        L.append("")
        L.append(f"Detected **{ctx['n_missed']}** events where a ticker moved > threshold but was not in the recommendation set.")
        if ctx["missed_examples"]:
            for m in ctx["missed_examples"]:
                L.append(f"- `{m.get('ticker')}` on {m.get('anchor_date')} — "
                         f"{m.get('forward_days')}-day return {_pct(m.get('forward_return'), sign=True)} · "
                         f"blocked by `{m.get('blocking_reason')}`")
        L.append("")

    # Archive Progress
    L.append("## Archive Maturation")
    L.append("")
    L.append(f"- **{ctx['n_archive_days']} / 30** archive days accumulated")
    L.append(f"- **{ctx['days_remaining']}** trading days until Alpha Signature v2.1 gate unlocks")
    L.append("")

    # Action Items
    L.append("## Action Items")
    L.append("")
    action_items: list[str] = []
    # New strong buys
    new_strong = [c for c in ctx["changes"] if c.get("kind") == "NEW"
                    and c.get("today_action") == "Strong-Buy"]
    if new_strong:
        for c in new_strong[:5]:
            action_items.append(f"Consider entering `{c.get('ticker')}` — new Strong-Buy overnight")
    # Target hits
    target_hits = [c for c in ctx["changes"] if c.get("kind") == "TARGET_HIT"]
    for c in target_hits[:5]:
        action_items.append(f"Review `{c.get('ticker')}` — target achieved; consider partial exit")
    # Stop hits
    stop_hits = [c for c in ctx["changes"] if c.get("kind") == "STOP_HIT"]
    for c in stop_hits[:5]:
        action_items.append(f"Exit `{c.get('ticker')}` — stop-loss triggered")
    if not action_items:
        action_items.append("No immediate actions required today.")
    for a in action_items:
        L.append(f"- {a}")
    L.append("")

    # Footer
    L.append("---")
    L.append(f"_Generated {ctx['date_ist']} · AEGIS v2 (LOCKED)_")
    L.append(f"_Provenance: recommendations.json · investment_intelligence.json · benchmark.json · "
             f"decision_attribution.json · decision_center_today.json · winner_genome.json · "
             f"recommendation_lifecycle.json · missed_opportunities.json_")
    return "\n".join(L) + "\n"


# ─── HTML template (standalone; no external deps) ─────────────────

_HTML_CSS = """
:root {
  --bg: #fafaf8; --panel: #ffffff; --type-1: #1a1a1a; --type-2: #555;
  --type-3: #888; --rule: #e5e5e5; --pos: #1b7a3e; --neg: #b71c1c;
  --warn: #b76a02; --info: #3562b8; --accent: #345c9c; --accent-hi: #1e3e75;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #14161a; --panel: #1c1f24; --type-1: #f0f0f0; --type-2: #b0b0b0;
    --type-3: #757575; --rule: #2a2d34; --pos: #4caf50; --neg: #ef5350;
    --warn: #ffb74d; --info: #64b5f6; --accent: #7ea1d1; --accent-hi: #b0c9e8; }
}
* { box-sizing: border-box; }
body { font-family: ui-serif, Baskerville, Georgia, serif; margin: 0; padding: 24px;
       max-width: 900px; margin: 0 auto; background: var(--bg); color: var(--type-1);
       line-height: 1.55; font-size: 14px; }
h1 { font-size: 26px; letter-spacing: -0.01em; margin: 0 0 8px; }
h2 { font-size: 15px; font-family: ui-monospace, monospace; letter-spacing: 0.12em;
     text-transform: uppercase; color: var(--type-2); border-bottom: 1px solid var(--rule);
     padding: 20px 0 6px; margin: 20px 0 12px; }
.blockquote { font-style: italic; color: var(--type-2); border-left: 3px solid var(--accent);
              padding: 6px 12px; margin: 12px 0 18px; background: var(--panel); }
table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 12px;
        font-family: ui-monospace, monospace; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--rule); }
th { color: var(--type-3); font-weight: normal; letter-spacing: 0.08em;
     text-transform: uppercase; font-size: 10px; }
td .pos { color: var(--pos); }
td .neg { color: var(--neg); }
.pill { display: inline-block; padding: 1px 6px; border-radius: 3px;
        font-family: ui-monospace, monospace; font-size: 10px; letter-spacing: 0.06em; }
.pill.strong-buy { background: color-mix(in srgb, var(--pos) 20%, transparent); color: var(--pos); }
.pill.buy       { background: color-mix(in srgb, var(--pos) 12%, transparent); color: var(--pos); }
.pill.accumulate{ background: color-mix(in srgb, var(--pos) 8%, transparent);  color: var(--pos); }
.pill.hold      { background: color-mix(in srgb, var(--warn) 12%, transparent); color: var(--warn); }
.pill.reduce    { background: color-mix(in srgb, var(--neg) 10%, transparent); color: var(--neg); }
.pill.sell      { background: color-mix(in srgb, var(--neg) 18%, transparent); color: var(--neg); }
.tag { display: inline-block; padding: 1px 5px; border-radius: 2px;
       font: 8px ui-monospace, monospace; letter-spacing: 0.1em; text-transform: uppercase;
       vertical-align: middle; margin-left: 4px; }
.tag.live { color: var(--pos); border: 1px solid color-mix(in srgb, var(--pos) 40%, transparent); }
.tag.bt   { color: var(--type-3); border: 1px solid var(--rule); }
.kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
       gap: 10px; margin: 12px 0; }
.kpi > div { background: var(--panel); border: 1px solid var(--rule); padding: 10px 12px;
             border-radius: 4px; }
.kpi .k { font: 9px ui-monospace, monospace; color: var(--type-3);
          letter-spacing: 0.14em; text-transform: uppercase; }
.kpi .v { font-family: ui-serif, Baskerville, serif; font-size: 18px; margin-top: 4px; }
.kpi .s { font: 10px ui-monospace, monospace; color: var(--type-3); margin-top: 2px; }
footer { color: var(--type-3); font: 10px ui-monospace, monospace; letter-spacing: 0.02em;
         padding: 20px 0; border-top: 1px solid var(--rule); margin-top: 24px; line-height: 1.7; }
@media print { body { background: white; color: black; } h2 { color: #333; } }
"""


def _pill(action: str | None) -> str:
    if not action: return ""
    cls = action.lower().replace(" ", "-")
    return f'<span class="pill {cls}">{action}</span>'


def render_html(ctx: dict) -> str:
    p   = ctx["bm_portfolio"]
    ps  = ctx["portfolio_summary"]
    tc  = ctx.get("top_creator")
    td  = ctx.get("top_destroyer")

    parts: list[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>AEGIS Morning Research · {ctx['date_short']}</title>")
    parts.append(f"<style>{_HTML_CSS}</style>")
    parts.append("</head><body>")

    parts.append(f"<h1>AEGIS Morning Research</h1>")
    parts.append(f"<div style='color:var(--type-2);font-family:ui-monospace,monospace;font-size:11px;letter-spacing:0.06em;'>"
                    f"{ctx['date_ist']}</div>")

    parts.append(f"<div class='blockquote'>{ctx.get('dc_overnight_summary') or 'Overnight summary not available.'}</div>")

    # Portfolio Summary
    parts.append("<h2>Portfolio Summary</h2>")
    parts.append("<div class='kpi'>")
    parts.append(f"<div><div class='k'>Total Recs</div><div class='v'>{ps['n_recommendations']}</div><div class='s'>{ps['n_holdings']} held</div></div>")
    parts.append(f"<div><div class='k'>Strong-Buy</div><div class='v' style='color:var(--pos)'>{ps['n_strong_buy']}</div></div>")
    parts.append(f"<div><div class='k'>Buy</div><div class='v'>{ps['n_buy']}</div></div>")
    parts.append(f"<div><div class='k'>Accumulate</div><div class='v'>{ps['n_accumulate']}</div></div>")
    parts.append(f"<div><div class='k'>Hold</div><div class='v' style='color:var(--warn)'>{ps['n_hold']}</div></div>")
    parts.append(f"<div><div class='k'>Reduce/Sell</div><div class='v' style='color:var(--neg)'>{ps['n_reduce'] + ps['n_sell']}</div></div>")
    parts.append("</div>")

    # Alpha vs NIFTY
    parts.append("<h2>Alpha vs NIFTY <span class='tag bt'>Backtester</span></h2>")
    if p:
        aa = p.get("aegis_avg_return")
        nn = p.get("nifty_avg_return")
        ea = p.get("excess_alpha_avg")
        parts.append("<div class='kpi'>")
        parts.append(f"<div><div class='k'>AEGIS Avg</div><div class='v' style='color:{'var(--pos)' if aa and aa>0 else 'var(--neg)'}'>{_pct(aa, sign=True)}</div></div>")
        parts.append(f"<div><div class='k'>NIFTY Same Windows</div><div class='v'>{_pct(nn, sign=True)}</div></div>")
        parts.append(f"<div><div class='k'>Excess α</div><div class='v' style='color:{'var(--pos)' if ea and ea>0.02 else 'var(--neg)' if ea and ea<-0.02 else 'var(--warn)'}'>{_pct(ea, sign=True)}</div></div>")
        parts.append(f"<div><div class='k'>Beat NIFTY</div><div class='v'>{_pct(p.get('pct_beat_nifty'))}</div><div class='s'>{p.get('n_beat_nifty')}/{p.get('n_trades_benchmarked')}</div></div>")
        parts.append(f"<div><div class='k'>Verdict</div><div class='v' style='font-family:ui-monospace,monospace;font-size:13px'>{p.get('verdict','—')}</div></div>")
        parts.append("</div>")
    else:
        parts.append("<p>No benchmark data available.</p>")

    # Top 10 Opportunities
    parts.append("<h2>Top 10 Opportunities <span class='tag live'>Live</span></h2>")
    parts.append("<table><thead><tr>"
                    "<th>#</th><th>Ticker</th><th>Action</th><th>Score</th>"
                    "<th>CMP</th><th>Target</th><th>Stop</th><th>Hold</th>"
                    "<th>α vs NIFTY</th></tr></thead><tbody>")
    for i, r in enumerate(ctx["top10"], 1):
        alpha = (r.get("_bm") or {}).get("excess_alpha_avg")
        alpha_cls = "pos" if alpha and alpha > 0.02 else "neg" if alpha and alpha < -0.02 else ""
        parts.append(f"<tr><td>{i}</td>"
                        f"<td><b>{r['ticker']}</b></td>"
                        f"<td>{_pill(r.get('recommendation'))}</td>"
                        f"<td>{r.get('_ids') or '—'}</td>"
                        f"<td>{_price(r.get('_cmp'))}</td>"
                        f"<td class='pos'>{_price(r.get('_target_1'))}</td>"
                        f"<td class='neg'>{_price(r.get('_stop'))}</td>"
                        f"<td>{r.get('_hold_days') or '—'}d</td>"
                        f"<td class='{alpha_cls}'>{_pct(alpha, sign=True) if alpha is not None else '—'}</td></tr>")
    parts.append("</tbody></table>")

    # Recommendation Lifecycle Scoreboard
    parts.append("<h2>Recommendation Lifecycle Scoreboard <span class='tag live'>Live</span></h2>")
    parts.append("<table><thead><tr>"
                    "<th>#</th><th>Ticker</th><th>Sector</th><th>Age</th>"
                    "<th>Entry</th><th>D+1</th><th>D+3</th><th>D+5</th><th>D+10</th>"
                    "<th>Current</th><th>MaxGain</th><th>MaxDD</th><th>Status</th>"
                    "</tr></thead><tbody>")
    for i, r in enumerate(ctx.get("scoreboard") or [], 1):
        def _cell(v):
            if v is None: return "<td>—</td>"
            cls = "pos" if v > 0 else "neg" if v < 0 else ""
            return f"<td class='{cls}'>{_pct(v, sign=True)}</td>"
        age = f"{r.get('age_days')}/{r.get('expected_hold') or '—'}d" if r.get('age_days') is not None else "—"
        parts.append(
            f"<tr><td>{i}</td>"
            f"<td><b>{r['ticker']}</b></td>"
            f"<td>{r.get('sector', '—')}</td>"
            f"<td>{age}</td>"
            f"<td>{_price(r.get('entry_price'))}</td>"
            f"{_cell(r.get('d1'))}{_cell(r.get('d3'))}{_cell(r.get('d5'))}{_cell(r.get('d10'))}"
            f"{_cell(r.get('current_return'))}{_cell(r.get('max_gain'))}{_cell(r.get('max_dd'))}"
            f"<td>{r.get('status', '—')}</td></tr>"
        )
    parts.append("</tbody></table>")
    parts.append("<p style='color:var(--type-3); font-size: 11px; margin-top: 4px;'>"
                    "Day+N columns are trading-day forward returns from <code>first_seen_date</code>. "
                    "Populate as archive matures — expect empty until Day 10+ of live operation.</p>")

    # Overnight changes
    parts.append("<h2>Overnight Changes</h2>")
    if ctx["changes"]:
        parts.append("<table><thead><tr>"
                        "<th>Ticker</th><th>Kind</th><th>Y'day → Today</th><th>Reason</th></tr></thead><tbody>")
        for c in ctx["changes"]:
            parts.append(f"<tr><td><b>{c.get('ticker')}</b></td>"
                            f"<td>{(c.get('kind','') or '').replace('_',' ')}</td>"
                            f"<td>{c.get('yesterday_action') or '—'} → {c.get('today_action') or '—'}</td>"
                            f"<td style='color:var(--type-2);font-family:ui-serif,serif;'>{c.get('reason','')}</td></tr>")
        parts.append("</tbody></table>")
    else:
        parts.append("<p style='color:var(--type-2)'>No material changes overnight.</p>")

    # Risk Alerts
    if ctx["risk_alerts"]:
        parts.append("<h2>Risk Alerts</h2><ul>")
        for a in ctx["risk_alerts"]:
            parts.append(f"<li><b>{a['severity']}</b> · <code>{a['ticker']}</code> — {a['reason']}</li>")
        parts.append("</ul>")

    # Subsystem Attribution
    parts.append("<h2>Subsystem Attribution <span class='tag bt'>Backtester</span></h2>")
    if tc or td:
        parts.append("<div class='kpi'>")
        if tc:
            parts.append(f"<div><div class='k'>Alpha Creator</div>"
                            f"<div class='v' style='color:var(--pos);font-family:ui-monospace,monospace;font-size:14px'>{tc['subsystem']}</div>"
                            f"<div class='s'>α {_pct(tc['alpha_created'], sign=True)} · lift {tc['lift']:.2f}</div></div>")
        if td:
            parts.append(f"<div><div class='k'>Alpha Destroyer</div>"
                            f"<div class='v' style='color:var(--neg);font-family:ui-monospace,monospace;font-size:14px'>{td['subsystem']}</div>"
                            f"<div class='s'>α {_pct(td['alpha_created'], sign=True)} · lift {td['lift']:.2f}</div></div>")
        parts.append("</div>")

    # Missed Opportunities
    if ctx["n_missed"]:
        parts.append("<h2>Missed Opportunities <span class='tag live'>Live</span></h2>")
        parts.append(f"<p>Detected <b>{ctx['n_missed']}</b> events where a ticker moved > threshold but was not recommended.</p>")
        if ctx["missed_examples"]:
            parts.append("<ul>")
            for m in ctx["missed_examples"]:
                parts.append(f"<li><code>{m.get('ticker')}</code> on {m.get('anchor_date')} — "
                                f"{m.get('forward_days')}-day return "
                                f"<b class='pos'>{_pct(m.get('forward_return'), sign=True)}</b> · "
                                f"blocked by <code>{m.get('blocking_reason')}</code></li>")
            parts.append("</ul>")

    # Archive maturation
    parts.append("<h2>Archive Maturation</h2>")
    pct_maturity = min(100, int((ctx["n_archive_days"] / 30) * 100))
    parts.append(f"<div style='height:8px;background:var(--rule);border-radius:4px;overflow:hidden;'>"
                    f"<div style='height:100%;width:{pct_maturity}%;background:var(--accent);'></div></div>")
    parts.append(f"<div style='font-family:ui-monospace,monospace;font-size:11px;color:var(--type-3);margin-top:6px;letter-spacing:0.04em;'>"
                    f"<b>{ctx['n_archive_days']} / 30</b> archive days · "
                    f"<b>{ctx['days_remaining']}</b> trading days until Alpha Signature v2.1 gate unlocks</div>")

    # Action Items
    parts.append("<h2>Action Items</h2>")
    action_items: list[str] = []
    new_strong = [c for c in ctx["changes"] if c.get("kind") == "NEW" and c.get("today_action") == "Strong-Buy"]
    for c in new_strong[:5]:
        action_items.append(f"Consider entering <code>{c.get('ticker')}</code> — new Strong-Buy overnight")
    for c in [c for c in ctx["changes"] if c.get("kind") == "TARGET_HIT"][:5]:
        action_items.append(f"Review <code>{c.get('ticker')}</code> — target achieved; consider partial exit")
    for c in [c for c in ctx["changes"] if c.get("kind") == "STOP_HIT"][:5]:
        action_items.append(f"Exit <code>{c.get('ticker')}</code> — stop-loss triggered")
    if not action_items:
        action_items.append("No immediate actions required today.")
    parts.append("<ul>")
    for a in action_items:
        parts.append(f"<li>{a}</li>")
    parts.append("</ul>")

    parts.append("<footer>")
    parts.append(f"Generated {ctx['date_ist']} · AEGIS v2 (LOCKED) · <br>")
    parts.append("Provenance: recommendations.json · investment_intelligence.json · benchmark.json · "
                    "decision_attribution.json · decision_center_today.json · winner_genome.json · "
                    "recommendation_lifecycle.json · missed_opportunities.json")
    parts.append("</footer></body></html>")

    return "\n".join(parts)


# ─── Main entrypoint ──────────────────────────────────────────────

def main() -> int:
    t0 = time.time()
    print("=" * 68)
    print("  MORNING RESEARCH REPORT v1.0 · daily digest")
    print("=" * 68)

    ctx = build_report()
    md   = render_markdown(ctx)
    html = render_html(ctx)

    date = ctx["date_short"]
    md_path   = REPORTS / f"morning_{date}.md"
    html_path = REPORTS / f"morning_{date}.html"
    latest_md_path   = REPORTS / "morning_latest.md"
    latest_html_path = REPORTS / "morning_latest.html"

    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    latest_md_path.write_text(md, encoding="utf-8")
    latest_html_path.write_text(html, encoding="utf-8")

    print(f"  recommendations:    {ctx['portfolio_summary']['n_recommendations']}")
    print(f"  top10 rendered:     {len(ctx['top10'])}")
    print(f"  overnight changes:  {len(ctx['changes'])}")
    print(f"  risk alerts:        {len(ctx['risk_alerts'])}")
    print(f"  missed events:      {ctx['n_missed']}")
    print(f"  archive days:       {ctx['n_archive_days']} / 30")
    print()
    print(f"  MD  → {md_path.relative_to(_ROOT)}  ({md_path.stat().st_size / 1024:.1f} KB)")
    print(f"  HTML→ {html_path.relative_to(_ROOT)} ({html_path.stat().st_size / 1024:.1f} KB)")
    print(f"  latest→ reports/morning_latest.{{md,html}}")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
