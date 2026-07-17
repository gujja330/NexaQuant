# india/telegram_notify.py
"""
TELEGRAM DAILY NOTIFIER — a portfolio DIARY, not a jargon dump.

Reads today's canonical recommendations (data/aegis_today.csv) and the growing snapshot DB
(data/aegis_recommendation_db.csv) + registry, and sends a message that answers the operator's
real questions:
  * What do I own today, and how has each name moved since AEGIS first recommended it?
  * What entered / exited / got resized since last run — and WHY?
  * What did the strategy signal for exits (not "SELL NOW" — an explicit reason)?

Format is intentionally opinionated:
  * Grade A/B/C instead of raw "suitability" scores
  * Evidence label (strong / medium / low / none) — the case count driving Rec Confidence
  * Diary line per stock: entry → current with ₹ + % move
  * NEW / HOLD / WATCH verdict per pick
  * SOLD section with exit reason from india/exit_reasons.py
  * Portfolio weighted P&L since entry
  * "Exit signal return" wording — never "booked" (only your paper/live portfolio books P&L)

SECURITY: never hard-code the token. Put it in a git-ignored .env.telegram:
    TELEGRAM_BOT_TOKEN = 123456:ABC...           (from @BotFather)
    TELEGRAM_CHAT_ID   = 12345678                (your chat id; get it from @userinfobot)
Optional: AEGIS_SPREADSHEET_ID -> appends a link to the live Google Sheet.

Run:  python india/telegram_notify.py            # send today's summary
      python india/telegram_notify.py --check    # validate config + print the message (no send)
      python india/telegram_notify.py --resolve  # discover your chat id from getUpdates
"""
import os, sys, re, json, hashlib, urllib.parse, urllib.request, warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
CANON = ROOT / "data" / "aegis_today.csv"
DB_PATH = ROOT / "data" / "aegis_recommendation_db.csv"
REG_PATH = ROOT / "data" / "aegis_registry.csv"

# OPS001-I additions
MON001_FINGERPRINT_FILE = ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "reports" / "sealed_fingerprint.json"
MON001_YAML = ROOT / "india" / "monitoring" / "MON001_Forward_Validation" / "mon001.yaml"
TRIAL_MANIFEST = ROOT / "india" / "ai_lab" / "trial_manifest.md"


def load_env():
    for name in (".env.telegram", ".env.google", ".env"):
        p = ROOT / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    # accept common aliases so a simple .env works (TOKEN/BOT_TOKEN, CHAT_ID/CHAT)
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        for a in ("TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN"):
            if os.environ.get(a):
                os.environ["TELEGRAM_BOT_TOKEN"] = os.environ[a]; break
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        for a in ("CHAT_ID", "CHAT", "TELEGRAM_CHAT"):
            if os.environ.get(a):
                os.environ["TELEGRAM_CHAT_ID"] = os.environ[a]; break
    # sanitize: extract the bare token even if pasted with "...HTTP API:" prefix or stray spaces
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{20,}", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    if m:
        os.environ["TELEGRAM_BOT_TOKEN"] = m.group(0)


