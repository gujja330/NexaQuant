"""Command Center renderer · single crisp Telegram message per market.

Consumes the enriched `reports/recommendations.json` (or USA equivalent)
produced by cycles 3-4:
  - ceo_summary          → top of message (30-second glance)
  - investor_action      → Entry / If-Holding decisions per rec
  - rotation_intelligence → ROTATE X → Y with expected alpha
  - evolution            → what changed since previous snapshot
  - position_plan        → entry zone, stop, targets, allocation, horizon
  - why                  → top reasons + top risks

Design principles:
  · ONE message per market (not two chunks)
  · ~1800 char budget · full detail in dashboard/HTML
  · No HTML tags — plain text with Markdown-safe formatting
  · ASCII-safe arrows (->) · emojis for section visual hierarchy
  · CEO one-liner FIRST (the operator's "what should I do today")
  · Rotation calls next (highest institutional-value information)
  · Actionable entries with target/stop
  · Actionable exits with reason class (not just "rebalance")
  · Feedback loop: yesterday's evolution deltas if present

Article 101.2 compliant · pure rendering · zero new analytics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.delivery.telegram.command_center.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.delivery.telegram.command_center.v1"

# Telegram hard cap = 4096 · used as ultimate ceiling.
TELEGRAM_HARD_CAP = 4096
# Fallback default if configs/telegram_budget.json is missing or unreadable.
_FALLBACK_BUDGET = 4076
SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━"

# Cache to avoid re-reading budget config on every render call.
_BUDGET_CACHE: dict | None = None


def resolve_budget(message_kind: str = "command_center",
                      override: int | None = None) -> int:
    """Return the investor-configured budget for a message type.

    Precedence (highest wins):
      1. Explicit `override` arg passed by caller
      2. configs/telegram_budget.json → per_message[message_kind]
      3. configs/telegram_budget.json → global_default
      4. _FALLBACK_BUDGET

    Never exceeds TELEGRAM_HARD_CAP. Budget is fully investor-controlled —
    edit configs/telegram_budget.json to adjust.
    """
    if override is not None and override > 0:
        return min(int(override), TELEGRAM_HARD_CAP)
    global _BUDGET_CACHE
    if _BUDGET_CACHE is None:
        _BUDGET_CACHE = _load_budget_config()
    cfg = _BUDGET_CACHE or {}
    per = (cfg.get("per_message") or {}).get(message_kind)
    if isinstance(per, (int, float)) and per > 0:
        return min(int(per), TELEGRAM_HARD_CAP)
    default = cfg.get("global_default")
    if isinstance(default, (int, float)) and default > 0:
        return min(int(default), TELEGRAM_HARD_CAP)
    return _FALLBACK_BUDGET


def _load_budget_config() -> dict:
    p = Path("configs/telegram_budget.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def reload_budget_config() -> None:
    """Force reload of budget config · call after operator edits the file."""
    global _BUDGET_CACHE
    _BUDGET_CACHE = None


# Backwards-compat constant · anything importing BUDGET_CHARS still works
# but the value is now resolved dynamically from investor config on first
# read rather than being frozen at module load.
def _budget_chars() -> int:
    return resolve_budget("command_center")


class _LazyBudget(int):
    """int subclass that re-resolves from config on any arithmetic use."""
    def __new__(cls):
        return int.__new__(cls, resolve_budget("command_center"))

BUDGET_CHARS = _LazyBudget()

# Currency symbols per market — plain-ASCII fallbacks used because
# Telegram Markdown mode + Windows CI cp1252 both stumble on some Unicode.
CURRENCY = {"india": "Rs", "usa": "$"}


def _fmt_price(v, market: str) -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    sym = CURRENCY.get(market, "")
    if f >= 1000:
        return f"{sym}{f:,.0f}"
    if f >= 100:
        return f"{sym}{f:.0f}"
    return f"{sym}{f:.2f}"


def _fmt_pct(v, ndigits: int = 1) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):+.{ndigits}f}%"
    except (TypeError, ValueError):
        return "-"


def _short_ticker(t: str) -> str:
    """Strip .NS / .BO suffixes to save chars on India tickers."""
    if not t:
        return "?"
    return str(t).split(".", 1)[0]


# Static well-known company-name lookups per market. Used when the
# universe.json name is missing or equal to the ticker (which is the
# case for the dynamic S&P 500 + MidCap 400 universes populated by
# refresh_universe.py from Wikipedia — those come without names).
# When universe.json DOES carry names (Dow 30, NSE 200), those win.
_INDIA_COMPANY_NAMES = {
    "LUPIN": "Lupin",             "HEROMOTOCO": "Hero MotoCorp",
    "CHAMBLFERT": "Chambal Fert.", "PIDILITIND": "Pidilite",
    "SUNPHARMA": "Sun Pharma",     "ICICIBANK": "ICICI Bank",
    "TCS": "TCS",                  "HCLTECH": "HCL Tech",
    "NAUKRI": "Info Edge",         "COALINDIA": "Coal India",
    "BATAINDIA": "Bata India",     "BIOCON": "Biocon",
    "AMBER": "Amber Ent.",         "JSWENERGY": "JSW Energy",
    "PATANJALI": "Patanjali",       "TATAELXSI": "Tata Elxsi",
    "GUJGASLTD": "Gujarat Gas",    "KPITTECH": "KPIT Tech",
    "BANDHANBNK": "Bandhan Bank",  "KALYANKJIL": "Kalyan Jewel.",
    "VEDL": "Vedanta",             "ITC": "ITC",
    "GODREJIND": "Godrej Ind.",    "SONACOMS": "Sona Comstar",
    "LODHA": "Lodha",              "PNB": "Punjab Natl. Bank",
    "HINDZINC": "Hindustan Zinc",   "FORTIS": "Fortis Healthcare",
    "NTPC": "NTPC",                "IRCTC": "IRCTC",
    "TATAPOWER": "Tata Power",     "BEL": "Bharat Electronics",
    "APOLLOHOSP": "Apollo Hosp.",   "BHARTIARTL": "Bharti Airtel",
    "POWERGRID": "Power Grid",     "RELIANCE": "Reliance Ind.",
    "KOTAKBANK": "Kotak Bank",     "TATAMOTORS": "Tata Motors",
    "LTIM": "LTIMindtree",         "PEL": "Piramal Ent.",
}
_USA_COMPANY_NAMES = {
    "AAPL": "Apple",              "MSFT": "Microsoft",
    "NVDA": "NVIDIA",             "AMZN": "Amazon",
    "GOOGL": "Alphabet",          "META": "Meta Platforms",
    "TSLA": "Tesla",              "AVGO": "Broadcom",
    "JPM": "JPMorgan Chase",      "V": "Visa",
    "WMT": "Walmart",             "JNJ": "Johnson & Johnson",
    "PG": "Procter & Gamble",     "UNH": "UnitedHealth",
    "HD": "Home Depot",           "KO": "Coca-Cola",
    "MCD": "McDonald's",          "DIS": "Walt Disney",
    "CSCO": "Cisco",              "CRM": "Salesforce",
    "VZ": "Verizon",              "INTC": "Intel",
    "BA": "Boeing",               "CAT": "Caterpillar",
    "MRK": "Merck",               "NKE": "Nike",
    "IBM": "IBM",                 "GS": "Goldman Sachs",
    "AXP": "American Express",    "TRV": "Travelers",
    "MMM": "3M",                  "CVX": "Chevron",
    "AMGN": "Amgen",              "HON": "Honeywell",
    "NFLX": "Netflix",            "AMD": "AMD",
    "ADBE": "Adobe",              "TMUS": "T-Mobile",
    "CMCSA": "Comcast",           "QCOM": "Qualcomm",
    "COST": "Costco",             "PEP": "PepsiCo",
    "BLK": "BlackRock",           "SPGI": "S&P Global",
    "SBUX": "Starbucks",          "PYPL": "PayPal",
}


def _company_name(ticker: str, market: str) -> str:
    """Return best-known company short name for a ticker; empty if unknown."""
    if not ticker:
        return ""
    short = _short_ticker(ticker).upper()
    src = _INDIA_COMPANY_NAMES if market == "india" else _USA_COMPANY_NAMES
    return src.get(short, "")


def _ticker_with_name(ticker: str, market: str, width: int = 22) -> str:
    """Format `TICKER (Name)` · falls back to just ticker when name unknown."""
    short = _short_ticker(ticker)
    name = _company_name(ticker, market)
    if name:
        return f"{short} ({name})"
    return short


def _header(market: str, asof: str) -> list[str]:
    market_name = "🇮🇳 India NSE 200" if market == "india" else "🇺🇸 USA S&P 500 + MidCap 400"
    weekday = ""
    try:
        weekday = datetime.fromisoformat(asof).strftime("%a")
    except Exception:
        pass
    return [
        f"🏢 *AEGIS DAILY* · {market_name}",
        f"📅 {asof}" + (f" ({weekday})" if weekday else ""),
        SEPARATOR,
    ]


def _performance_summary(payload: Mapping, market: str) -> list[str]:
    """v3.0 FINAL Phase 6: 30-day performance block right at the top.

    Answers 'is following AEGIS working?' before ANY new recommendation.
    Uses learning.parquet (India) OR position_store history (both markets).
    """
    if market != "india":
        return []   # USA learning corpus not yet populated
    try:
        import pandas as pd
        from pathlib import Path
        lp = Path("reports/learning.parquet")
        if not lp.exists():
            return []
        df = pd.read_parquet(lp)
        # Filter to last 30 days of closed trades (by exit_date)
        try:
            df["exit_date_dt"] = pd.to_datetime(df["exit_date"], errors="coerce")
            cutoff = pd.Timestamp.today() - pd.Timedelta(days=30)
            recent = df[df["exit_date_dt"] >= cutoff]
        except Exception:
            recent = df.tail(30)   # fallback: last 30 rows

        # If recent window is empty (all closed trades > 30 days old · common
        # in a paper-only test env), fall back to since-inception summary
        # so the block is never blank.
        window_label = "30-Day"
        if len(recent) == 0:
            recent = df
            window_label = "Since inception"

        n = len(recent)
        if n == 0:
            return []
        wins = int(recent["is_winner"].sum()) if "is_winner" in recent.columns else 0
        losses = n - wins
        win_rate = round(100 * wins / n, 1) if n else 0.0
        median_ret = round(float(recent["return_pct"].median()), 2) if "return_pct" in recent.columns else 0.0
        avg_hold = round(float(recent["n_bars_held"].mean()), 1) if "n_bars_held" in recent.columns else 0.0
        # Alpha proxy · median return (per-trade)
        return [
            "",
            f"📈 *{window_label.upper()} PERFORMANCE*",
            f"   Recommendations: {n} · Wins: {wins} · Losses: {losses}",
            f"   Win Rate: {win_rate}% · Median return: {median_ret:+.2f}%",
            f"   Avg hold: {avg_hold:.0f} days · Track record since 2022-01",
        ]
    except Exception:
        return []


def _ceo_call(cs: Mapping) -> list[str]:
    """Top block — the 30-second recommendation."""
    lines = ["🎯 *CEO CALL TODAY*"]
    action = cs.get("recommended_action") or "no signal"
    lines.append(f"   {action}")
    regime = cs.get("market_regime") or "unknown"
    actionable = cs.get("actionable_count") or 0
    rotations = cs.get("rotations_count") or 0
    lines.append(f"   🌐 Market: {regime}   ·   ⚡ Actionable: {actionable}   ·   🔄 Rotations: {rotations}")
    # Article IX/X · canonical + proposed_by attribution (from Research Platform SSoT)
    proposed_by = cs.get("proposed_by")
    canonical = cs.get("canonical_status") or cs.get("canonical_engine")
    eval_day = cs.get("evaluation_day")
    if proposed_by and canonical:
        eval_str = f"  ·  📅 Day {eval_day}" if eval_day else ""
        lines.append(f"   🏛 Proposed by: *{proposed_by}*  ·  Canonical: *{canonical}*{eval_str}")
        lines.append(f"   _60d = first-decision checkpoint · 90d = final production decision_")
    # Discipline warnings surface right below the CEO call.
    warnings = cs.get("discipline_warnings") or []
    for w in warnings[:3]:
        lines.append(f"   ⚠️ {w}")
    return lines


def _rotation_calls(recs: Sequence[Mapping], market: str, max_rows: int = 4,
                       per_ticker_cap_pct: float = 6.0) -> list[str]:
    """Every rec with should_rotate=True · GROUPED by destination ticker.

    Ticket 14 fix: previously three separate BATA→LUPIN / AMBER→LUPIN /
    JSW→LUPIN lines invited an operator to allocate 3×5%=15% into LUPIN
    (violates 6% per-ticker cap). Now consolidated: ONE LUPIN destination
    line listing all sources · consolidated allocation capped at 6%.
    """
    rots = []
    for r in recs:
        ri = r.get("rotation_intelligence") or {}
        if ri.get("should_rotate"):
            rots.append({
                "from":  r.get("ticker") or "",
                "to":    ri.get("replacement_ticker") or "",
                "alpha": ri.get("expected_alpha_delta_pct") or 0,
                "edge":  ri.get("edge") or 0,
            })
    if not rots:
        return []

    # Aggregate by destination ticker
    from collections import defaultdict
    by_dest: dict[str, list[dict]] = defaultdict(list)
    for r in rots:
        by_dest[r["to"]].append(r)

    # Sort destinations by best-alpha rotation
    dest_order = sorted(by_dest.items(),
                          key=lambda kv: -max(x["alpha"] for x in kv[1]))

    # Canonical attribution · pull from any rotation_intelligence (all identical
    # since stamped in one pass by ssot _stamp_canonical)
    first_ri = next((r.get("rotation_intelligence") for r in recs
                        if r.get("rotation_intelligence", {}).get("should_rotate")), {}) or {}
    proposed_by = first_ri.get("proposed_by")
    canonical_status = first_ri.get("canonical_status")
    eval_day = first_ri.get("evaluation_day")

    lines = ["", f"🔄 *ROTATION SIGNALS ({len(rots)} rotations · {len(by_dest)} destinations)*",
             "   _Sell weaker positions, buy stronger ones — expected alpha gain_"]
    if proposed_by and canonical_status:
        eval_str = f"  ·  📅 Day {eval_day}" if eval_day else ""
        lines.append(f"   🏛 Proposed by *{proposed_by}*  ·  Canonical: *{canonical_status}*{eval_str}")

    # Portfolio-cap awareness (Ticket 14 · Portfolio Intelligence article)
    lines.append(f"   ⚖️ Allocation cap: {per_ticker_cap_pct}% per ticker (Portfolio Engine)")

    for dest, sources in dest_order[:max_rows]:
        dest_name = _ticker_with_name(dest, market)
        best_alpha = max(s["alpha"] for s in sources)
        # Rank sources by expected alpha
        sources.sort(key=lambda x: -x["alpha"])
        source_labels = []
        for s in sources[:4]:
            source_labels.append(f"{_short_ticker(s['from'])} (+{s['alpha']:.1f}%)")
        if len(sources) > 4:
            source_labels.append(f"+{len(sources) - 4} more")
        # Consolidation warning if multiple sources point to same dest
        consolidated_note = ""
        if len(sources) > 1:
            consolidated_note = (f"      ⚠️ {len(sources)} sources rotate to same target · "
                                    f"cap consolidated allocation at {per_ticker_cap_pct}%")
        lines.append(f"   🟢 *{dest_name}* — best +{best_alpha:.1f}% α")
        lines.append(f"      Sources: {', '.join(source_labels)}")
        if consolidated_note:
            lines.append(consolidated_note)

    if len(dest_order) > max_rows:
        lines.append(f"   _...+{len(dest_order) - max_rows} more destinations_")
    return lines


def _actionable_entries(recs: Sequence[Mapping], market: str,
                          max_rows: int = 4) -> list[str]:
    """Recs with is_actionable_entry — ranked by ensemble_score."""
    picks = [r for r in recs
              if (r.get("investor_action") or {}).get("is_actionable_entry")]
    picks.sort(key=lambda r: -(r.get("ensemble_score") or 0))
    if not picks:
        return []
    lines = ["", f"🟢 *NEW BUY IDEAS ({len(picks)})*",
             "   _If you don't own these, consider entering_"]
    for r in picks[:max_rows]:
        t = _ticker_with_name(r.get("ticker") or "?", market)
        ia = r.get("investor_action") or {}
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        ev = r.get("evolution") or {}
        alloc = pp.get("suggested_allocation_pct") or 0
        hdays = pp.get("time_horizon_days") or 0
        entry = ia.get("entry") or "?"
        rank = r.get("rank")
        # Ticket 12 · Explicit confidence field selection + label.
        # We display `calibrated_confidence` from the SSoT bridge · this is
        # the post-calibration probability (Runner 2 v3 · [0,1]) NOT the
        # legacy Runner 1 "Rec Confidence %" which was on a different scale.
        # If operator sees older 80-90% values it's because they were seeing
        # Runner 1's raw score · Runner 2's calibrated numbers are honest.
        conf = r.get("calibrated_confidence")
        conf_label = "cal"   # explicit · shows in header as "conf 52% cal"
        if conf is None:
            conf = r.get("confidence")
            conf_label = "raw"
        # Recommendation Age (Phase 5)
        days_rec = ev.get("days_recommended") or 1
        remaining = max(0, hdays - days_rec + 1)
        age_str = ("NEW today" if ev.get("is_new") else
                    f"day {days_rec} of {hdays} · {remaining}d left")
        # Ticket 4: performance since rec date from position_store
        perf = _perf_since_rec(r.get("ticker") or "", market)
        # Emoji per entry-level
        emoji = "🟢🟢" if entry == "BUY" and (r.get("percentile_action") == "STRONG_BUY") else "🟢"
        # Header line with rank + confidence + current price
        rank_str = f"#{rank}" if rank else "—"
        conf_str = f"{conf:.0%} {conf_label}" if isinstance(conf, (int, float)) and conf else "—"
        cp = _fmt_price(ez.get("current_price") or perf.get("current_price"), market)
        lines.append(f"   {emoji} *{t}*   rank {rank_str}  ·  conf {conf_str}  ·  now {cp}")
        lines.append(f"      _{age_str}_ · 💰 {entry} · size {alloc}% · hold ~{hdays} days")
        if ez.get("stop_loss") is not None and ez.get("target_1") is not None:
            lines.append(
                f"      📥 Buy zone: {_fmt_price(ez.get('ideal_buy_low'), market)}"
                f"–{_fmt_price(ez.get('ideal_buy_high'), market)}"
            )
            # Target 1 (conservative) + Target 2 (stretch · +50% headroom on target-1 range)
            t1 = ez.get("target_1")
            t2 = ez.get("target_2")
            if t2 is None and t1 is not None and ez.get("current_price"):
                # Derive Target 2 as +50% of Target 1's headroom over current price
                cp_val = ez.get("current_price")
                if cp_val and t1 > cp_val:
                    t2 = cp_val + (t1 - cp_val) * 1.5
            t1_str = _fmt_price(t1, market)
            t2_str = _fmt_price(t2, market) if t2 else "—"
            lines.append(
                f"      🛡 Stop: {_fmt_price(ez.get('stop_loss'), market)}"
                f"   🎯 T1: {t1_str}   🎯🎯 T2: {t2_str}"
            )
        # Ticket 4: Performance since recommendation date (per rec inline)
        if perf and not ev.get("is_new") and perf.get("current_return_pct") is not None:
            lines.append(
                f"      📈 Since {perf.get('first_seen_date')}: "
                f"entry {_fmt_price(perf.get('entry_price'), market)} → "
                f"now {_fmt_price(perf.get('current_price'), market)}  "
                f"({perf['current_return_pct']:+.2f}%)"
            )
            if perf.get("max_gain_pct") is not None or perf.get("max_drawdown_pct") is not None:
                lines.append(
                    f"      🔺 Max gain +{perf.get('max_gain_pct', 0):.2f}%   "
                    f"🔻 Max DD {perf.get('max_drawdown_pct', 0):+.2f}%"
                )
    if len(picks) > max_rows:
        lines.append(f"   _...+{len(picks) - max_rows} more new-buy ideas_")
    return lines


def _perf_since_rec(ticker: str, market: str) -> dict:
    """Ticket 4 · Recommendation Performance Since Rec Date.

    Reads from backend/portfolio/position_store which already tracks
    first_seen_date · first_seen_price · high_water · low_water · last_seen_price
    per ticker. Returns the enriched performance dict for the Command Center.
    """
    try:
        from pathlib import Path
        from backend.portfolio.position_store import load_position
        reports_dir = Path("reports") if market == "india" else Path("usa/reports")
        rec = load_position(reports_dir, market, ticker)
        if rec is None:
            return {}
        entry = rec.first_seen_price
        curr = rec.last_seen_price
        high = rec.high_water_price
        low = rec.low_water_price
        if entry and entry > 0:
            return {
                "first_seen_date":    rec.first_seen_date,
                "entry_price":        entry,
                "current_price":      curr,
                "high_water":         high,
                "low_water":          low,
                "current_return_pct": round((curr / entry - 1) * 100, 2) if curr else None,
                "max_gain_pct":       round((high / entry - 1) * 100, 2) if high else None,
                "max_drawdown_pct":   round((low / entry - 1) * 100, 2) if low else None,
                "n_appearances":      rec.n_appearances,
            }
    except Exception:
        pass
    return {}


def _actionable_exits(recs: Sequence[Mapping], market: str,
                        max_rows: int = 4) -> list[str]:
    exits = [r for r in recs
              if (r.get("investor_action") or {}).get("if_holding") in ("REDUCE", "EXIT")]
    exits.sort(key=lambda r: r.get("ensemble_score") or 0)   # worst first
    if not exits:
        return []
    lines = ["", f"🔴 *EXITS IF YOU HOLD ({len(exits)})*",
             "   _If any of these are in your portfolio, act on them_"]
    for r in exits[:max_rows]:
        t = _ticker_with_name(r.get("ticker") or "?", market)
        ia = r.get("investor_action") or {}
        raw_action = ia.get("if_holding") or "?"
        # 4-state vocabulary · REDUCE + AVOID collapse to EXIT
        action = "EXIT" if raw_action in ("REDUCE", "SELL", "AVOID", "EXIT") else raw_action
        emoji = "🔴"
        # Discipline check: if the exit reason class is RANK_ONLY / churn
        # AND ensemble_score is still positive, flag it.
        score = r.get("ensemble_score") or 0
        churn_warn = "   ⚠️ still positive-score — confirm intended" if (
            action in ("REDUCE", "EXIT") and score > 0) else ""
        risks = ((r.get("why") or {}).get("top_risks") or [None])[0]
        risks_short = (str(risks)[:80] + "...") if risks and len(str(risks)) > 80 else (risks or "")
        lines.append(f"   {emoji} *{t}*   →   {action}{churn_warn}")
        if risks_short:
            lines.append(f"      ⚠️ Reason: {risks_short}")
    if len(exits) > max_rows:
        lines.append(f"   _...+{len(exits) - max_rows} more exit signals_")
    return lines


def _daily_change_summary(recs: Sequence[Mapping], market: str, max_rows: int = 5) -> list[str]:
    """v3.0 FINAL Phase 4: What Changed Since Yesterday.

    Shows every material rec change with rank/confidence/action deltas.
    Higher-value than the old _evolution_summary because it formats each
    change as a PM-friendly diff block.
    """
    changes = []
    for r in recs:
        ev = r.get("evolution") or {}
        if ev.get("is_new"):
            continue   # NEW recs handled separately below
        if not (ev.get("action_change") or ev.get("lifecycle_change")
                or ev.get("rank_change") not in (None, 0)
                or ev.get("confidence_change") not in (None, 0.0)):
            continue
        changes.append({
            "ticker": r.get("ticker") or "?",
            "action_change":     ev.get("action_change"),
            "rank_change":       ev.get("rank_change"),
            "confidence_change": ev.get("confidence_change"),
            "allocation_change": ev.get("allocation_change_pct"),
            "lifecycle_change":  ev.get("lifecycle_change"),
            "narrative":         ev.get("narrative") or "",
        })
    fresh = [r.get("ticker") for r in recs if (r.get("evolution") or {}).get("is_new")]

    if not changes and not fresh:
        return []

    lines = ["", "🔄 *WHAT CHANGED SINCE YESTERDAY*"]

    if not changes and fresh:
        # First-run day · everything is NEW · minimal display
        lines.append(f"   All {len(fresh)} recs are fresh today (day 1 of snapshot tracking)")
        return lines

    # Compact one-line-per-change format · saves ~30 chars per change vs
    # the older multi-line block format. Still preserves all key deltas.
    for c in changes[:max_rows]:
        t = _short_ticker(c["ticker"])
        parts = []
        if c["action_change"]:
            parts.append(f"{c['action_change']}")
        if c["rank_change"]:
            arrow = "↑" if c["rank_change"] < 0 else "↓"
            parts.append(f"rank {arrow}{abs(int(c['rank_change']))}")
        if c["confidence_change"]:
            parts.append(f"conf {c['confidence_change']:+.3f}")
        if c["allocation_change"]:
            parts.append(f"wt {c['allocation_change']:+.1f}%")
        detail = "  ·  ".join(parts) if parts else "—"
        lines.append(f"   • *{t}*  ·  {detail}")

    if len(changes) > max_rows:
        lines.append(f"   _...+{len(changes) - max_rows} more_")

    if fresh:
        fresh_list = ", ".join(_short_ticker(t) for t in fresh[:5])
        more = f" +{len(fresh) - 5}" if len(fresh) > 5 else ""
        lines.append(f"   🆕 NEW today: {fresh_list}{more}")

    return lines


def _evolution_summary(recs: Sequence[Mapping], max_rows: int = 3) -> list[str]:
    """DEPRECATED · replaced by _daily_change_summary in v3.0 FINAL.
    Kept as no-op for callers that still reference it."""
    return []
    changes = []
    for r in recs:
        ev = r.get("evolution") or {}
        if ev.get("action_change") or ev.get("lifecycle_change") or (
            ev.get("rank_change") not in (None, 0)):
            changes.append({
                "ticker": _short_ticker(r.get("ticker") or "?"),
                "narrative": ev.get("narrative") or "",
                "is_new": ev.get("is_new"),
            })
    fresh = [c for c in changes if c["is_new"]]
    material = [c for c in changes if not c["is_new"]]
    if not (fresh or material):
        return []
    lines = ["", "*WHAT CHANGED SINCE LAST RUN*"]
    if material:
        for c in material[:max_rows]:
            n = c["narrative"][:80]
            lines.append(f"  {c['ticker']}: {n}")
    if fresh:
        fresh_ts = ", ".join(c["ticker"] for c in fresh[:5])
        more = f" +{len(fresh) - 5}" if len(fresh) > 5 else ""
        lines.append(f"  NEW: {fresh_ts}{more}")
    return lines


def _risk_pulse(cs: Mapping, recs: Sequence[Mapping], market: str) -> list[str]:
    """Portfolio concentration + top/bottom risk-adjacent picks."""
    top_opp = cs.get("top_opportunity") or {}
    top_risk = cs.get("top_risk") or {}
    lines = []
    if top_opp.get("ticker") or top_risk.get("ticker"):
        lines.append("")
        lines.append("💼 *PORTFOLIO PULSE*")
    if top_opp.get("ticker"):
        lines.append(
            f"   🎯 Top opportunity: {_ticker_with_name(top_opp['ticker'], market)} · "
            f"{top_opp.get('action', '?')} · size {top_opp.get('allocation_pct', 0)}%"
        )
    if top_risk.get("ticker"):
        lines.append(
            f"   ⚠️ Top risk: {_ticker_with_name(top_risk['ticker'], market)} · "
            f"{top_risk.get('if_holding', '?')}"
        )
    return lines


def _ai_scorecard_line(payload: Mapping, market: str) -> list[str]:
    """v2.4: one-line AI Scorecard right below CEO CALL.
    v3.0 expansion: also list per-metric star breakdown so operator sees
    WHICH dimensions the AI is strong/weak on, not just the overall grade."""
    sc = payload.get("ai_scorecard") or {}
    if not sc or not sc.get("overall_score"):
        return []
    stars = "⭐" * max(0, min(5, sc.get("overall_stars") or 0))
    n = sc.get("n_trades") or 0
    verdict = (sc.get("verdict") or "-").replace("_", " ")
    period = f"{sc.get('period_start', '')[:10]} → {sc.get('period_end', '')[:10]}"
    lines = [
        "",
        f"📊 *AI PERFORMANCE SCORECARD*",
        f"   {stars}   {sc.get('overall_score')}/100 · {verdict}",
        f"   {n} closed trades · {period}",
    ]
    # Evidence Cycle 1: calibration verdict — never a new section,
    # just an honest label under the scorecard. Silent if data missing.
    cal_verdict = sc.get("calibration_verdict")
    if cal_verdict:
        cal_slope = sc.get("calibration_slope")
        if cal_slope is not None and (cal_slope < 0.5 or cal_slope > 1.5):
            lines.append(f"   ⚠️ Confidence calibration: {cal_verdict}")
        else:
            lines.append(f"   ✓ Confidence calibration: {cal_verdict}")
    # Per-metric breakdown · one compact line per metric with emoji+stars+value
    try:
        from pathlib import Path
        sc_path = Path("reports/ai_scorecard.json") if market == "india" else None
        if sc_path and sc_path.exists():
            full = json.loads(sc_path.read_text(encoding="utf-8"))
            metrics = full.get("metrics") or []
            if metrics:
                emoji_map = {
                    "Recommendation Accuracy": "🎯",
                    "Exit Timing":              "🚪",
                    "Target Hit Rate":          "🏹",
                    "Risk Control":             "🛡",
                    "Rotation Quality":         "🔄",
                    "Confidence Calibration":   "📐",
                }
                # Compact two-per-line format so 6 metrics = 3 lines (vs 6)
                pieces = []
                for m in metrics:
                    e = emoji_map.get(m.get("name", ""), "•")
                    st = "⭐" * (m.get("stars") or 0) or "—"
                    pieces.append(f"{e}{st}")
                # 3 columns per line
                for i in range(0, len(pieces), 3):
                    lines.append("   " + "   ".join(pieces[i:i+3]))
    except Exception:
        pass
    return lines


def _attribution_top(payload: Mapping) -> list[str]:
    """v2.4: which models drove today's decisions."""
    a = payload.get("attribution_summary") or {}
    if not a:
        return []
    drivers = a.get("dominant_drivers") or {}
    if not drivers:
        return []
    top_two = list(drivers.items())[:2]
    sector_share = a.get("avg_sector_share_pct")
    lines = ["", "🧠 *WHAT DROVE TODAY'S DECISIONS*"]
    for label, count in top_two:
        lines.append(f"   • {label}: dominant on {count} rec(s)")
    if sector_share is not None:
        if sector_share < 1.0:
            # Phase 10 · sector engine quiet today (not 0% displayed as failure)
            lines.append(f"   • Sector engine: 🔇 Quiet today (adaptive weight near zero)")
        elif a.get("sector_engine_measurably_active"):
            lines.append(f"   • Sector engine: 🟢 Active ({sector_share}% share)")
        else:
            lines.append(f"   • Sector engine: 🟡 Contributing ({sector_share}% share)")
    return lines


