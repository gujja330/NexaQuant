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
import os, sys, re, json, urllib.parse, urllib.request, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
CANON = ROOT / "data" / "aegis_today.csv"
DB_PATH = ROOT / "data" / "aegis_recommendation_db.csv"
REG_PATH = ROOT / "data" / "aegis_registry.csv"


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

    lines = []
    header_bits = [f"📊 <b>AEGIS Daily</b> · {asof}"]
    if prof:
        header_bits.append(prof)
    lines.append(" · ".join(header_bits))
    if regime and cur_exp is not None:
        lines.append(f"{regime} market · Deploy <b>{cur_exp:.0%}</b> · Keep {1-cur_exp:.0%} cash · Horizon {hold_short}")
    n_buy = int((t["Strength"].isin(["STRONG BUY", "BUY"])).sum()) if "Strength" in t else len(t)
    lines.append(f"<b>{len(t)} stocks</b> · {n_buy} buy-rated · sorted best-first")
    lines.append("")
    lines.append("═══ YOUR STOCKS ═══")

    # weighted portfolio return accumulator (skip NEW positions — they have no move yet)
    port_pcts = []  # list of (pct, weight)

    last_tier = None
    for _, r in t.iterrows():
        strat = str(_val(r, "Strength"))
        if strat != last_tier:
            lines.append("")
            lines.append(f"{TIER_EMOJI.get(strat, '▫️')} <b>{strat}</b> — {TIER_HEAD.get(strat, '')}")
            last_tier = strat

        sym = str(_val(r, "Stock"))
        sec = str(_val(r, "Sector"))
        try:
            cur_px = float(_val(r, "Current Price"))
        except Exception:
            cur_px = 0.0
        try:
            wt = float(_val(r, "Weight %"))
        except Exception:
            wt = 0.0
        score = _val(r, "Score /100")
        conf = _val(r, "Rec Confidence %")
        buy_rng = str(_val(r, "Buy Range"))
        info = _entry_info(sym, db, asof)

        # Line 1: symbol · sector · status
        if info is None or info["days"] == 0 or info["price"] <= 0:
            lines.append(f"  <b>{sym}</b> · {sec} · <i>NEW today</i>")
        else:
            lines.append(f"  <b>{sym}</b> · {sec} · held {info['days']} days")

        # Line 2: price move (only when we have a real entry)
        if info and info["price"] > 0 and info["days"] > 0 and cur_px > 0:
            pct = (cur_px - info["price"]) / info["price"] * 100
            rp = cur_px - info["price"]
            arrow = "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")
            lines.append(f"    ₹{info['price']:,.0f} → ₹{cur_px:,.0f}  {arrow} <b>{pct:+.1f}%</b> ({rp:+,.0f}/share)")
            if wt > 0:
                port_pcts.append((pct, wt))
        elif cur_px > 0:
            lines.append(f"    Now ₹{cur_px:,.0f}")

        # Line 3: enter zone · capital · grade · evidence
        bits3 = [f"Enter {buy_rng}", f"{wt:.0f}% of capital", f"Grade {_grade(score)} ({score}/100)"]
        ev = _evidence(score, conf)
        if ev:
            bits3.append(ev)
        lines.append("    " + " · ".join(bits3))

        # Line 4 (optional): target / expected range only when we have real evidence (>=5 cases)
        tgt = str(_val(r, "Hist Target"))
        if tgt.replace(".", "", 1).isdigit():
            rng = str(_val(r, "Expected Range (hist)"))
            exp_str = ""
            if "to" in rng:
                rng_clean = rng.split("(")[0].strip()
                exp_str = f", {hold_short} range {rng_clean}"
            lines.append(f"    Target ₹{tgt} in {hold_short}{exp_str}")

        # Line 5: verdict
        if info is None or info["days"] == 0:
            verdict = "→ <b>NEW BUY</b>"
        elif strat == "WATCH":
            verdict = "→ <b>TRIM</b> if held (below buy threshold)"
        else:
            verdict = "→ <b>HOLD</b>"
        lines.append(f"    {verdict}")

    # Portfolio-level P&L rollup (weighted, held positions only)
    if port_pcts:
        total_wt = sum(w for _, w in port_pcts)
        port_ret = sum(p * w for p, w in port_pcts) / total_wt if total_wt else 0.0
        arrow_p = "🟢" if port_ret > 0 else ("🔴" if port_ret < 0 else "⚪")
        lines.append("")
        lines.append("═══ HELD POSITIONS SO FAR ═══")
        lines.append(f"  Weighted avg since entry: {arrow_p} <b>{port_ret:+.1f}%</b>  "
                     f"({len(port_pcts)} positions with history)")

    # SOLD section — classified exits, not naive "SELL NOW"
    if diff_d and diff_d.get("removed"):
        pnl_rows = _sold_pnl(diff_d["removed"], db, prev_snap, cur_snap,
                             reg_df, closes, prev_exp, cur_exp, diff_d.get("new"))
        if pnl_rows:
            lines.append("")
            lines.append("═══ EXITS (signals — book only if you executed) ═══")
            for x in pnl_rows:
                arrow = "🟢" if x["pct"] > 0 else "🔴"
                lines.append(f"  {x['emoji']} <b>{x['sym']}</b> · {x['sector']} · held {x['days']} days")
                lines.append(f"    ₹{x['entry']:,.0f} → ₹{x['exit']:,.0f}  {arrow} exit signal <b>{x['pct']:+.1f}%</b>")
                lines.append(f"    {x['headline']}: {x['detail']}")

    # Other changes (adds / weight moves / sector rotation)
    if diff_d and not diff_d.get("note"):
        change_lines = []
        if diff_d.get("new"):
            change_lines.append("➕ Added today: " + ", ".join(diff_d["new"]))
        if diff_d.get("increased"):
            change_lines.append("⬆ Weight up: " + "; ".join(diff_d["increased"][:4]))
        if diff_d.get("reduced"):
            change_lines.append("⬇ Weight down: " + "; ".join(diff_d["reduced"][:4]))
        if diff_d.get("rotation"):
            change_lines.append("🔄 Sector shift: " + ", ".join(diff_d["rotation"][:6]))
        if change_lines:
            lines.append("")
            lines.append("═══ OTHER CHANGES vs last run ═══")
            for c in change_lines:
                lines.append("  " + c)

    # Track record from the frozen backtest evidence (source==historical, quarantined)
    try:
        from india.scorecard import load_scored, headline, rolling_12m
        sr = load_scored()
        if not sr.empty:
            h = headline(sr); r12 = rolling_12m(sr)
            lines.append("")
            lines.append("═══ TRACK RECORD ═══")
            tr = (f"  Wins: <b>{h['win_rate']:.0f}%</b> closed positive · Typical <b>{h['median_ret']:+.1f}%</b> "
                  f"median ({h['scored_recs']} scored)")
            if r12:
                tr += f" · 12M win {r12['win_rate']:.0f}%"
            lines.append(tr)
    except Exception:
        pass

    sid = os.environ.get("AEGIS_SPREADSHEET_ID") or os.environ.get("PRISM_SPREADSHEET_ID")
    if sid:
        lines += ["", f"📈 Live sheet: https://docs.google.com/spreadsheets/d/{sid}"]
    lines += ["", "<i>Signals only. Book P&L reflects only what your paper/live portfolio executes.</i>",
              "<i>Historical evidence, not a forecast. Portfolio process validated; individual selection experimental.</i>"]
    return "\n".join(x for x in lines if x is not None)


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