def resolve_chat_id():
    """Find your chat id from the bot's recent messages (getUpdates) — message the bot first."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("  no TELEGRAM_BOT_TOKEN / TOKEN set."); return
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20) as r:
            data = json.loads(r.read())
    except Exception:
        print("  getUpdates failed (network or bad token). Check the token, then re-run."); return
    chats = {}
    for u in data.get("result", []):
        ch = (u.get("message") or u.get("channel_post") or {}).get("chat", {})
        if ch.get("id"):
            chats[ch["id"]] = ch.get("first_name") or ch.get("title") or ch.get("username", "")
    if chats:
        print("  Found chat id(s) — add the right one to .env.telegram as TELEGRAM_CHAT_ID:")
        for cid, name in chats.items():
            print(f"    TELEGRAM_CHAT_ID={cid}   ({name})")
    else:
        print("  No chats yet. In Telegram, open your bot and press Start / send 'hi', then re-run --resolve.")


TIER_EMOJI = {"STRONG BUY": "🟢", "BUY": "🔵", "ACCUMULATE": "🟡", "WATCH": "⚪"}
TIER_HEAD = {
    "STRONG BUY": "keep or add if room",
    "BUY": "hold; don't chase above enter zone",
    "ACCUMULATE": "add gradually below enter zone",
    "WATCH": "watch only — do NOT add fresh money",
}


def _val(r, key, default=""):
    v = r.get(key, default)
    return default if (v is None or (isinstance(v, float) and pd.isna(v))) else v


def _grade(score):
    """A/B/C/D label from the raw 0-100 score."""
    try:
        s = float(score)
    except Exception:
        return "?"
    if s >= 70: return "A"
    if s >= 55: return "B"
    if s >= 45: return "C"
    return "D"


def _evidence(score, conf):
    """Reverse-engineer the case-count bucket from rec_conf_pct = 40 + 0.45*score + case_bonus.
    Bonus buckets: 15 (>=10 cases), 8 (5-9), 3 (1-4), 0 (none). Returns short label."""
    try:
        s = float(score); c = float(conf)
    except Exception:
        return ""
    bonus = c - 40 - 0.45 * s
    if bonus >= 12: return "strong evidence"
    if bonus >= 6:  return "medium evidence"
    if bonus >= 1.5: return "low evidence"
    return "new stock (no history)"


def _entry_info(sym, db, today_snap):
    """Walk backward through consecutive snapshots that still contain sym; the earliest is the
    current holding streak's entry. Returns {date, price, days} or None."""
    if db is None or db.empty:
        return None
    snaps_all = sorted(db["recommended_date"].astype(str).unique())
    if not snaps_all:
        return None
    sym_snaps = set(db[db["symbol"] == sym]["recommended_date"].astype(str))
    if not sym_snaps:
        return None
    entry_snap = None
    for snap in reversed(snaps_all):
        if snap in sym_snaps:
            entry_snap = snap
        else:
            break
    if entry_snap is None:
        return None
    row = db[(db["symbol"] == sym) & (db["recommended_date"].astype(str) == entry_snap)].iloc[0]
    try:
        entry_price = float(row.get("entry", 0))
    except Exception:
        entry_price = 0.0
    try:
        days = (pd.Timestamp(today_snap) - pd.Timestamp(entry_snap)).days
    except Exception:
        days = 0
    return {"date": entry_snap, "price": entry_price, "days": max(days, 0)}


def _sold_pnl(removed_syms, db, prev_snap, cur_snap, reg_df, closes, prev_exp, cur_exp, entries):
    """For each removed symbol, compute exit signal % + attribute a reason from india.exit_reasons."""
    if not removed_syms or db is None or db.empty:
        return []
    from india.exit_reasons import classify_exit
    out = []
    today = pd.Timestamp.now().normalize()
    for s in removed_syms:
        rows = db[db["symbol"] == s]
        if rows.empty:
            continue
        dates = sorted(rows["recommended_date"].astype(str).unique())
        entry_snap = dates[0]
        entry_row = rows[rows["recommended_date"].astype(str) == entry_snap].iloc[0]
        try:
            entry_price = float(entry_row.get("entry", 0))
        except Exception:
            entry_price = 0.0
        # try live parquet, fall back to closes
        cur_price = None
        p = ROOT / "data" / "raw" / "india" / f"{s}_D1.parquet"
        if p.exists():
            try:
                cur_price = float(pd.read_parquet(p)["close"].iloc[-1])
            except Exception:
                cur_price = None
        if cur_price is None and closes is not None and s in closes.columns:
            try:
                cur_price = float(closes[s].dropna().iloc[-1])
            except Exception:
                pass
        if entry_price <= 0 or cur_price is None:
            continue
        pct = 100 * (cur_price - entry_price) / entry_price
        rp = cur_price - entry_price
        try:
            days = (today - pd.Timestamp(entry_snap)).days
        except Exception:
            days = 0
        code, emoji, headline, detail = classify_exit(
            s, prev_snap, cur_snap, reg_df=reg_df, closes=closes,
            prev_exp=prev_exp, cur_exp=cur_exp, today=today, entries=entries or [])
        out.append({
            "sym": s, "sector": str(entry_row.get("sector", "")),
            "entry": entry_price, "exit": cur_price, "pct": pct, "rupee": rp, "days": max(days, 0),
            "code": code, "emoji": emoji, "headline": headline, "detail": detail,
        })
    return out


# ================================================================
# OPS001-I · Institutional-quality Telegram formatter helpers
# See docs/OPS001H_TELEGRAM_REDESIGN.md for the design.
# Presentation-only additions. No strategy / scoring / production
# logic touched.
# ================================================================


def _today_ist_str():
    """Today's IST calendar date (UTC+5:30). Independent of host TZ."""
    utc = datetime.now(timezone.utc)
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def _now_utc_and_ist():
    utc = datetime.now(timezone.utc)
    ist = utc + timedelta(hours=5, minutes=30)
    return utc.strftime("%Y-%m-%dT%H:%MZ"), ist.strftime("%H:%M IST")