def _runner1_orphans(payload: Mapping, market: str, max_rows: int = 3) -> list[str]:
    """v3.0 Option D: Runner 1's active picks that Runner 2 did NOT include.

    Runner 1 is the defensive/legacy engine · demoted to a validation layer.
    Its picks are NOT active AEGIS recommendations — but showing them here
    preserves continuity ('where did APOLLO go?') and lets the operator
    see what a conservative model thinks vs what Runner 2 v3 (canonical)
    chose to promote.
    """
    if market != "india":
        return []   # Runner 1 covers India only today
    rv = payload.get("runner1_validation") or {}
    orphans = rv.get("runner1_orphans") or []
    if not orphans:
        return []
    # Operator's 4-state vocabulary: STRONG BUY · BUY · HOLD · EXIT
    strength_emoji = {
        "STRONG BUY":  "🟢🟢",
        "BUY":         "🟢",
        "ACCUMULATE":  "🟢",           # collapsed → BUY
        "HOLD":        "⚪",
        "WATCH":       "⚪",           # collapsed → HOLD
        "EXIT":        "🔴",
        "SELL":        "🔴",           # collapsed → EXIT
        "STRONG SELL": "🔴",           # collapsed → EXIT
        "REDUCE":      "🔴",           # collapsed → EXIT
        "AVOID":       "🔴",           # collapsed → EXIT
    }
    strength_display = {
        "ACCUMULATE":  "BUY",
        "WATCH":       "HOLD",
        "SELL":        "EXIT",
        "STRONG SELL": "EXIT",
        "REDUCE":      "EXIT",
        "AVOID":       "EXIT",
    }
    lines = ["",
                f"🛡 *DEFENSIVE VIEW · Runner 1 picks Runner 2 skipped ({len(orphans)})*",
                "   _Legacy engine's active picks · not AEGIS canonical · shown for continuity_"]
    currency = "Rs" if market == "india" else "$"
    for o in orphans[:max_rows]:
        t = _ticker_with_name(o.get("ticker") or "", market)
        raw_strength = (o.get("strength") or "?").upper()
        strength = strength_display.get(raw_strength, raw_strength)
        emoji = strength_emoji.get(raw_strength, "⚪")
        score = o.get("score")
        conf = o.get("confidence")
        price = o.get("price")
        buy_range = (o.get("buy_range") or "").strip()
        hist_target = o.get("hist_target")
        expected_range = (o.get("expected_range") or "").strip()
        holding = (o.get("holding") or "").strip()
        valid_until = (o.get("valid_until") or "").strip()
        reason_short = (o.get("reason") or "")[:60]

        # Line 1: emoji · ticker · strength · score · confidence
        header_parts = [f"{emoji} *{t}* — {strength}"]
        if isinstance(score, (int, float)):
            header_parts.append(f"📊 {score:.0f}/100")
        if isinstance(conf, (int, float)):
            header_parts.append(f"conf {conf:.0f}%")
        lines.append("   " + "  ·  ".join(header_parts))

        # Line 2: current price · buy zone · hold period
        detail_parts = []
        if isinstance(price, (int, float)) and price > 0:
            detail_parts.append(f"💰 now {currency}{price:,.2f}")
        if buy_range:
            detail_parts.append(f"📥 Buy: {currency}{buy_range}")
        if holding:
            detail_parts.append(f"⏳ {holding}")
        if detail_parts:
            lines.append("      " + "  ·  ".join(detail_parts))

        # Line 3: stop-loss · T1 · T2 (parity with rotational display)
        # Stop = -5% of current (Runner 1 CSV doesn't ship stop · standard AEGIS-Shield policy)
        # T1 = Runner 1's Hist Target when available · else current+8%
        # T2 = current + 15% (stretch)
        if isinstance(price, (int, float)) and price > 0:
            stop = price * 0.95
            t1 = hist_target if isinstance(hist_target, (int, float)) and hist_target > price else price * 1.08
            t2 = price * 1.15
            targets_line = (f"      🛡 Stop: {currency}{stop:,.2f}"
                                f"   🎯 T1: {currency}{t1:,.2f}"
                                f"   🎯🎯 T2: {currency}{t2:,.2f}")
            lines.append(targets_line)

        # Line 4: expected range + valid-until (compact)
        meta_parts = []
        if expected_range:
            meta_parts.append(f"📊 range {expected_range}")
        if valid_until:
            meta_parts.append(f"✅ valid → {valid_until}")
        if meta_parts:
            lines.append("      " + "  ·  ".join(meta_parts))

        if reason_short:
            lines.append(f"      _{reason_short}_")

    if len(orphans) > max_rows:
        lines.append(f"   _...+{len(orphans) - max_rows} more defensive picks_")
    lines.append(f"   ↳ 📚 Runner 1 → validation layer only (Option D · Article 4 SSoT)")
    return lines


