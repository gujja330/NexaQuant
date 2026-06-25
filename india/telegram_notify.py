# india/telegram_notify.py
"""
TELEGRAM DAILY NOTIFIER — push a concise AEGIS summary to your phone each morning.

Reads today's canonical recommendations (data/aegis_today.csv) + the recommendation DB diff, and sends
one clean message via the Telegram Bot API. Presentation only — no new logic, no secrets in code.

SECURITY: never hard-code the token. Put it in a git-ignored .env.telegram (matched by .env* in
.gitignore):
    TELEGRAM_BOT_TOKEN = 123456:ABC...           (from @BotFather)
    TELEGRAM_CHAT_ID   = 12345678                (your chat id; get it from @userinfobot)
Optional: AEGIS_SPREADSHEET_ID -> appends a link to the live Google Sheet.

Run:  python india/telegram_notify.py            # send today's summary
      python india/telegram_notify.py --check    # validate config + print the message (no send)
"""
import os, sys, re, json, glob, urllib.parse, urllib.request, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
CANON = ROOT / "data" / "aegis_today.csv"


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
    import re
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


EMOJI = {"STRONG BUY": "🟢", "BUY": "🔵", "ACCUMULATE": "🟡", "WATCH": "⚪"}


def _val(r, key, default=""):
    v = r.get(key, default)
    return default if (v is None or (isinstance(v, float) and pd.isna(v))) else v


def build_message():
    if not CANON.exists():
        return "AEGIS: no recommendations file yet (run recommendation_generator.py)."
    t = pd.read_csv(CANON)
    if t.empty:
        return "AEGIS: no recommendations today."
    try:
        from india.confidence_engine import current_regime
        exp, regime, _ = current_regime()
        regime_line = f"Regime <b>{regime}</b> · deploy <b>{exp:.0%}</b> · cash {1-exp:.0%}"
    except Exception:
        regime_line = ""
    asof = str(_val(t.iloc[0], "Generated"))
    hold = str(_val(t.iloc[0], "Recommended Holding"))
    n_buy = int((t["Strength"].isin(["STRONG BUY", "BUY"])).sum()) if "Strength" in t else len(t)

    lines = [f"📊 <b>AEGIS Daily</b> · {asof}", regime_line,
             f"{len(t)} holdings · {n_buy} buy-rated · horizon {hold} · sorted best-first", ""]

    last_tier = None
    for i, (_, r) in enumerate(t.iterrows(), 1):
        strat = str(_val(r, "Strength"))
        if strat != last_tier:                                  # group header per strength tier
            lines.append(f"{EMOJI.get(strat, '▫️')} <b>{strat}</b>")
            last_tier = strat
        px = _val(r, "Current Price"); rng = str(_val(r, "Expected Range (hist)"))
        hm = re.search(r"\(([^)]+)\)", str(_val(r, "Recommended Holding")))
        hold_short = hm.group(1) if hm else str(_val(r, "Recommended Holding"))
        l1 = f"  <b>{_val(r,'Stock')}</b> · {_val(r,'Sector')} · hold {hold_short}"
        bits = [f"₹{px}", f"buy {_val(r,'Buy Range')}",
                f"score {_val(r,'Score /100')}", f"conf {_val(r,'Rec Confidence %')}%",
                f"{_val(r,'Weight %')}% (₹{_val(r,'Allocation Rs')})"]
        tgt = str(_val(r, "Hist Target"))
        if tgt.replace(".", "", 1).isdigit():                   # numeric target only when >=5 analogues
            bits.insert(2, f"tgt ₹{tgt} in {hold_short}")
        if "to" in rng:                                         # expected range, tied to the period
            bits.insert(3 if tgt.replace('.', '', 1).isdigit() else 2, f"exp {rng} over {hold_short}")
        lines.append(l1)
        lines.append("    " + " · ".join(str(b) for b in bits))

    try:
        from india.recommendation_db import load_db, daily_diff
        d = daily_diff(load_db())
        if d and not d.get("note"):
            ch = []
            if d["new"]:
                ch.append("➕ " + ", ".join(d["new"]))
            if d["removed"]:
                ch.append("➖ " + ", ".join(d["removed"]))
            if ch:
                lines += ["", "<b>Changes since last run</b>", "  " + " · ".join(ch)]
    except Exception:
        pass

    sid = os.environ.get("AEGIS_SPREADSHEET_ID") or os.environ.get("PRISM_SPREADSHEET_ID")
    if sid:
        lines += ["", f"📈 Live sheet: https://docs.google.com/spreadsheets/d/{sid}"]
    lines += ["", "<i>Historical evidence, not a forecast. Portfolio process validated; "
              "individual stock selection experimental.</i>"]
    return "\n".join(x for x in lines if x is not None)


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (.env.telegram) — cannot send.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000],
                                   "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as resp:
            ok = json.loads(resp.read()).get("ok", False)
        print("  sent." if ok else "  Telegram API returned not-ok.")
        return ok
    except Exception:
        print("  send failed (network or bad token/chat_id).")
        return False


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")     # let the Windows console print emoji in --check
    except Exception:
        pass
    load_env()
    msg = build_message()
    if "--resolve" in sys.argv:
        resolve_chat_id(); return
    if "--check" in sys.argv:
        have = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        print("  config:", "READY" if have else "MISSING TELEGRAM_BOT_TOKEN/CHAT_ID in .env.telegram")
        print("  --- message preview ---")
        print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    else:
        send(msg)


if __name__ == "__main__":
    main()