def _read_mon001_fingerprint():
    """Read sealed_fingerprint.json. Returns dict with hash + algorithm_version.
    Never raises — returns empty strings on failure."""
    try:
        data = json.loads(MON001_FINGERPRINT_FILE.read_text(encoding="utf-8"))
        return {"hash": data.get("hash", ""), "algorithm_version": data.get("algorithm_version", 0)}
    except Exception:
        return {"hash": "", "algorithm_version": 0}


def _read_trial_count():
    """cumulative_strategy_search from trial_manifest.md."""
    try:
        text = TRIAL_MANIFEST.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"cumulative_strategy_search:\s*(\d+)", text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _days_between(from_date, to_date=None):
    """Days between YYYY-MM-DD dates. to_date defaults to today IST."""
    try:
        if to_date is None:
            to_date = _today_ist_str()
        return int((pd.Timestamp(to_date) - pd.Timestamp(str(from_date))).days)
    except Exception:
        return 0


def _derive_stop_price(entry_price, buy_range_str, default_pct=0.05):
    """Presentation-only stop level for the operator's downside anchor.
    Not a strategy stop. Uses buy-range-low × 0.97 if available, else
    entry × (1 - default_pct). Returns (stop_price, stop_pct) or (None, 0)."""
    try:
        e = float(entry_price)
        if e <= 0:
            return None, 0.0
    except Exception:
        return None, 0.0
    stop = e * (1 - default_pct)
    try:
        # buy_range_str like "4830 - 5104" or "4830-5104"
        parts = re.split(r"[-–\s]+", str(buy_range_str).strip())
        parts = [p for p in parts if p]
        if parts:
            lo = float(parts[0])
            if lo > 0:
                stop = max(stop, lo * 0.97)
    except Exception:
        pass
    stop_pct = (stop - e) / e * 100
    return stop, stop_pct


def _pct_from_current(current_price, target_str):
    """Return % move from current to target (nullable if either missing)."""
    try:
        c = float(current_price); t = float(target_str)
        if c <= 0:
            return None
        return (t - c) / c * 100
    except Exception:
        return None


def _actions_counts(t, diff_d):
    """Count NEW / HOLD / EXIT / WATCH for the ACTIONS block.
    Derives NEW from diff_d['new']; WATCH from Strength column; HOLD is remainder."""
    watch = 0
    if "Strength" in t.columns:
        watch = int((t["Strength"].astype(str).str.upper() == "WATCH").sum())
    new_syms = (diff_d or {}).get("new") or []
    removed = (diff_d or {}).get("removed") or []
    new_ct = len(new_syms)
    exit_ct = len(removed)
    hold_ct = max(0, len(t) - new_ct - watch)
    return {"new": new_ct, "hold": hold_ct, "exit": exit_ct, "watch": watch}


def _sector_allocation(t):
    """Aggregate weight per sector. Returns [(sector, weight_pct)] sorted desc."""
    from collections import defaultdict
    totals = defaultdict(float)
    for _, r in t.iterrows():
        sec = str(_val(r, "Sector", "")) or "Unknown"
        try:
            wt = float(_val(r, "Weight %", 0))
        except Exception:
            wt = 0.0
        totals[sec] += wt
    return sorted(totals.items(), key=lambda kv: -kv[1])


def _largest_position(t):
    """Return (ticker, weight%) of largest position by Weight %."""
    if t is None or t.empty or "Weight %" not in t.columns:
        return None, 0.0
    try:
        idx = t["Weight %"].astype(float).idxmax()
        row = t.loc[idx]
        return str(_val(row, "Stock", "")), float(_val(row, "Weight %", 0))
    except Exception:
        return None, 0.0


def _portfolio_confidence(t):
    """Weight-weighted mean of Rec Confidence % over the portfolio."""
    if t is None or t.empty:
        return None
    try:
        conf = t["Rec Confidence %"].astype(float)
        wts = t["Weight %"].astype(float)
        tw = float(wts.sum())
        if tw <= 0:
            return float(conf.mean())
        return float((conf * wts).sum() / tw)
    except Exception:
        return None


def _nifty_summary():
    """Read latest Nifty close + prior close from parquet. None if unavailable."""
    for name in ("NIFTY_D1.parquet", "^NSEI_D1.parquet", "NIFTY50_D1.parquet",
                  "NIFTY_INDEX_D1.parquet"):
        p = ROOT / "data" / "raw" / "india" / name
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if len(df) < 2:
                    continue
                cols_lc = {c.lower(): c for c in df.columns}
                close_col = cols_lc.get("close") or cols_lc.get("adj close")
                if not close_col:
                    continue
                last = float(df[close_col].iloc[-1])
                prev = float(df[close_col].iloc[-2])
                chg = (last - prev) / prev * 100 if prev > 0 else 0.0
                return {"close": last, "chg_pct": chg}
            except Exception:
                continue
    return None