def _intraday_hint(payload: Mapping, market: str) -> list[str]:
    """One-liner pointing at today's intraday shadow snapshot.

    Reads reports/research/research_platform.json (unified SSoT). If no
    Research Platform data yet, returns empty (graceful).
    """
    if market != "india":
        return []
    try:
        p = Path("reports/research/intraday_platform.json")
        if not p.exists():
            return []
        rp = json.loads(p.read_text(encoding="utf-8"))
        intra = (rp.get("live_evaluation") or {}).get("india") or {}
        dp = intra.get("daily_proxy") or {}
        r1 = dp.get("runner1") or {}
        r2 = dp.get("runner2") or {}
        leader = dp.get("leader") or "TIE"
        edge = dp.get("leader_edge_pct") or 0.0
        if not (r1 or r2):
            return []
        return [
            "",
            f"⚡ *INTRADAY SHADOW* (measurement only · deferred as product)",
            f"   R1 {r1.get('total_return_pct', 0):+.2f}%  ·  "
            f"R2 {r2.get('total_return_pct', 0):+.2f}%  ·  "
            f"Leader *{leader}*  ·  Edge {edge:+.2f}pp",
        ]
    except Exception:
        return []


def _runner2_exclusive(payload: Mapping, market: str, max_rows: int = 5) -> list[str]:
    """Symmetric to Defensive View · Runner 2 picks Runner 1 does NOT include.

    Operator asked: "you said both runners said CHAMBLFERT but I cannot see it
    in defensive?" — because CHAMBLFERT is a Runner-2-only pick (not in
    Runner 1's active list). This block surfaces such picks so the operator
    has visibility BOTH ways: R1-only AND R2-only.
    """
    if market != "india":
        return []
    recs = payload.get("recommendations") or []
    exclusive = []
    for r in recs:
        ia = r.get("investor_action") or {}
        if ia.get("entry") != "BUY":
            continue
        v = r.get("validation") or {}
        # NOT_TRACKED means Runner 1 doesn't have it at all today
        if v.get("agreement_label") == "NOT_TRACKED":
            exclusive.append(r)
    if not exclusive:
        return []
    lines = ["",
                f"🎯 *R2-EXCLUSIVE · Runner 2 picks Runner 1 not tracking ({len(exclusive)})*",
                "   _AEGIS canonical picks with no Runner 1 opinion today_"]
    currency = "Rs" if market == "india" else "$"
    for r in exclusive[:max_rows]:
        t = _ticker_with_name(r.get("ticker") or "?", market)
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        conf = r.get("calibrated_confidence")
        rank = r.get("rank")
        cp = _fmt_price(ez.get("current_price"), market)
        pct = r.get("percentile_action") or "BUY"
        # Collapse to 4-state
        pct_disp = "STRONG BUY" if pct == "STRONG_BUY" else "BUY"
        emoji = "🟢🟢" if pct == "STRONG_BUY" else "🟢"
        rank_str = f"#{rank}" if rank else "—"
        conf_str = f"conf {conf:.0%}" if isinstance(conf, (int, float)) else ""
        lines.append(f"   {emoji} *{t}* — {pct_disp}  ·  rank {rank_str}  ·  {conf_str}")
        lines.append(f"      💰 now {cp}"
                        + (f"  ·  🎯 T1 {_fmt_price(ez.get('target_1'), market)}"
                                if ez.get("target_1") else ""))
    if len(exclusive) > max_rows:
        lines.append(f"   _...+{len(exclusive) - max_rows} more R2-exclusive_")
    return lines


