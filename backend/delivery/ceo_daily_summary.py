# backend/delivery/ceo_daily_summary.py
"""AEGIS · Sprint M · Part 19 · CEO Daily Summary.

CEO directive 2026-08-25: "Every daily run should produce · NEW /
EXISTING / RISK / LOSSES / WINNERS / ROTATIONS / LEARNING · one-liner
per section · do not repeat unchanged stocks merely to fill space".

Produces a 5-section markdown digest for the daily CEO glance:

  🆕 NEW           · top 3-5 NEW opportunities today
  ✅ EXISTING      · top changes only (not full list)
  ⚠  RISK          · top 3 · alerts
  ❌ LOSSES        · what went wrong yesterday
  🏆 WINNERS       · what worked

Optional additions:
  🔄 ROTATIONS     · replace X with Y suggestions
  📚 LEARNING      · one-liner from Distillation (Sprint L when ready)

Consumes: opportunity_engine · attribution_matrix · win_attribution ·
          loss_attribution_v2 · loss_avoidance_guard · aegis_alpha_report

Locks preserved: reads only · never writes to R1/R2 · never touches
Excel format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path


SCHEMA_FINGERPRINT = "aegis.ceo_daily_summary.v1.20260825"


@dataclass
class DailySummary:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    data_state: str = "?"
    lifecycle_verdict: str = "?"
    new: list = field(default_factory=list)          # top NEW today
    existing_changes: list = field(default_factory=list)
    risk_alerts: list = field(default_factory=list)
    losses: list = field(default_factory=list)       # yesterday
    winners: list = field(default_factory=list)      # yesterday
    rotations: list = field(default_factory=list)
    learning_line: str = ""


def _load(root: Path, subpath: str) -> dict:
    p = root / subpath
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute(root: Path, market: str) -> DailySummary:
    mkt = market.lower()
    s = DailySummary(
        market=mkt,
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    # data + lifecycle state
    oe = _load(root, f"reports/context/opportunity_engine_{mkt}.json")
    ls = _load(root, f"reports/context/lifecycle_stabilization_{mkt}.json")
    s.data_state = oe.get("data_state", "?")
    s.lifecycle_verdict = ls.get("verdict", "?")

    # NEW · from opportunity_engine detail
    detail = oe.get("detail", [])
    for r in detail:
        if r.get("opportunity_state") == "NEW":
            s.new.append({
                "ticker": r.get("ticker"),
                "runner": r.get("runner"),
                "reason": r.get("reason", ""),
            })
    s.new = s.new[:5]

    # EXISTING · only entries added today
    for tk in (oe.get("added_today") or [])[:5]:
        s.existing_changes.append({"ticker": tk.split("|")[0],
                                   "runner": tk.split("|")[1] if "|" in tk else ""})

    # RISK · from loss_avoidance_guard EXIT/TIGHTEN verdicts
    la = _load(root, f"reports/context/loss_avoidance_{mkt}.json")
    for v in (la.get("verdicts") or []):
        if v.get("verdict") in ("EXIT", "TIGHTEN_STOP"):
            s.risk_alerts.append({
                "ticker": v.get("ticker"),
                "verdict": v.get("verdict"),
                "pnl_pct": v.get("pnl_pct"),
                "signal": (v.get("signals_fired") or [""])[0],
            })
    s.risk_alerts = s.risk_alerts[:3]

    # LOSSES + WINNERS · today's closed cohort from loss/win_patterns
    _lp = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    _wp = _load(root, f"reports/research/win_patterns_{mkt}.json")
    # yesterday's cohort · exits within last 2 days
    from datetime import timedelta
    _y_start = (date.today() - timedelta(days=2)).isoformat()
    for e in (_lp.get("exits") or []):
        if e.get("exit_date", "") < _y_start: continue
        if e.get("is_win"): continue
        s.losses.append({
            "ticker": e.get("ticker"), "pnl_pct": e.get("pnl_pct"),
            "category": e.get("category"),
        })
    for w in (_wp.get("winners") or []):
        if w.get("exit_date", "") < _y_start: continue
        s.winners.append({
            "ticker": w.get("ticker"), "pnl_pct": w.get("pnl_pct"),
            "pattern": w.get("pattern"),
        })
    s.losses = s.losses[:5]
    s.winners = s.winners[:5]

    # ROTATIONS · from rotation_outcomes / rotation_ledger
    _rot = _load(root, "reports/research/rotation_ledger.jsonl")
    # placeholder · rotation_outcomes not standardized yet
    s.rotations = []

    # LEARNING · one-liner from top research ticket
    try:
        from backend.research.research_ticket import load_top_tickets
        top = load_top_tickets(root, n=1)
        if top:
            s.learning_line = (f"top ticket · {top[0].get('id')} · "
                               f"impact {top[0].get('impact_score')} · "
                               f"{top[0].get('status')}")
    except Exception:
        pass

    return s


def render_markdown(s: DailySummary) -> str:
    lines = [
        f"# 🎯 AEGIS · CEO DAILY · {s.market.upper()} · {s.asof}",
        "",
        f"**Data state**: {s.data_state}  ·  **Lifecycle**: {s.lifecycle_verdict}",
        "",
        "## 🆕 NEW opportunities",
    ]
    if not s.new:
        lines.append("- (no new opportunities today)")
    for n in s.new:
        lines.append(f"- **{n.get('ticker')}** · {n.get('runner')} · {n.get('reason','')}")
    lines.append("")
    lines.append("## ✅ EXISTING · changes today")
    if not s.existing_changes:
        lines.append("- (no changes vs yesterday's active set)")
    for e in s.existing_changes:
        lines.append(f"- {e.get('ticker')} · {e.get('runner')}")
    lines.append("")
    lines.append("## ⚠  RISK alerts (top 3)")
    if not s.risk_alerts:
        lines.append("- (no risk-alert triggers today)")
    for r in s.risk_alerts:
        lines.append(f"- **{r.get('ticker')}** · {r.get('verdict')} · "
                     f"P&L {r.get('pnl_pct')}% · {r.get('signal')}")
    lines.append("")
    lines.append("## ❌ LOSSES (yesterday cohort)")
    if not s.losses:
        lines.append("- (no losing exits)")
    for l in s.losses:
        lines.append(f"- {l.get('ticker')} · {l.get('pnl_pct')}% · "
                     f"category {l.get('category')}")
    lines.append("")
    lines.append("## 🏆 WINNERS (yesterday cohort)")
    if not s.winners:
        lines.append("- (no winning exits)")
    for w in s.winners:
        lines.append(f"- {w.get('ticker')} · +{w.get('pnl_pct')}% · "
                     f"pattern {w.get('pattern')}")
    lines.append("")
    if s.learning_line:
        lines.append("## 📚 LEARNING")
        lines.append(f"- {s.learning_line}")
    return "\n".join(lines)


def emit(root: Path, s: DailySummary) -> Path:
    p = (root / "reports" / "research"
         / f"ceo_daily_summary_{s.market}.md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_markdown(s), encoding="utf-8")
    # JSON too
    jp = p.parent / f"ceo_daily_summary_{s.market}.json"
    jp.write_text(json.dumps(asdict(s), indent=2, default=str,
                             ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(s: DailySummary) -> str:
    return (f"ceo_daily_summary · state={s.data_state} · "
            f"NEW={len(s.new)} · RISK={len(s.risk_alerts)} · "
            f"LOSSES={len(s.losses)} · WINNERS={len(s.winners)}")
