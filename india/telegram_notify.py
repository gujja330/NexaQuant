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
import os, sys, json, glob, urllib.parse, urllib.request, warnings
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


def build_message():
    if not CANON.exists():
        return "AEGIS: no recommendations file yet (run recommendation_generator.py)."
    t = pd.read_csv(CANON)
    try:
        from india.confidence_engine import current_regime
        exp, regime, _ = current_regime()
        head_regime = f"{regime} regime · deploy {exp:.0%}"
    except Exception:
        head_regime = ""
    asof = str(t["Generated"].iloc[0]) if "Generated" in t and len(t) else ""
    lines = [f"<b>AEGIS — {asof}</b>", head_regime, ""]
    for _, r in t.head(12).iterrows():
        rng = r.get("Expected Range (hist)", "—")
        lines.append(f"<b>{r.get('Strength','')}</b>  {r.get('Stock','')} "
                     f"({r.get('Sector','')})  buy {r.get('Buy Range','')}  "
                     f"exp {rng}  conf {r.get('Rec Confidence %','')}%")
    # what changed since last run
    try:
        from india.recommendation_db import load_db, daily_diff
        d = daily_diff(load_db())
        if d and not d.get("note"):
            lines += ["", f"<b>Changes:</b> +{d['new'] or '—'}  -{d['removed'] or '—'}"]
    except Exception:
        pass
    sid = os.environ.get("AEGIS_SPREADSHEET_ID")
    if sid:
        lines += ["", f"Live sheet: https://docs.google.com/spreadsheets/d/{sid}"]
    lines += ["", "<i>Historical evidence, not a forecast. Stock selection experimental.</i>"]
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