def _risk_summary(t, db):
    """closest-to-stop and closest-to-target lists + concentration %.
    Presentation-only: uses derived stops (not strategy stops)."""
    closest_stop = []; closest_target = []
    for _, r in t.iterrows():
        sym = str(_val(r, "Stock", ""))
        try:
            cur_px = float(_val(r, "Current Price", 0))
        except Exception:
            cur_px = 0.0
        if cur_px <= 0:
            continue
        info = _entry_info(sym, db, str(_val(r, "Generated", "")))
        entry_px = info["price"] if info else cur_px
        stop_px, _ = _derive_stop_price(entry_px, _val(r, "Buy Range", ""))
        tgt_str = str(_val(r, "Hist Target", ""))
        try:
            tgt = float(tgt_str)
        except Exception:
            tgt = None
        if stop_px:
            dist_stop = (cur_px - stop_px) / cur_px * 100
            if dist_stop < 8.0:
                closest_stop.append((sym, dist_stop))
        if tgt:
            dist_tgt = (tgt - cur_px) / cur_px * 100
            if 0 <= dist_tgt < 5.0:
                closest_target.append((sym, dist_tgt))
    closest_stop.sort(key=lambda x: x[1])
    closest_target.sort(key=lambda x: x[1])
    # concentration: top-3 weight
    try:
        top3_wt = float(t.nlargest(3, "Weight %")["Weight %"].sum())
    except Exception:
        top3_wt = 0.0
    return {"closest_stop": closest_stop[:3], "closest_target": closest_target[:3],
            "top3_weight": top3_wt}


def _performance_buckets_from_registry(reg_df):
    """Compute 30D/90D/1Y win-rate + median from registry mature outcomes.
    Uses registry rows whose maturity has been logged. Returns dict of buckets."""
    if reg_df is None or reg_df.empty:
        return {}
    try:
        # heuristic: registry has 'asof' + 'maturity_return_pct' when mature; may not.
        # Use whatever we can find; skip if columns missing.
        if "maturity_return_pct" not in reg_df.columns or "asof" not in reg_df.columns:
            return {}
        d = reg_df[["asof", "maturity_return_pct"]].dropna()
        d["asof"] = pd.to_datetime(d["asof"], errors="coerce")
        d = d.dropna(subset=["asof"])
        today = pd.Timestamp(_today_ist_str())
        buckets = {}
        for label, days in [("30D", 30), ("90D", 90), ("1Y", 365)]:
            cutoff = today - pd.Timedelta(days=days)
            sub = d[d["asof"] >= cutoff]
            if len(sub) < 3:
                continue
            wins = (sub["maturity_return_pct"] > 0).mean()
            med = sub["maturity_return_pct"].median()
            buckets[label] = {"n": len(sub), "win_rate": wins * 100, "median": med}
        return buckets
    except Exception:
        return {}


def _why_changed_narrative(diff_d, sector_alloc):
    """Two-to-four-sentence narrative synthesised from portfolio changes."""
    parts = []
    if not diff_d:
        return None
    new_syms = (diff_d or {}).get("new") or []
    removed = (diff_d or {}).get("removed") or []
    increased = (diff_d or {}).get("increased") or []
    if new_syms:
        # Dominant sector of new adds
        parts.append(f"{len(new_syms)} new: {', '.join(new_syms[:3])}"
                      + ("…" if len(new_syms) > 3 else "") + ".")
    if removed:
        parts.append(f"{len(removed)} exit: {', '.join(removed[:3])}"
                      + ("…" if len(removed) > 3 else "") + ".")
    if sector_alloc:
        top_sec, top_w = sector_alloc[0]
        parts.append(f"Portfolio tilt toward <b>{top_sec}</b> ({top_w:.0f}%).")
    if increased:
        parts.append(f"Weight increases: {'; '.join(increased[:2])}.")
    if not parts:
        return None
    return " ".join(parts)


def _integrity_footer(asof, cycle_version="AEGIS_v2.2"):
    """Auditable integrity footer per OPS001-H §3.12.
    Includes run UTC + IST, market asof, MON001 fingerprint, trial count,
    cert id, next refresh guidance. Report SHA256 is appended AFTER the
    full body is assembled — see the tail of build_message()."""
    utc_str, ist_str = _now_utc_and_ist()
    fp = _read_mon001_fingerprint()
    fp_short = (fp["hash"] or "")[:8]
    trial = _read_trial_count()
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔐 <b>Integrity</b>",
        f"  <code>Run {utc_str} ({ist_str})</code>",
        f"  <code>Market asof {asof} (last close)</code>",
        f"  <code>MON001 fp {fp_short}… · algo v{fp['algorithm_version']}</code>",
        f"  <code>Cert MON001-CERT-2026-07-17 · Cycle {cycle_version}"
        + (f" · Trials {trial}" if trial is not None else "") + "</code>",
        f"  <code>Report SHA {{MSG_SHA}}</code>",   # placeholder replaced below
        "  <i>Advisory only · PAPER_ONLY · Not investment advice</i>",
    ]
    return "\n".join(lines)