def _runner1_agreement_summary(payload: Mapping, market: str) -> list[str]:
    """v3.0: one-line "Runner 1 agrees with N of M today's picks" summary."""
    if market != "india":
        return []
    rv = payload.get("runner1_validation") or {}
    if not rv:
        return []
    consensus = rv.get("consensus_pct")
    counts = rv.get("agreement_counts") or {}
    if consensus is None:
        return []
    emoji = "🟢" if consensus >= 40 else ("🟡" if consensus >= 20 else "🟠")
    return [
        "",
        f"🤝 *DUAL-ENGINE VALIDATION*",
        f"   {emoji} Runner 1 agrees with {counts.get('AGREE', 0)}/{rv.get('n_runner2_recs', 0)} "
        f"of today's picks ({consensus}% consensus)",
        f"   Disagreements: {counts.get('DISAGREE', 0)} · "
        f"Neutral: {counts.get('NEUTRAL', 0)} · "
        f"Not tracked: {counts.get('NOT_TRACKED', 0)}",
    ]


def _research_platform_block(payload: Mapping, market: str) -> list[str]:
    """AEGIS Research Platform · executive dashboard block.

    Reads reports/research/research_platform.json (unified SSoT). Compact
    executive format per operator spec — program status, live leader,
    historical winner, disagreement panel, correlation lab lever count.

    Renders identically for India and USA · USA sees only its own
    delivery slice + the historical layer.
    """
    from pathlib import Path
    try:
        p = Path("reports/research/research_platform.json")
        if not p.exists():
            return []
        rp = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

    prog = rp.get("program") or {}
    status = rp.get("status") or {}
    layers = rp.get("layers") or {}
    live = layers.get("live_evaluation") or {}
    hist = layers.get("historical") or {}
    corr = layers.get("correlation_lab") or {}
    dis = layers.get("disagreements") or {}
    expl = layers.get("explainability") or {}

    day = prog.get("day_of_program") or 0
    target = prog.get("window_days_target") or 90
    minimum = prog.get("window_days_minimum") or 60
    canonical = prog.get("canonical") or "UNDECIDED"
    leader = status.get("leader") or "TIE"
    edge = status.get("leader_edge_pct") or 0.0
    confidence = status.get("confidence") or "insufficient"

    # Historical winner (for the operator's chosen market)
    hist_key = market if market in ("india", "usa") else "india"
    hist_market = (hist.get(hist_key) or {})
    hist_overall = hist_market.get("overall_winner") if hist_market else None
    hist_wins = None
    if hist_market:
        y1 = hist_market.get("year_wins_runner1", 0)
        y2 = hist_market.get("year_wins_runner2", 0)
        yt = hist_market.get("year_ties", 0)
        hist_wins = f"R1 {y1} / R2 {y2} / TIE {yt}"

    def _fmt_runner(label: str, m: dict | None) -> str:
        if not m:
            return f"   {label}: no data"
        ret = m.get("total_return_pct", 0.0)
        wr = (m.get("win_rate") or 0) * 100
        n = m.get("n_positions", 0)
        sharpe = m.get("sharpe_ratio")
        dd = m.get("max_drawdown_pct", 0.0)
        pf = m.get("profit_factor")
        parts = [f"   *{label}*",
                    f"      Ret {ret:+.2f}% · Win {wr:.0f}% · N {n}"]
        secondary = []
        if sharpe is not None:
            secondary.append(f"Sharpe {sharpe:.2f}")
        if pf is not None:
            secondary.append(f"PF {pf:.2f}")
        if dd:
            secondary.append(f"DD {dd:.1f}%")
        if secondary:
            parts.append(f"      " + " · ".join(secondary))
        return "\n".join(parts)

    lines: list[str] = ["", "━━━━━━━━━━━━━━━━━━━━━",
                            "🏁 *AEGIS RESEARCH PLATFORM*",
                            "━━━━━━━━━━━━━━━━━━━━━",
                            f"Program: {minimum} / {target} Days · Day {day}",
                            f"Canonical: *{canonical}*  ·  Leader: {leader}  ·  Edge: {edge:+.2f}%",
                            f"Confidence: {confidence}"]

    if market == "usa":
        # USA slice
        usa = live.get("usa_delivery") or {}
        r2 = usa.get("runner2")
        lines += ["", "🇺🇸 *USA DELIVERY* (Runner 2 only · R1 does not cover USA)"]
        lines.append(_fmt_runner("Runner 2", r2))
        if hist_market:
            lines += ["", f"📚 Historical: winner {hist_overall or '—'} · {hist_wins or ''}"]
        return lines

    # India · full display
    ind = live.get("india_delivery") or {}
    r1 = ind.get("runner1")
    r2 = ind.get("runner2")
    ind_leader = ind.get("leader")
    ind_edge = ind.get("leader_edge_pct") or 0.0
    overlap = ind.get("overlap") or {}

    lines += ["", "🇮🇳 *INDIA DELIVERY*",
                 f"   Leader: {ind_leader}  ·  Edge {ind_edge:+.2f}pp"]
    lines.append(_fmt_runner("Runner 1", r1))
    lines.append(_fmt_runner("Runner 2", r2))
    if overlap and overlap.get("agreement_pct") is not None:
        lines.append(f"   Overlap: agree {overlap.get('agreement_pct')}%  ·  "
                        f"disagree {overlap.get('disagreement_pct')}%  ·  "
                        f"buy-overlap {overlap.get('buy_overlap_pct')}%")

    # Intraday · shadow (deferred per CEO)
    intra = live.get("india_intraday") or {}
    dp = intra.get("daily_proxy") or {}
    r1i = dp.get("runner1")
    r2i = dp.get("runner2")
    it_leader = dp.get("leader") or "TIE"
    it_edge = dp.get("leader_edge_pct") or 0.0
    if r1i or r2i:
        lines += ["", "⚡ *INDIA INTRADAY* (shadow · deferred as product · measurement only)",
                     f"   Leader: {it_leader}  ·  Edge {it_edge:+.2f}pp"]
        if r1i:
            lines.append(f"   R1: {r1i.get('total_return_pct', 0):+.2f}% · "
                            f"Win {(r1i.get('win_rate') or 0)*100:.0f}% · "
                            f"N {r1i.get('n_positions', 0)}")
        if r2i:
            lines.append(f"   R2: {r2i.get('total_return_pct', 0):+.2f}% · "
                            f"Win {(r2i.get('win_rate') or 0)*100:.0f}% · "
                            f"N {r2i.get('n_positions', 0)}")

    # Historical winner
    if hist_market:
        lines += ["", f"📚 *Historical (India)*: winner {hist_overall or '—'}  ·  {hist_wins or ''}"]

    # Disagreement panel · show up to 3 decisive buckets
    if dis and dis.get("decisive_buckets"):
        lines += ["", "⚖️ *DISAGREEMENTS · verdict panel*"]
        for bucket, v in list(dis.get("decisive_buckets", {}).items())[:3]:
            lines.append(f"   {bucket}: winner {v.get('winner')} · "
                            f"R1 WR {(v.get('r1_win_rate') or 0)*100:.0f}% · "
                            f"R2 WR {(v.get('r2_win_rate') or 0)*100:.0f}% · "
                            f"n {v.get('n_scored', 0)}")
    elif dis and dis.get("n_total"):
        lines += ["", f"⚖️ Disagreements: {dis.get('n_total')} logged · "
                         f"{dis.get('n_scorable', 0)} scorable · verdict panel building"]

    # Correlation lab summary
    if corr and corr.get("pearson") is not None:
        pear = corr.get("pearson")
        n_levers = len((corr.get("top_refinement_levers") or []))
        lines += ["", f"🔬 *Correlation Lab*: intraday↔delivery pearson {pear:+.3f}  ·  "
                         f"{n_levers} refinement lever(s) surfaced"]

    # Explainability narrative (today)
    if expl and expl.get("narrative"):
        lines += ["", f"📝 {expl.get('narrative')[:200]}"]

    lines += ["",
                 "_Governed by Article IX (Research Lifecycle) + Article X (Evidence-First Promotion) · Paper-only · Both runners CANDIDATES · No canonicity declaration until Day-60 first-decision + Day-90 target confirmed._"]
    return lines


