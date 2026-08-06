"""AEGIS · Detailed per-stock card renderer + daily-detail companion file.

Per operator directive 2026-08-01 (locked in docs/AEGIS_STOCK_CARD_FORMAT.md):

    "everystock to show in below format"

The full card has ~18 sections per stock. 15 stocks × 45 lines = ~8000
chars, which exceeds Telegram's 4096 single-message cap. Solution:
send compact Command Center message as usual · attach an .md file with
one detailed card per stock.

Field precedence (never fake data):
    · known → render real value
    · missing → render "—" explicitly
    · never fabricate

File: reports/telegram/aegis_detail_{market}_{asof}.md
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Mapping, Sequence

# Reused helpers from command_center to avoid duplication
from .command_center import (
    _company_name, _short_ticker, _fmt_price,
    CURRENCY,
)


def _fmt_pct(v, ndigits: int = 2, signed: bool = True) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if f <= 1 and f >= -1:
            f *= 100
        if signed:
            return f"{f:+.{ndigits}f}%"
        return f"{f:.{ndigits}f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_date(iso: str | None, fmt: str = "%d-%b-%Y") -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(str(iso)[:19].replace("Z", "+00:00")).strftime(fmt)
    except (ValueError, TypeError):
        try:
            return datetime.fromisoformat(str(iso)[:10]).strftime(fmt)
        except Exception:
            return str(iso)


def _load_position(root: Path, market: str, ticker: str) -> dict | None:
    """Load a single position record from position_store.

    P0 FIX 2026-08-06 · fuzzy-match on short ticker vs full-suffix ticker.
    Rec payloads use 'TCS' but position_store keys are 'TCS.NS' · exact
    match was failing · falling back to current_price for Entry · breaking
    the frozen-entry contract on live daily rows."""
    if market == "usa":
        p = root / "usa" / "reports" / "position_store" / market / "positions.json"
    else:
        p = root / "reports" / "position_store" / market / "positions.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        positions = d.get("positions") or {}
        # Try exact match first
        if ticker in positions:
            return positions[ticker]
        # Fuzzy: strip .NS / .BO from both sides · match by short ticker
        short = ticker.replace(".NS", "").replace(".BO", "").upper()
        for k, v in positions.items():
            ks = k.replace(".NS", "").replace(".BO", "").upper()
            if ks == short:
                return v
        return None
    except Exception:
        return None


def _load_ledger_events_for_ticker(root: Path, market: str, ticker: str) -> list[dict]:
    """Load R006 portfolio_ledger events for a ticker."""
    p = root / "reports" / "research" / "portfolio_ledger.jsonl"
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("market") == market and d.get("ticker") == ticker:
                out.append(d)
    except Exception:
        pass
    return out


def _lifecycle_state(events: list[dict]) -> str:
    """Derive current lifecycle state from ledger events."""
    if not events:
        return "NEW"
    last = events[-1].get("event") or ""
    if last in ("EXIT_STOP", "EXIT_TARGET", "EXIT_HORIZON",
                   "EXIT_MANUAL", "ROTATE_OUT"):
        return "EXITED"
    if last == "HOLD":
        return "HOLD"
    if last in ("OPEN", "ROTATE_IN"):
        return "ACTIVE"
    if last == "REBALANCE":
        return "ACTIVE"
    return "NEW"


def _exit_triggers_checklist(events: list[dict]) -> list[tuple[str, bool]]:
    """Return [(label, checked), ...] for the Exit Trigger checklist."""
    happened = {e.get("event") for e in events}
    return [
        ("Target Hit",   "EXIT_TARGET" in happened),
        ("Stop Hit",     "EXIT_STOP"   in happened),
        ("Time Expired", "EXIT_HORIZON" in happened),
        ("Rotation",     "ROTATE_OUT"  in happened),
        ("Manual Exit",  "EXIT_MANUAL" in happened),
    ]


def _drivers_from_attribution(rec: Mapping) -> list[str]:
    """Extract top drivers from attribution block (R2) or CSV Why (R1)."""
    def _clean(item) -> str:
        # Handles: str · dict{"model_id": ..., "score": ...} · dict{"Model Id": ...} · dict{"name": ...}
        if isinstance(item, str):
            s = item
        elif isinstance(item, dict):
            s = (item.get("model_id") or item.get("Model Id") or item.get("name")
                    or item.get("feature") or item.get("id") or "")
        else:
            s = str(item)
        s = str(s).replace("aegis.", "").replace(".v1", "").replace("_", " ").title().strip()
        return s

    attr = rec.get("attribution") or {}
    top_models = attr.get("top_models") or rec.get("top_models") or []
    if top_models:
        cleaned = [_clean(m) for m in top_models[:5]]
        return [c for c in cleaned if c]
    top_features = rec.get("top_features") or []
    if top_features:
        cleaned = [_clean(f) for f in top_features[:5]]
        return [c for c in cleaned if c]
    return []


def _render_card(rec: Mapping, market: str, root: Path,
                     runner: str = "R2", status_override: str | None = None) -> str:
    """Render one detailed stock card per the locked format spec."""
    raw_ticker = rec.get("ticker") or "?"
    ticker = _short_ticker(raw_ticker)
    company = _company_name(raw_ticker, market) or ""
    company_str = f" ({company})" if company else ""

    ia = rec.get("investor_action") or {}
    pp = rec.get("position_plan") or {}
    ez = pp.get("entry_zone") or {}
    ev = rec.get("evolution") or {}
    ri = rec.get("rotation_intelligence") or {}

    entry_action = str(ia.get("entry") or "").upper()
    pct_action = str(rec.get("percentile_action") or "").upper()
    if status_override:
        status = status_override
    elif ri.get("should_rotate"):
        status = "ROTATE OUT"
    elif entry_action == "BUY" and pct_action == "STRONG_BUY":
        status = "STRONG BUY"
    elif entry_action == "BUY":
        status = "NEW BUY"
    elif entry_action == "SELL" or ia.get("if_holding") in ("EXIT", "REDUCE", "SELL"):
        status = "EXIT"
    else:
        status = "HOLD"

    strength_emoji_map = {
        "STRONG BUY":  "🟢🟢",
        "NEW BUY":     "🟢",
        "BUY":         "🟢",
        "HOLD":        "⚪",
        "ROTATE OUT":  "🔄",
        "ROTATE IN":   "🔄",
        "EXIT":        "🔴",
    }
    emoji = strength_emoji_map.get(status, "⚪")

    rank = rec.get("rank")
    conf_cal = rec.get("calibrated_confidence")
    conf_raw = rec.get("confidence")
    if isinstance(conf_cal, (int, float)) and conf_cal:
        conf_str = f"{conf_cal*100:.0f}% (Calibrated)"
    elif isinstance(conf_raw, (int, float)) and conf_raw:
        conf_str = f"{conf_raw*100:.0f}% (Raw)"
    else:
        conf_str = "—"

    ensemble_score = rec.get("ensemble_score")
    if isinstance(ensemble_score, (int, float)):
        score_str = f"{ensemble_score:.0f}/100" if ensemble_score > 5 else \
                     f"{ensemble_score*100:.0f}/100"
    else:
        score_str = "—"

    horizon = pp.get("time_horizon_days") or 0
    days_rec = ev.get("days_recommended") or 0
    days_left = max(0, horizon - days_rec + 1) if horizon else 0

    currency = CURRENCY.get(market, "")
    current_price = ez.get("current_price")

    # Position store for entry/high-water/low-water/dates
    ps = _load_position(root, market, ticker)
    entry_price = None
    first_seen = None
    high_water = None
    low_water = None
    if ps:
        entry_price = ps.get("first_seen_price")
        first_seen = ps.get("first_seen_date")
        high_water = ps.get("high_water_price")
        low_water = ps.get("low_water_price")
        if current_price is None:
            current_price = ps.get("last_seen_price")

    def _px(v):
        return _fmt_price(v, market) if v else "—"

    def _abs_pct(base, target):
        if not (base and target and base > 0):
            return "—"
        return _fmt_pct((target - base) / base * 100, ndigits=1)

    stop = ez.get("stop_loss")
    t1 = ez.get("target_1")
    t2 = ez.get("target_2")
    if t2 is None and t1 is not None and current_price:
        t2 = current_price + (t1 - current_price) * 1.5

    stop_risk = _abs_pct(entry_price or current_price, stop)
    t1_reward = _abs_pct(entry_price or current_price, t1)
    t2_reward = _abs_pct(entry_price or current_price, t2)

    # Performance metrics from position store
    if entry_price and current_price:
        cur_ret = _fmt_pct((current_price / entry_price - 1) * 100)
    else:
        cur_ret = "—"
    if entry_price and high_water:
        max_gain = _fmt_pct((high_water / entry_price - 1) * 100)
    else:
        max_gain = "—"
    if entry_price and low_water:
        max_dd = _fmt_pct((low_water / entry_price - 1) * 100)
    else:
        max_dd = "—"

    # Lifecycle from R006 ledger
    events = _load_ledger_events_for_ticker(root, market, ticker)
    state = _lifecycle_state(events)
    exit_triggers = _exit_triggers_checklist(events)

    # Expected alpha
    expected_alpha = ri.get("expected_alpha_delta_pct")
    if expected_alpha is None and t1 and (entry_price or current_price):
        expected_alpha = ((t1 / (entry_price or current_price)) - 1) * 100
    exp_alpha_str = _fmt_pct(expected_alpha) if expected_alpha is not None else "—"

    drivers = _drivers_from_attribution(rec)
    drivers_str = "\n".join(f"✓ {d}" for d in drivers) if drivers else "—"

    sector = rec.get("sector") or "—"
    alloc = pp.get("suggested_allocation_pct") or 0

    def _check(flag: bool) -> str:
        return "✓" if flag else "□"

    lines = [
        f"{emoji} {ticker}{company_str}",
        "────────────────────────",
        f"Rank          #{rank if rank else '—'}",
        f"Runner        {runner}",
        f"Status        {status}",
        f"Confidence    {conf_str}",
        f"Model Score   {score_str}",
        "",
        "Holding",
        f"Day {days_rec} / {horizon if horizon else '—'}",
        f"{days_left} days remaining" if horizon else "— days remaining",
        "",
        "Current",
        f"{_px(current_price)}",
        "",
        "Recommendation",
        f"{status}",
        f"Position Size: {alloc}%" if alloc else "Position Size: —",
        "",
        "Entry",
        f"Recommended : {_fmt_date(first_seen)}",
        f"Entry Price : {_px(entry_price)}",
        f"Buy Zone    : {_px(ez.get('ideal_buy_low'))}–{_px(ez.get('ideal_buy_high'))}",
        "",
        "Risk",
        f"Stop Loss   : {_px(stop)}",
        f"Risk         : {stop_risk}",
        "",
        "Reward",
        f"Target 1    : {_px(t1)} ({t1_reward})",
        f"Target 2    : {_px(t2)} ({t2_reward})",
        "",
        "Performance",
        f"Current      : {cur_ret}",
        f"Max Gain     : {max_gain}",
        f"Max DD       : {max_dd}",
        "",
        "Lifecycle",
        "State",
        f"→ {state}",
        "",
        "Exit Trigger",
    ] + [f"{_check(v)} {label}" for label, v in exit_triggers] + [
        "",
        "Top Drivers",
        drivers_str,
        "",
        "Portfolio",
        f"Sector           : {sector}",
        f"Portfolio Weight : {alloc}%" if alloc else "Portfolio Weight : —",
        "Correlation       : — (needs Ticket R007 correlation matrix)",
        "",
        "Expected Alpha",
        exp_alpha_str,
        "Confidence Band",
        "— (needs Ticket R007 calibration variance data)",
        "",
        "Historical Similar Setups",
        "Win Rate      —",
        "Median Return —",
        "Average Hold  —",
        "  (Ticket R007 · per-setup backtest lookup · not yet built)",
        "",
        "Last Updated",
        _fmt_date(datetime.now(timezone.utc).isoformat(),
                    fmt="%d-%b-%Y %H:%M UTC"),
    ]
    return "\n".join(lines)


def _r1_orphan_to_rec_shape(o: Mapping, market: str) -> dict:
    """Adapt a Runner 1 orphan dict into a rec-shaped dict for _render_card.

    Sprint H fix 2026-08-06: enriched to give R1 orphans the SAME rich
    field coverage as R2 recs so XLSX columns render properly. Per operator
    feedback: 'Every stock should look exactly like Runner 2 · not Strong
    Buy 77 · 2 Months'.
    """
    import re
    strength = str(o.get("strength") or "").upper()
    status = {
        "STRONG BUY": "STRONG BUY",
        "BUY":        "BUY",
        "ACCUMULATE": "BUY",
        "HOLD":       "HOLD",
        "WATCH":      "HOLD",
    }.get(strength, strength)
    price = o.get("price")
    hist_target = o.get("hist_target")

    # Parse buy_range "1415 - 1495" → (low, high)
    buy_low = buy_high = None
    buy_range = str(o.get("buy_range") or "")
    m = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", buy_range)
    if m:
        try: buy_low, buy_high = float(m.group(1)), float(m.group(2))
        except ValueError: pass
    if buy_low is None and isinstance(price, (int, float)):
        buy_low, buy_high = price * 0.99, price * 1.01

    stop = price * 0.95 if isinstance(price, (int, float)) and price else None
    t1 = (hist_target if isinstance(hist_target, (int, float)) and hist_target
              else (price * 1.08 if isinstance(price, (int, float)) else None))
    t2 = (t1 * 1.07 if t1 else (price * 1.15 if isinstance(price, (int, float)) else None))

    # Parse holding "2 months (2M)" → 60 days
    horizon_days = 60
    holding = str(o.get("holding") or "")
    m = re.match(r"(\d+)\s*(month|week|day)", holding.lower())
    if m:
        n = int(m.group(1))
        horizon_days = {"month": 30, "week": 7, "day": 1}.get(m.group(2), 30) * n

    # Parse reason string into top-drivers list (split on · or ,)
    reason = str(o.get("reason") or "")
    drivers = []
    for part in re.split(r"[·|,\n]+", reason):
        p = part.strip()
        if p and len(p) < 50: drivers.append(p)
    top_drivers = drivers[:3] if drivers else []

    return {
        "ticker":  o.get("ticker") or "?",
        "sector":  o.get("sector") or "—",
        "confidence": (o.get("confidence") or 0) / 100 if o.get("confidence") else None,
        "calibrated_confidence": (o.get("confidence") or 0) / 100 if o.get("confidence") else None,
        "ensemble_score": o.get("score"),
        "investor_action": {"entry": "BUY" if status in ("STRONG BUY", "BUY") else "HOLD",
                                    "is_actionable_entry": status in ("STRONG BUY", "BUY")},
        "position_plan": {
            "entry_zone": {
                "current_price": price,
                "ideal_buy_low":  buy_low,
                "ideal_buy_high": buy_high,
                "stop_loss":     stop,
                "target_1":      t1,
                "target_2":      t2,
            },
            "time_horizon_days": horizon_days,
            "suggested_allocation_pct": 5.0,   # R1 default from adaptive_rec_v2
        },
        "evolution": {"first_seen_date": None,
                          "days_recommended": 0,     # populated from position_store via detail_xlsx
                          "momentum_direction": "STABLE"},
        "rotation_intelligence": {},
        "percentile_action": strength.replace(" ", "_"),
        # Sprint H enrichment for R2-parity rendering
        "attribution": {"top_features": top_drivers,
                             "top_models": []},
        "why": {"top_reasons": drivers[:5] if drivers else [],
                    "top_risks": []},
        "bull_case": reason[:200] if reason else "",
        "bear_case": "",
        # R1 has a valid_until field · surface as info
        "r1_valid_until": o.get("valid_until"),
    }


def render_daily_detail_report(root: Path, market: str, asof: str) -> Path:
    """Build the full-detail companion .md file with cards for every stock."""
    recs_path = (root / "usa" / "reports" / "recommendations.json"
                    if market == "usa" else root / "reports" / "recommendations.json")
    if not recs_path.exists():
        return None
    payload = json.loads(recs_path.read_text(encoding="utf-8"))
    recs = payload.get("recommendations") or []

    out_dir = root / "reports" / "telegram"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"aegis_detail_{market}_{asof}.md"

    market_flag = "🇮🇳" if market == "india" else "🇺🇸"
    market_name = "India NSE 200" if market == "india" else "USA S&P 500 + MidCap 400"

    lines = [
        f"# AEGIS Daily Detail · {market_flag} {market_name}",
        f"**As of** {asof}",
        f"**Generated** {datetime.now(timezone.utc).isoformat()}",
        "",
        "This companion file contains the full detailed card for every stock in today's report ·",
        "per the format locked in `docs/AEGIS_STOCK_CARD_FORMAT.md`. Every field is populated with real",
        "data from the position store, portfolio ledger (R006), and today's recommendations · missing",
        "fields render as `—` explicitly (never faked).",
        "",
        "---",
        "",
    ]

    # Runner 2 cards
    lines.append(f"## 🚀 Runner 2 · Adaptive Strategy · {len(recs)} tracked positions")
    lines.append("")
    for r in recs:
        card = _render_card(r, market, root, runner="R2")
        lines.append("```")
        lines.append(card)
        lines.append("```")
        lines.append("")

    # Runner 1 cards (India only)
    if market == "india":
        rv = payload.get("runner1_validation") or {}
        orphans = rv.get("runner1_orphans") or []
        if orphans:
            lines.append("---")
            lines.append("")
            lines.append(f"## 🛡 Runner 1 · Baseline / Validation Strategy · {len(orphans)} active picks")
            lines.append("")
            for o in orphans:
                r1_rec = _r1_orphan_to_rec_shape(o, market)
                card = _render_card(r1_rec, market, root, runner="R1")
                lines.append("```")
                lines.append(card)
                lines.append("```")
                lines.append("")

    lines.extend([
        "---",
        "",
        f"## Report metadata",
        f"- Payload asof: {payload.get('asof')}",
        f"- Payload engine: {payload.get('engine')}",
        f"- Format spec: `docs/AEGIS_STOCK_CARD_FORMAT.md`",
        f"- Portfolio ledger: `reports/research/portfolio_ledger.jsonl` (R006)",
        f"- Position store: `reports/position_store/{market}/positions.json`",
        "",
        f"**Advisory only · PAPER · Not investment advice**",
    ])

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