def _finalize_integrity(msg):
    """Compute SHA256 of the message body (excluding the placeholder) and
    substitute it in. Yields an auditable hash the operator can compare
    across runs to detect duplicates."""
    placeholder = "{MSG_SHA}"
    without = msg.replace(placeholder, "PENDING")
    sha = hashlib.sha256(without.encode("utf-8")).hexdigest()[:8]
    return msg.replace(placeholder, f"{sha}…")


# ================================================================
# End OPS001-I helpers.
# ================================================================


def build_message():
    if not CANON.exists():
        return "AEGIS: no recommendations file yet (run recommendation_generator.py)."
    t = pd.read_csv(CANON)
    if t.empty:
        return "AEGIS: no recommendations today."

    # supporting data — all wrapped so a missing file never blocks the send
    db = pd.DataFrame()
    diff_d = {}
    try:
        from india.recommendation_db import load_db, daily_diff
        db = load_db()
        diff_d = daily_diff(db) if not db.empty else {}
    except Exception:
        pass

    reg_df = None
    try:
        if REG_PATH.exists():
            reg_df = pd.read_csv(REG_PATH)
    except Exception:
        pass

    closes = None
    prev_exp = cur_exp = None
    regime = ""
    try:
        from india.confidence_engine import current_regime
        cur_exp, regime, _ = current_regime()
    except Exception:
        pass
    try:
        from india.feature_engine import load_panels
        closes = load_panels()[0]
    except Exception:
        pass

    # prev/cur snapshot rows for exit classification (from the DB)
    prev_snap = cur_snap = pd.DataFrame()
    if not db.empty:
        snaps = sorted(db["recommended_date"].astype(str).unique())
        if len(snaps) >= 2:
            prev_snap = db[db["recommended_date"].astype(str) == snaps[-2]]
            cur_snap = db[db["recommended_date"].astype(str) == snaps[-1]]

    asof = str(_val(t.iloc[0], "Generated"))
    hm0 = re.search(r"\(([^)]+)\)", str(_val(t.iloc[0], "Recommended Holding")))
    hold_short = hm0.group(1) if hm0 else str(_val(t.iloc[0], "Recommended Holding"))
    prof = str(_val(t.iloc[0], "Profile")) if "Profile" in t else ""

    # OPS001-I precomputes -----------------------------------------------
    actions = _actions_counts(t, diff_d)
    nifty = _nifty_summary()
    sector_alloc = _sector_allocation(t)
    largest_sym, largest_wt = _largest_position(t)
    port_conf = _portfolio_confidence(t)
    risk = _risk_summary(t, db)
    perf_buckets = _performance_buckets_from_registry(reg_df)
    weekday_map = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    try:
        weekday = weekday_map[pd.Timestamp(asof).weekday()]
    except Exception:
        weekday = ""

    lines = []

    # ── HEADER (§3.1) ──────────────────────────────────────────────────
    lines.append("🏢 <b>NEXAQUANT · AEGIS Daily</b>")
    hdr2 = f"📅 Market asof <code>{asof}</code>"
    if weekday:
        hdr2 += f" ({weekday})"
    if regime:
        hdr2 += f" · Regime <b>{regime}</b>"
    lines.append(hdr2)
    hdr3_bits = []
    if prof:
        hdr3_bits.append(f"💼 <b>{prof.split(' ')[0]}</b>")
    if cur_exp is not None:
        hdr3_bits.append(f"Deploy <b>{cur_exp:.0%}</b> · Cash <b>{1-cur_exp:.0%}</b>")
    if nifty is not None:
        arrow_n = "▲" if nifty["chg_pct"] > 0 else ("▼" if nifty["chg_pct"] < 0 else "→")
        hdr3_bits.append(f"Nifty {arrow_n} <b>{nifty['chg_pct']:+.2f}%</b>")
    if hdr3_bits:
        lines.append(" · ".join(hdr3_bits))

    # ── TODAY'S ACTIONS (§3.2) ──────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎯 <b>ACTIONS TODAY</b>")
    if actions["new"] == 0 and actions["exit"] == 0 and actions["watch"] == 0:
        lines.append(f"  ⚪ <b>NO ACTION REQUIRED</b> — {actions['hold']} positions held; portfolio stable.")
    else:
        parts = []
        if actions["new"]:  parts.append(f"🟢 <b>{actions['new']} BUY</b>")
        if actions["hold"]: parts.append(f"🟡 <b>{actions['hold']} HOLD</b>")
        if actions["exit"]: parts.append(f"🔴 <b>{actions['exit']} EXIT</b>")
        if actions["watch"]: parts.append(f"⚪ <b>{actions['watch']} WATCH</b>")
        lines.append("  " + " · ".join(parts))
        lines.append("  ➤ Detail below")

    # ── MARKET SUMMARY (§3.3) ──────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🌐 <b>MARKET</b>")
    if nifty is not None:
        lines.append(f"  • Nifty <b>{nifty['close']:,.0f}</b> "
                     f"({nifty['chg_pct']:+.2f}%) · Regime <b>{regime or 'N/A'}</b>")
    else:
        lines.append(f"  • Regime <b>{regime or 'N/A'}</b>")
    if sector_alloc:
        top_secs = ", ".join(f"<b>{s}</b>" for s, _ in sector_alloc[:2])
        lines.append(f"  • Portfolio tilt: {top_secs}")
    lines.append(f"  • {len(t)} recommendations · sorted best-first · horizon {hold_short}")

    # ── PORTFOLIO HEALTH (§3.4) ────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("❤️ <b>PORTFOLIO HEALTH</b>")
    health_bits = []
    if port_conf is not None:
        health_bits.append(f"<code>Conf {port_conf:.0f}/100</code>")
    if sector_alloc:
        top_sec, top_w = sector_alloc[0]
        health_bits.append(f"<code>Top sector {top_sec} {top_w:.0f}%</code>")
    if largest_sym:
        health_bits.append(f"<code>Largest {largest_sym} {largest_wt:.0f}%</code>")
    if health_bits:
        lines.append("  " + " · ".join(health_bits))
    health2 = []
    if cur_exp is not None:
        health2.append(f"<code>Cash {1-cur_exp:.0%}</code>")
    health2.append(f"<code>Hold {hold_short}</code>")
    if risk["top3_weight"]:
        health2.append(f"<code>Top-3 conc {risk['top3_weight']:.0f}%</code>")
    if health2:
        lines.append("  " + " · ".join(health2))

    lines.append("")
    lines.append("──────── ⬇ scroll for detail ⬇ ────────")

    # ── TOP OPPORTUNITIES + CURRENT HOLDINGS (§3.5–3.6) ────────────────
    # Split t into "new/watch" (opportunities) and "held" (holdings).
    new_syms_set = set((diff_d or {}).get("new") or [])
    port_pcts = []  # for legacy portfolio-P&L rollup

    # Emit NEW picks first (Top Opportunities)
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🟢 <b>TOP OPPORTUNITIES</b>")
    opp_count = 0
    for _, r in t.iterrows():
        sym = str(_val(r, "Stock", ""))
        strat = str(_val(r, "Strength", ""))
        sec = str(_val(r, "Sector", ""))
        if sym in new_syms_set:
            opp_count += 1
            _emit_opportunity(lines, r, sym, sec, strat, db, asof, hold_short)

    if opp_count == 0:
        lines.append("  <i>No NEW picks today. See Current Holdings below.</i>")

    # Emit HOLD positions (Current Holdings)
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    hold_positions_count = 0
    lines.append("🟡 <b>CURRENT HOLDINGS</b>")
    for _, r in t.iterrows():
        sym = str(_val(r, "Stock", ""))
        strat = str(_val(r, "Strength", ""))
        sec = str(_val(r, "Sector", ""))
        if sym in new_syms_set or strat == "WATCH":
            continue
        info = _entry_info(sym, db, asof)
        if info is None or info["days"] == 0:
            continue
        hold_positions_count += 1
        try:
            cur_px = float(_val(r, "Current Price", 0))
        except Exception:
            cur_px = 0.0
        if cur_px > 0 and info["price"] > 0:
            pct = (cur_px - info["price"]) / info["price"] * 100
            rp = cur_px - info["price"]
            arrow = "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")
            wt = float(_val(r, "Weight %", 0) or 0)
            if wt > 0:
                port_pcts.append((pct, wt))
            lines.append(f"  <b>{sym}</b> · {sec} · held <b>{info['days']}d</b>")
            lines.append(f"    <code>₹{info['price']:,.0f} → ₹{cur_px:,.0f}</code>  "
                         f"{arrow} <b>{pct:+.1f}%</b> · <code>{rp:+,.0f}/sh</code>")
            stop_px, stop_pct = _derive_stop_price(info["price"], _val(r, "Buy Range", ""))
            expiry = str(_val(r, "Valid Until", ""))
            trail_pct = 3.0
            hold_bits = ["Continue <b>HOLD</b>"]
            if stop_px:
                hold_bits.append(f"Stop <code>₹{stop_px:,.0f}</code> ({stop_pct:+.1f}%)")
            hold_bits.append(f"Trail <b>{trail_pct:.0f}%</b>")
            if expiry:
                hold_bits.append(f"Expires <code>{expiry}</code>")
            lines.append("    " + " · ".join(hold_bits))

    if hold_positions_count == 0:
        lines.append("  <i>No held positions yet.</i>")

    # ── EXITS (§3.7) ────────────────────────────────────────────────────
    exit_rows = []
    if diff_d and diff_d.get("removed"):
        exit_rows = _sold_pnl(diff_d["removed"], db, prev_snap, cur_snap,
                              reg_df, closes, prev_exp, cur_exp, diff_d.get("new"))
    if exit_rows:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔴 <b>EXITS</b>")
        for x in exit_rows:
            arrow = "🟢" if x["pct"] > 0 else "🔴"
            lines.append(f"  <b>{x['sym']}</b> · {x['sector']} · held <b>{x['days']}d</b>")
            lines.append(f"    <code>₹{x['entry']:,.0f} → ₹{x['exit']:,.0f}</code>  "
                         f"{arrow} exit signal <b>{x['pct']:+.1f}%</b>")
            reason = x.get('headline', '') or 'Rotation'
            detail = x.get('detail', '') or ''
            lines.append(f"    ✋ Reason: <b>{reason}</b>")
            if detail:
                lines.append(f"    <i>{detail}</i>")

    # ── WHAT CHANGED (§3.8) ─────────────────────────────────────────────
    narrative = _why_changed_narrative(diff_d, sector_alloc)
    if narrative:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔄 <b>WHAT CHANGED SINCE LAST RUN</b>")
        lines.append(f"  {narrative}")

    # ── RISK SUMMARY (§3.9) ────────────────────────────────────────────
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ <b>RISK SUMMARY</b>")
    if risk["closest_stop"]:
        cs = " · ".join(f"<b>{s}</b> ({d:+.1f}%)" for s, d in risk["closest_stop"])
        lines.append(f"  🔺 Closest to stop: {cs}")
    if risk["closest_target"]:
        ct = " · ".join(f"<b>{s}</b> ({d:+.1f}%)" for s, d in risk["closest_target"])
        lines.append(f"  🎯 Closest to target: {ct}")
    lines.append(f"  Concentration: top-3 = <b>{risk['top3_weight']:.0f}%</b>")

    # ── PORTFOLIO WEIGHTED P&L (unchanged behaviour) ───────────────────
    if port_pcts:
        total_wt = sum(w for _, w in port_pcts)
        port_ret = sum(p * w for p, w in port_pcts) / total_wt if total_wt else 0.0
        arrow_p = "🟢" if port_ret > 0 else ("🔴" if port_ret < 0 else "⚪")
        lines.append(f"  Weighted since entry: {arrow_p} <b>{port_ret:+.1f}%</b> "
                     f"({len(port_pcts)} positions)")

    # ── PERFORMANCE (§3.10) ─────────────────────────────────────────────
    perf_lines = []
    try:
        from india.scorecard import load_scored, headline, rolling_12m
        sr = load_scored()
        if not sr.empty:
            h = headline(sr); r12 = rolling_12m(sr)
            perf_lines.append(f"  <code>Since inception  Wins {h['win_rate']:.0f}% · "
                              f"Median {h['median_ret']:+.1f}%  ({h['scored_recs']} recs)</code>")
            if r12:
                perf_lines.append(f"  <code>1-year          Wins {r12['win_rate']:.0f}% · "
                                  f"Median {r12['median_ret']:+.1f}%   ({r12.get('scored_recs', '?')} recs)</code>")
    except Exception:
        pass
    for lbl, days in [("30D", 30), ("90D", 90)]:
        if lbl in perf_buckets:
            b = perf_buckets[lbl]
            perf_lines.append(f"  <code>{lbl:<15} Wins {b['win_rate']:.0f}% · "
                              f"Median {b['median']:+.1f}%   ({b['n']} recs)</code>")
    if perf_lines:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📈 <b>PERFORMANCE</b>")
        lines.extend(perf_lines)

    # ── FOOTER — INTEGRITY (§3.12) ─────────────────────────────────────
    lines.append(_integrity_footer(asof))
    sid = os.environ.get("AEGIS_SPREADSHEET_ID") or os.environ.get("PRISM_SPREADSHEET_ID")
    if sid:
        lines += ["", f"📈 Live sheet: https://docs.google.com/spreadsheets/d/{sid}"]

    msg = "\n".join(x for x in lines if x is not None)
    msg = _finalize_integrity(msg)
    return msg