# Legacy aliases (kept so section-order tuple below doesn't break)
def _head_to_head_block(payload: Mapping, market: str) -> list[str]:
    """Deprecated · superseded by _research_platform_block. Kept as no-op alias."""
    return []


def _backtest_snapshot_block(payload: Mapping, market: str) -> list[str]:
    """Deprecated · content now consolidated inside _research_platform_block."""
    return []


# ═══ Standalone Research Platform message (sent as second Telegram) ═══
def render_research_platform_message(market: str,
                                          budget: int | None = None) -> str:
    """Render the full AEGIS Research Platform report as a standalone
    Telegram message. Sent right after the main Command Center · gives
    the operator the full evidence panel without competing for budget.

    Reads reports/research/research_platform.json (SSoT). Returns a
    single string ≤ budget chars, with all Research artefacts:
      · Program status + canonical decision
      · Runner 1 vs Runner 2 side-by-side (all metrics)
      · India Intraday shadow (both runners)
      · Historical per-year winner (backtracking)
      · Disagreement verdict panel
      · Correlation Lab · refinement levers
      · Explainability narrative
    """
    from pathlib import Path
    # Delivery-ONLY JSON · separate from intraday (operator directive · no clubbing)
    budget = resolve_budget("research_platform", override=budget)
    try:
        p = Path("reports/research/delivery_platform.json")
        if not p.exists():
            return ""
        rp = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""

    prog = rp.get("program") or {}
    status = rp.get("status") or {}
    live = rp.get("live_evaluation") or {}
    hist = rp.get("historical") or {}
    dis = rp.get("disagreements") or {}
    expl = rp.get("explainability") or {}
    tickets = rp.get("tickets") or []
    corr = None  # correlation lab lives in intraday_platform.json now

    day = prog.get("day_of_program") or 0
    target = prog.get("window_days_target") or 90
    minimum = prog.get("window_days_minimum") or 60
    canonical = prog.get("canonical") or "UNDECIDED"
    leader = status.get("leader") or "TIE"
    edge = status.get("leader_edge_pct") or 0.0
    confidence = status.get("confidence") or "insufficient"

    conf_emoji = {
        "insufficient": "🟠",
        "flipping":     "🟡",
        "growing":      "🟢",
        "stable":       "🟢",
    }.get(confidence, "⚪")

    market_flag = "🇮🇳" if market == "india" else ("🇺🇸" if market == "usa" else "🌐")

    lines: list[str] = [
        "🏁 *AEGIS RESEARCH PLATFORM*",
        f"{market_flag} {market.upper()}  ·  📅 Day *{day}* of {target}  (min {minimum})",
        SEPARATOR,
        f"🏛 *Canonical:* {canonical}   ·   🥇 *Leader:* {leader}",
        f"📊 *Edge:* {edge:+.2f}pp   ·   {conf_emoji} *Confidence:* {confidence}",
    ]

    # ── India Delivery · side-by-side R1 vs R2 ──
    # (Intraday content lives EXCLUSIVELY in MSG 3 · never mixed here)
    if market != "usa":
        ind = live.get("india") or {}
        r1 = ind.get("runner1") or {}
        r2 = ind.get("runner2") or {}
        overlap = ind.get("overlap") or {}
        ind_leader = ind.get("leader")
        ind_edge = ind.get("leader_edge_pct") or 0.0
        lines += ["",
                     "🇮🇳 *INDIA DELIVERY · Runner 1 vs Runner 2*",
                     f"   🥇 Leader: *{ind_leader}*  ·  Edge {ind_edge:+.2f}pp"]
        lines += ["",
                     "   📊 *Head-to-Head Metrics*"]
        rows = [
            ("N picks",         r1.get("n_positions", 0),     r2.get("n_positions", 0)),
            ("Return %",        f"{r1.get('total_return_pct', 0):+.2f}",
                                     f"{r2.get('total_return_pct', 0):+.2f}"),
            ("Win rate %",      f"{(r1.get('win_rate') or 0)*100:.0f}",
                                     f"{(r2.get('win_rate') or 0)*100:.0f}"),
            ("Median %",        f"{r1.get('median_return_pct', 0):+.2f}",
                                     f"{r2.get('median_return_pct', 0):+.2f}"),
            ("Sharpe",          _fmt(r1.get('sharpe_ratio')),
                                     _fmt(r2.get('sharpe_ratio'))),
            ("Sortino",         _fmt(r1.get('sortino_ratio')),
                                     _fmt(r2.get('sortino_ratio'))),
            ("Profit Factor",   _fmt(r1.get('profit_factor')),
                                     _fmt(r2.get('profit_factor'))),
            ("Max DD %",        f"{r1.get('max_drawdown_pct', 0):.2f}",
                                     f"{r2.get('max_drawdown_pct', 0):.2f}"),
            ("Tail Loss (CVaR)", _fmt(r1.get('tail_loss_cvar_pct')),
                                     _fmt(r2.get('tail_loss_cvar_pct'))),
            ("Turnover %",      f"{r1.get('turnover_pct', 0):.1f}",
                                     f"{r2.get('turnover_pct', 0):.1f}"),
            ("Stability %",     f"{r1.get('recommendation_stability_pct', 0):.1f}",
                                     f"{r2.get('recommendation_stability_pct', 0):.1f}"),
        ]
        lines.append(f"   `{'Metric':<15} {'R1':>10} {'R2':>10} {'Δ':>8}`")
        for label, v1, v2 in rows:
            try:
                delta = float(str(v2).replace('+','')) - float(str(v1).replace('+',''))
                delta_str = f"{delta:+.2f}" if isinstance(delta, float) else ""
            except (ValueError, TypeError):
                delta_str = "—"
            lines.append(f"   `{label:<15} {str(v1):>10} {str(v2):>10} {delta_str:>8}`")

        if overlap.get("agreement_pct") is not None:
            lines += ["",
                         f"   🤝 Agreement {overlap.get('agreement_pct')}%  ·  "
                         f"⚔️ Disagreement {overlap.get('disagreement_pct')}%",
                         f"   🎯 Buy Overlap {overlap.get('buy_overlap_pct')}%  ·  "
                         f"🏷 Sector Overlap {overlap.get('sector_overlap_pct')}%"]

        # ── Historical backtracking (per-year) ──
        h_india = hist.get("india") or {}
        years = h_india.get("years") or []
        if years:
            lines += ["",
                         "📚 *HISTORICAL BACKTRACK · India · per-year*"]
            for y in years[-5:]:
                w = y.get("winner_this_year") or "—"
                edge_y = y.get("edge_pp", 0)
                lines.append(f"   {y.get('year')}: winner *{w}*  ·  "
                                f"R1 med {y.get('runner1',{}).get('median_return_pct',0):+.2f}%  ·  "
                                f"R2 med {y.get('runner2',{}).get('median_return_pct',0):+.2f}%  ·  "
                                f"Δ {edge_y:+.2f}pp")
            overall = h_india.get("overall_winner")
            y1 = h_india.get("year_wins_runner1", 0)
            y2 = h_india.get("year_wins_runner2", 0)
            yt = h_india.get("year_ties", 0)
            lines.append(f"   🏆 Overall: *{overall}*  ·  R1 wins {y1} / R2 wins {y2} / ties {yt}")

        # ── Disagreement panel ──
        if dis and dis.get("all_buckets"):
            lines += ["",
                         "⚖️ *DISAGREEMENT VERDICT PANEL* (gold layer)"]
            for bucket, v in list((dis.get("all_buckets") or {}).items())[:6]:
                w = v.get("winner", "—")
                n = v.get("n_scored", 0)
                lines.append(f"   {bucket}: winner *{w}*  ·  "
                                f"R1 WR {(v.get('r1_win_rate') or 0)*100:.0f}%  ·  "
                                f"R2 WR {(v.get('r2_win_rate') or 0)*100:.0f}%  ·  n {n}")
            note = dis.get("sample_size_note") or ""
            if note:
                lines.append(f"   _{note}_")

        # ── Correlation lab ──
        if corr and corr.get("pearson") is not None:
            pear = corr.get("pearson")
            n_levers = len(corr.get("top_refinement_levers") or [])
            interp = corr.get("interpretation", "") or ""
            lines += ["",
                         f"🔬 *CORRELATION LAB · Intraday↔Delivery*",
                         f"   Pearson {pear:+.3f}  ·  {n_levers} refinement lever(s)",
                         f"   _{interp[:180]}_"]
            for lev in (corr.get("top_refinement_levers") or [])[:3]:
                slice_str = ", ".join(f"{k}={v}" for k, v in (lev.get("slice") or {}).items()
                                            if k in ("sector", "industry", "dimension_bucket"))
                lines.append(f"   • {lev.get('category')}: {slice_str}")

        # ── Explainability narrative ──
        if expl and expl.get("narrative"):
            lines += ["",
                         "📝 *TODAY'S NARRATIVE*",
                         f"   {expl.get('narrative')[:250]}"]

    # ── USA slice (Runner 2 only) ──
    if market == "usa":
        usa = live.get("usa") or {}
        r2 = usa.get("runner2") or {}
        lines += ["",
                     "🇺🇸 *USA DELIVERY* (Runner 2 only · R1 does not cover USA)",
                     f"   N picks {r2.get('n_positions', 0)}  ·  "
                     f"Return {r2.get('total_return_pct', 0):+.2f}%  ·  "
                     f"Win {(r2.get('win_rate') or 0)*100:.0f}%",
                     f"   Sharpe {_fmt(r2.get('sharpe_ratio'))}  ·  "
                     f"PF {_fmt(r2.get('profit_factor'))}  ·  "
                     f"Max DD {r2.get('max_drawdown_pct', 0):.2f}%"]
        h_usa = hist.get("usa") or {}
        if h_usa.get("years"):
            lines += ["", "📚 *HISTORICAL BACKTRACK · USA · per-year*"]
            for y in h_usa["years"][-5:]:
                lines.append(f"   {y.get('year')}: winner *{y.get('winner_this_year')}*")

    # ── Tickets summary ──
    if tickets:
        lines += ["",
                     "🎫 *RESEARCH TICKETS*"]
        for t in tickets[:5]:
            cand = "🏛 candidate" if t.get("canonical_candidate") else "⏸ deferred"
            lines.append(f"   • {t.get('ticket_id')}: {t.get('lifecycle_state')}  ·  {cand}")

    # ── Footer ──
    lines += ["",
                 SEPARATOR,
                 "_Governed by Article IX (Research Lifecycle) + Article X (Evidence-First Promotion)_",
                 "_Paper-only · Both runners CANDIDATES · No canonicity declaration before Day 60_"]

    msg = "\n".join(lines).strip()
    if len(msg) > budget:
        # Hard-cap only if exceeded · rare
        msg = msg[:budget - 100] + "\n\n_...truncated to budget..._"
    return msg


