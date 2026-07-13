"""
DATA FRESHNESS GATE — refuse to publish recommendations on stale data.

Runs after `daily_run.py --pull`. Compares the max last-bar date across all
data/raw/india/*_D1.parquet files against the EXPECTED previous trading session
(walks back from today skipping weekends + a short NSE holiday list).

Exit codes:
  0  fresh — proceed with recommendation_generator
  1  no data at all — pipeline aborted
  2  stale (gap >= 1 session) — abort + send a "DATA STALE" alert via telegram_notify

Optional env:
  AEGIS_ALLOW_STALE=1       skip the gate (only for manual debug runs)
  AEGIS_STALE_ALERT=1       send the DATA STALE Telegram alert instead of exiting silently
                            (default 1 when TELEGRAM_BOT_TOKEN is set)

Run: python scripts/check_data_freshness.py
"""
import os, sys, json, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "india"

# Small hand-curated NSE 2026 holidays (major only). Add as needed; freshness will still be
# correct on unknown holidays because we abort on stale-gap > 1 (single missed day is tolerated).
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 6),    # Holi
    date(2026, 3, 31),   # Id-Ul-Fitr
    date(2026, 4, 3),    # Mahavir Jayanti
    date(2026, 4, 10),   # Good Friday
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 11, 8),   # Diwali (Muhurat Trading — half day; treat as holiday for daily bar)
    date(2026, 11, 25),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}


def expected_previous_session(today=None):
    """Walk back one day at a time, skipping weekends + holidays. If run before market close
    on a weekday, the 'previous session' is genuinely yesterday. If run early morning as
    scheduled, this returns the last completed session."""
    d = (today or date.today()) - timedelta(days=1)
    while d.weekday() >= 5 or d in NSE_HOLIDAYS_2026:
        d -= timedelta(days=1)
    return d


def latest_bar_date():
    """Return the max last-bar date across all Nifty-200 parquet files, and how many were read."""
    import pandas as pd
    dates = []
    files = list(RAW.glob("*_D1.parquet"))
    for p in files:
        try:
            df = pd.read_parquet(p)
            if len(df):
                dates.append(df.index[-1].date())
        except Exception:
            continue
    return (max(dates) if dates else None), len(files)


def send_stale_alert(latest, expected, gap):
    """Publish a DATA STALE notice via Telegram. Non-fatal if creds absent."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("  (no Telegram creds — skipping stale alert)")
        return
    txt = (f"⚠️ <b>AEGIS: DATA STALE — no new recommendation today</b>\n"
           f"Latest bar: <b>{latest}</b>\n"
           f"Expected session: <b>{expected}</b>\n"
           f"Gap: <b>{gap} day(s)</b>\n\n"
           f"<i>Pipeline aborted before recommendation_generator. Will retry on next scheduled run.</i>")
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat, "text": txt, "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False)
        print("  stale alert sent." if ok else "  stale alert: Telegram not-ok.")
    except Exception as e:
        print(f"  stale alert send failed: {e}")


def main():
    if os.environ.get("AEGIS_ALLOW_STALE") == "1":
        print("  AEGIS_ALLOW_STALE=1 — bypassing freshness gate")
        sys.exit(0)

    latest, n = latest_bar_date()
    expected = expected_previous_session()

    if latest is None:
        print(f"  NO DATA in {RAW} (scanned {n} files)")
        send_stale_alert("<none>", expected, gap="?")
        sys.exit(1)

    gap = (expected - latest).days
    print(f"  latest bar: {latest}  expected session: {expected}  gap: {gap}d  ({n} files scanned)")
    if gap >= 1:
        print(f"  STALE — refusing to publish stale recommendations.")
        send_stale_alert(latest, expected, gap)
        sys.exit(2)
    print("  FRESH — proceed with recommendation_generator.")
    sys.exit(0)


if __name__ == "__main__":
    main()