def _emit_opportunity(lines, r, sym, sec, strat, db, asof, hold_short):
    """Emit a single NEW opportunity block (OPS001-H §3.5)."""
    try:
        cur_px = float(_val(r, "Current Price", 0))
    except Exception:
        cur_px = 0.0
    try:
        wt = float(_val(r, "Weight %", 0))
    except Exception:
        wt = 0.0
    score = _val(r, "Score /100", "")
    conf = _val(r, "Rec Confidence %", "")
    buy_rng = str(_val(r, "Buy Range", ""))
    tgt_str = str(_val(r, "Hist Target", ""))
    expiry = str(_val(r, "Valid Until", ""))
    review = str(_val(r, "Review Date", ""))
    why = str(_val(r, "Why", ""))
    tgt_pct = _pct_from_current(cur_px, tgt_str)
    stop_px, stop_pct = _derive_stop_price(cur_px if cur_px > 0 else 0, buy_rng)

    lines.append("")
    lines.append(f"🟢 <b>{sym} · {sec}</b> · NEW · Grade <b>{_grade(score)}</b> ({score}/100)")
    if cur_px > 0:
        lines.append(f"    Now <code>₹{cur_px:,.0f}</code> · Buy <code>{buy_rng}</code> · Weight <b>{wt:.0f}%</b>")
    if tgt_str and tgt_str.replace(".", "", 1).isdigit() and tgt_pct is not None:
        lines.append(f"    🎯 Target <code>₹{float(tgt_str):,.0f}</code> ({tgt_pct:+.1f}%) · Hold <b>{hold_short}</b>")
    if stop_px:
        lines.append(f"    ⛔ Stop <code>₹{stop_px:,.0f}</code> ({stop_pct:+.1f}%) · Trail <b>3%</b>")
    if expiry or review:
        parts = []
        parts.append("Age <code>0d</code>")
        if expiry:
            parts.append(f"Expires <code>{expiry}</code>")
        if review:
            parts.append(f"Review <code>{review}</code>")
        lines.append(f"    📅 " + " · ".join(parts))
    ev = _evidence(score, conf)
    if ev:
        lines.append(f"    📊 <i>Confidence {conf}% ({ev})</i>")
    if why:
        why_short = why[:200] + ("…" if len(why) > 200 else "")
        lines.append(f"    💡 <i>{why_short}</i>")