def _fmt(v) -> str:
    """Format an optional numeric metric for display · '—' for None."""
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


# ═══ Standalone Intraday Platform message (Msg 3 · parallel to delivery) ═══
def render_intraday_platform_message(market: str,
                                          budget: int | None = None) -> str:
    """Dedicated Intraday message · parallel to delivery/research platform.

    Operator ask: "goahead and do same operations runner 1, runner 2
    implement fully for intraday, make a parallel implementation."

    Structure mirrors the delivery Research Platform message but scoped
    to INTRADAY shadow only:
      · Runner 1 vs Runner 2 hourly-intraday side-by-side (all metrics)
      · Intraday daily-proxy fallback (single-bar open→close) for coverage
      · Historical intraday signal test (correlation lab verdict)
      · Refinement lever list (sector-scoped ORC pockets)
      · Explicit deferred-as-product framing per CEO

    Reads reports/research/intraday_platform.json (SEPARATE from delivery).
    Sent as a THIRD Telegram message after the daily advisory and the
    delivery Research Platform message. NEVER reads delivery data.
    """
    from pathlib import Path
    budget = resolve_budget("intraday_platform", override=budget)
    try:
        p = Path("reports/research/intraday_platform.json")
        if not p.exists():
            return ""
        rp = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""

    live = rp.get("live_evaluation") or {}
    intra = live.get("india") or {}
    prog = rp.get("program") or {}
    corr_from_intraday = rp.get("correlation_lab") or {}
    layers = {}   # legacy · not used in split-file mode

    day = prog.get("day_of_program") or 0
    target = prog.get("window_days_target") or 90
    market_flag = "🇮🇳" if market == "india" else "🌐"

    # Intraday-specific parameters (tighter than swing · session-scoped)
    INTRADAY_STOP_PCT = 0.003    # -0.3% intraday stop (much tighter than swing -5%)
    INTRADAY_T1_PCT   = 0.005    # +0.5% intraday T1
    INTRADAY_T2_PCT   = 0.010    # +1.0% intraday T2 (stretch)

    lines: list[str] = [
        "⚡ *AEGIS INTRADAY · shadow evaluation*",
        f"{market_flag} {market.upper()}  ·  📅 Day *{day}* of {target}",
        SEPARATOR,
        "🏛 *Status:* DEFERRED as product · measurement only · no orders",
        "🎯 *Session:* open → close  ·  ⏳ *Hold:* same-day (1 session)",
        ("_📚 SHADOW UNIVERSE: reuses swing picks as measurement corpus._ "
             "_No separate intraday-selection engine yet (would need vol/breakout ranker)._"),
    ]

    if market != "india":
        lines += ["",
                     "_Intraday shadow currently India-only · USA not yet enabled_"]
        return "\n".join(lines).strip()

    currency = "Rs"

    # ── Load per-stock positions from the paper stores (both runners) ──
    def _load_intraday_positions(runner_slug: str) -> dict:
        p = Path(f"reports/research/{runner_slug}/positions.json")
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("positions") or {}
        except Exception:
            return {}

    r1_positions = _load_intraday_positions("runner1_intraday_h1")
    r2_positions = _load_intraday_positions("runner2_intraday_h1")

    # If no hourly yet, fall back to daily-proxy positions so user sees SOMETHING
    if not r1_positions:
        r1_positions = _load_intraday_positions("runner1_intraday")
    if not r2_positions:
        r2_positions = _load_intraday_positions("runner2_intraday")

    hourly = intra.get("hourly") or {}
    r1h = hourly.get("runner1") or {}
    r2h = hourly.get("runner2") or {}

    def _stock_rows(positions: dict) -> list[dict]:
        rows = []
        for t, p in positions.items():
            entry = p.get("entry_price") or 0
            last = p.get("last_seen_price") or 0
            high = p.get("high_water_price") or last
            low = p.get("low_water_price") or last
            if entry <= 0:
                continue
            ret = (last / entry - 1.0) * 100
            stop = entry * (1 - INTRADAY_STOP_PCT)
            t1 = entry * (1 + INTRADAY_T1_PCT)
            t2 = entry * (1 + INTRADAY_T2_PCT)
            hit_t1 = high >= t1
            hit_t2 = high >= t2
            hit_stop = low <= stop
            rows.append({
                "ticker":  t,
                "entry":   entry,
                "close":   last,
                "high":    high,
                "low":     low,
                "ret_pct": ret,
                "stop":    stop,
                "t1":      t1,
                "t2":      t2,
                "hit_t1":  hit_t1,
                "hit_t2":  hit_t2,
                "hit_stop": hit_stop,
            })
        rows.sort(key=lambda r: -r["ret_pct"])
        return rows

    r1_rows = _stock_rows(r1_positions)
    r2_rows = _stock_rows(r2_positions)

    def _emit_stock_lines(rows: list[dict], runner_label: str) -> None:
        lines.append("")
        lines.append(f"🇮🇳 *{runner_label} · INTRADAY ({len(rows)} stocks)*")
        if not rows:
            lines.append(f"   _no picks today · {runner_label} emitted no BUYs today_")
            return
        winners = [r for r in rows if r["ret_pct"] > 0]
        losers = [r for r in rows if r["ret_pct"] < 0]
        hit_t1 = sum(1 for r in rows if r["hit_t1"])
        hit_t2 = sum(1 for r in rows if r["hit_t2"])
        hit_stop = sum(1 for r in rows if r["hit_stop"])
        # Aggregate line
        lines.append(f"   📊 Return _{_mean_ret(rows):+.2f}%_  ·  "
                        f"Win {len(winners)}/{len(rows)}  ·  "
                        f"🏹 T1 hit {hit_t1}  ·  🎯🎯 T2 hit {hit_t2}  ·  "
                        f"🛡 stop hit {hit_stop}")
        # Winners
        if winners:
            lines.append("   🟢 *WINNERS*")
            for r in winners:
                _emit_stock(r, currency, market)
        if losers:
            lines.append("   🔴 *LOSERS*")
            for r in losers:
                _emit_stock(r, currency, market)

    def _mean_ret(rows) -> float:
        if not rows:
            return 0.0
        return sum(r["ret_pct"] for r in rows) / len(rows)

    def _emit_stock(r: dict, currency: str, market: str) -> None:
        short = _short_ticker(r["ticker"])
        name = _company_name(r["ticker"], market)
        nm = f" ({name})" if name else ""
        # Line 1: ticker · open → close · intraday %
        lines.append(f"      {'🟢' if r['ret_pct'] > 0 else '🔴'} *{short}*{nm}  ·  "
                        f"{currency}{r['entry']:,.2f} → {currency}{r['close']:,.2f}  ·  "
                        f"*{r['ret_pct']:+.2f}%*")
        # Line 2: intra-session H/L
        lines.append(f"         📈 H {currency}{r['high']:,.2f}  ·  "
                        f"📉 L {currency}{r['low']:,.2f}")
        # Line 3: session-scoped stop / T1 / T2 with hit markers
        t1_mark = " ✅" if r["hit_t1"] else ""
        t2_mark = " ✅" if r["hit_t2"] else ""
        stop_mark = " ⚠️" if r["hit_stop"] else ""
        lines.append(f"         🛡 Stop {currency}{r['stop']:,.2f}{stop_mark}  ·  "
                        f"🎯 T1 {currency}{r['t1']:,.2f}{t1_mark}  ·  "
                        f"🎯🎯 T2 {currency}{r['t2']:,.2f}{t2_mark}")

    _emit_stock_lines(r1_rows, "RUNNER 1")
    _emit_stock_lines(r2_rows, "RUNNER 2")

    # ── Head-to-head aggregate ──
    dp = intra.get("daily_proxy") or {}
    dp_leader = dp.get("leader") or "TIE"
    dp_edge = dp.get("leader_edge_pct") or 0.0
    lines += ["",
                 "🥇 *HEAD-TO-HEAD*",
                 f"   Leader: *{dp_leader}*  ·  Edge {dp_edge:+.2f}pp"]

    # ── Historical intraday backtrack (per-year via correlation-lab data) ──
    # Uses the pearson + sector-slice tests as the historical evidence panel.
    corr = corr_from_intraday or {}
    if corr and corr.get("pearson") is not None:
        pear = corr.get("pearson")
        n_levers = len(corr.get("top_refinement_levers") or [])
        interp = (corr.get("interpretation") or "")[:120]
        lines += ["",
                     "📚 *INTRADAY BACKTRACK · historical evidence*",
                     f"   Corpus n_trades: {corr.get('n_trades', 0)}",
                     f"   Pearson intraday↔swing: {pear:+.3f}",
                     f"   🔬 {n_levers} refinement lever(s) surfaced (sector-scoped)",
                     f"   _{interp}_"]

    lines += ["",
                 SEPARATOR,
                 "_Ticket R003 · Article IX · not a product · hourly bars fetched by parallel job_"]

    msg = "\n".join(lines).strip()
    if len(msg) > budget:
        msg = msg[:budget - 100] + "\n\n_...truncated to budget..._"
    return msg


def _integrity_footer(payload: Mapping, market: str) -> list[str]:
    """Tickets 16+17 · timestamps in operator-relevant timezone.

    Instead of pure UTC (unfriendly), render:
      · IST for India delivery
      · ET (auto-DST) for USA delivery
      · UTC as the audit anchor
    Also surface prices-as-of asof date so operator knows staleness.
    """
    from datetime import datetime, timezone, timedelta
    run_iso = str(payload.get("run_utc") or "")
    asof = str(payload.get("asof") or "")
    # Parse run_utc
    try:
        run_dt = datetime.fromisoformat(run_iso.replace("Z", "+00:00"))
        if run_dt.tzinfo is None:
            run_dt = run_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        run_dt = datetime.now(timezone.utc)

    utc_str = run_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # India: fixed IST = UTC+5:30 (no DST)
    ist_dt = run_dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
    ist_str = ist_dt.strftime("%H:%M IST")
    # USA: ET (NYSE market time) + CT (Central · operator-requested)
    # both auto-DST via zoneinfo · fall back to fixed offsets if unavailable
    try:
        from zoneinfo import ZoneInfo
        et_dt = run_dt.astimezone(ZoneInfo("America/New_York"))
        et_label = "EDT" if et_dt.dst() != timedelta(0) else "EST"
        et_str = et_dt.strftime("%H:%M ") + et_label
        ct_dt = run_dt.astimezone(ZoneInfo("America/Chicago"))
        ct_label = "CDT" if ct_dt.dst() != timedelta(0) else "CST"
        ct_str = ct_dt.strftime("%H:%M ") + ct_label
    except Exception:
        et_dt = run_dt.astimezone(timezone(timedelta(hours=-5)))
        et_str = et_dt.strftime("%H:%M EST")
        ct_dt = run_dt.astimezone(timezone(timedelta(hours=-6)))
        ct_str = ct_dt.strftime("%H:%M CST")

    if market == "india":
        local_line = f"🕒 Run {ist_str}  ·  {utc_str}  ·  AEGIS v3.0"
    else:
        # USA · NYSE ET is authoritative market time · CT is operator convenience
        local_line = f"🕒 Run NYSE {et_str}  ·  Chicago {ct_str}  ·  {utc_str}  ·  AEGIS v3.0"

    prices_line = f"💵 Prices as of last market close ({asof})" if asof else ""

    lines = ["", SEPARATOR]
    if prices_line:
        lines.append(prices_line)
    lines.append(local_line)
    lines.append(f"⚖️ Advisory only · PAPER · Not investment advice")
    return lines