def _chunk_at_sections(text, max_len=3900):
    """Split at section boundaries (blank lines or ═══ headers) if the message exceeds Telegram's cap.
    Telegram allows 4096 chars per message; 3900 leaves headroom for HTML tag padding + emoji width."""
    if len(text) <= max_len:
        return [text]
    chunks, cur, cur_len = [], [], 0
    for line in text.split("\n"):
        add = len(line) + 1
        if cur_len + add > max_len and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [line], add
        else:
            cur.append(line); cur_len += add
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (.env.telegram) — cannot send.")
        return False
    chunks = _chunk_at_sections(text)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok_all = True
    for i, chunk in enumerate(chunks, 1):
        data = urllib.parse.urlencode({
            "chat_id": chat, "text": chunk[:4090],
            "parse_mode": "HTML", "disable_web_page_preview": "true",
        }).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=20) as resp:
                ok = json.loads(resp.read()).get("ok", False)
            ok_all = ok_all and ok
            if not ok:
                print(f"  Telegram API returned not-ok on chunk {i}/{len(chunks)}.")
        except Exception as e:
            print(f"  send failed on chunk {i}/{len(chunks)}: {e}")
            return False
    print(f"  sent ({len(chunks)} message{'s' if len(chunks) > 1 else ''}).")
    return ok_all


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")     # let the Windows console print emoji in --check
    except Exception:
        pass
    load_env()
    if "--resolve" in sys.argv:
        resolve_chat_id(); return
    msg = build_message()
    if "--check" in sys.argv:
        have = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        print("  config:", "READY" if have else "MISSING TELEGRAM_BOT_TOKEN/CHAT_ID in .env.telegram")
        print("  --- message preview ---")
        # strip HTML for terminal preview
        preview = re.sub(r"</?b>", "", msg)
        preview = re.sub(r"</?i>", "", preview)
        print(preview)
    else:
        send(msg)


if __name__ == "__main__":
    main()