def render_command_center_message(payload: Mapping, market: str,
                                       budget: int | None = None) -> str:
    """Render single crisp Telegram message from enriched recommendations.json.

    Returns a single string ≤ budget chars. Sections are added in priority
    order (CEO call → rotations → new buys → exits → evolution → risk pulse
    → footer). If any section would push us over budget, later sections are
    truncated or dropped rather than mid-section.
    """
    if not payload:
        return "AEGIS: no data available"
    # Resolve investor-configured budget (configs/telegram_budget.json)
    budget = resolve_budget("command_center", override=budget)
    cs = payload.get("ceo_summary") or {}
    recs = payload.get("recommendations") or []
    asof = str(payload.get("asof") or "?")

    # v3.0 FINAL · Phase 13 · Command Center section order (operator spec)
    #   CEO Call → 30-Day Performance → AI Scorecard → Dual-Engine Validation
    #   → What Changed → Rotation Signals → New Buy Ideas → Exits
    #   → Defensive View (Recommendation History proxy) → Decision Drivers
    #   → Portfolio Pulse → Run Metadata
    sections = [
        ("header",           _header(market, asof)),
        ("ceo_call",         _ceo_call(cs)),
        ("perf_summary",     _performance_summary(payload, market)),
        ("ai_scorecard",     _ai_scorecard_line(payload, market)),
        ("dual_engine",      _runner1_agreement_summary(payload, market)),
        ("what_changed",     _daily_change_summary(recs, market)),
        ("rotations",        _rotation_calls(recs, market)),
        ("new_buys",         _actionable_entries(recs, market)),
        ("exits",            _actionable_exits(recs, market)),
        ("r1_orphans",       _runner1_orphans(payload, market)),
        ("r2_exclusive",     _runner2_exclusive(payload, market)),
        # Intraday hint removed 2026-07-30 · shadow approach rejected.
        # See docs/AEGIS_INTRADAY_ARCHITECTURE.md for real intraday spec.
        ("attribution",      _attribution_top(payload)),
        ("risk_pulse",       _risk_pulse(cs, recs, market)),
        # Full Research Platform detail sent as a dedicated follow-up message
        # (render_research_platform_message) · no longer competes for budget
        ("footer",            _integrity_footer(payload, market)),
    ]

    # Reserve footer size upfront so we NEVER blow past budget on final render.
    footer_lines = sections[-1][1]
    footer_len = len("\n".join(footer_lines)) + 1 if footer_lines else 0
    effective_budget = max(0, budget - footer_len)

    out: list[str] = []
    used = 0
    for name, lines in sections[:-1]:      # everything except footer
        block = "\n".join(lines) + ("\n" if lines else "")
        if used + len(block) > effective_budget:
            continue                         # drop this section entirely
        out.extend(lines)
        used += len(block)
    # Footer always fits · pre-reserved above
    out.extend(footer_lines)

    return "\n".join(out).strip()


def load_and_render(reports_dir: Path, market: str,
                       budget: int | None = None) -> tuple[str, dict]:
    """Load recommendations.json and render. Returns (message, meta)."""
    p = reports_dir / "recommendations.json"
    if not p.exists():
        return f"AEGIS {market}: recommendations.json missing", {"n_recs": 0}
    payload = json.loads(p.read_text(encoding="utf-8"))
    msg = render_command_center_message(payload, market, budget=budget)
    effective_budget = budget if budget is not None else resolve_budget("command_center")
    meta = {
        "n_recs":          len(payload.get("recommendations") or []),
        "asof":            payload.get("asof"),
        "budget_chars":    effective_budget,
        "message_chars":   len(msg),
        "n_rotations":     (payload.get("ceo_summary") or {}).get("rotations_count", 0),
        "n_actionable":    (payload.get("ceo_summary") or {}).get("actionable_count", 0),
    }
    return msg, meta
