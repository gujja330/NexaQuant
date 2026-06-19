# india/broker_angelone.py
"""
Angel One SmartAPI adapter (FREE) — auth + clean historical data pull (+ order placement later).
This unlocks the AI refinement: clean Nifty-200 history (vs flaky yfinance) and live execution.

SETUP (once, on your PC):
    pip install smartapi-python pyotp
    # Create an app at https://smartapi.angelbroking.com -> get API Key.
    # Enable TOTP (save the secret string when it shows the QR).
    setx ANGEL_API_KEY      "your_api_key"        # (Windows; or export on Linux)
    setx ANGEL_CLIENT_CODE  "your_client_code"
    setx ANGEL_PIN          "your_mpin"
    setx ANGEL_TOTP_SECRET  "your_totp_secret"

RUN:
    python india/broker_angelone.py --check            # auth + print profile/funds (no trades)
    python india/broker_angelone.py --pull             # download clean DAILY history -> data/raw/india/
    python india/broker_angelone.py --pull --interval ONE_HOUR --days 365   # intraday history

Saves to data/raw/india/<SYM>_D1.parquet (same format as yfinance) so the engine auto-uses the
cleaner Angel data. Orders are NOT placed here (paper/live runner comes next, after validation).
"""
import argparse, os, sys, time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.data_nse import UNIVERSE
RAW = ROOT / "data" / "raw" / "india"
RAW.mkdir(parents=True, exist_ok=True)
SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


def _load_dotenv():
    """Load credentials from a .env.angel (or .env) file in the repo root — no PowerShell needed.
    Lines like  ANGEL_API_KEY=xxxx . Existing real env vars take priority. File is git-ignored."""
    for name in (".env.angel", ".env"):
        p = ROOT / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        print(f"  loaded credentials from {name}")
        return


def connect():
    """Authenticate to SmartAPI (TOTP-based). Returns the SmartConnect session object."""
    _load_dotenv()
    try:
        from SmartApi import SmartConnect
        import pyotp
    except ImportError as e:
        sys.exit(f"Missing dep: {e}. Run:  pip install smartapi-python pyotp logzero websocket-client")
    for v in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET"):
        if not os.environ.get(v):
            sys.exit(f"Set {v} (see the setup notes at the top of this file).")
    obj = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
    totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
    sess = obj.generateSession(os.environ["ANGEL_CLIENT_CODE"], os.environ["ANGEL_PIN"], totp)
    if not sess.get("status"):
        sys.exit(f"Login failed: {sess.get('message', sess)}")
    print(f"  connected: client={os.environ['ANGEL_CLIENT_CODE']}")
    return obj


def nse_tokens(symbols):
    """Resolve plain symbols (e.g. RELIANCE) -> Angel NSE-equity tokens via the scrip master."""
    import requests
    master = requests.get(SCRIP_URL, timeout=90).json()
    by_name = {}
    for it in master:
        if it.get("exch_seg") == "NSE" and str(it.get("symbol", "")).endswith("-EQ"):
            by_name[it["symbol"][:-3]] = it["token"]
    return {s: by_name.get(s) for s in symbols}


def _get_candles_retry(obj, params, tries=6):
    """One historical call with backoff on Angel's 'exceeding access rate' throttle.
    The historical endpoint is strict (~1 req every ~1s+); on a rate error we wait
    progressively longer (2,4,8,16,32s) and retry instead of losing the chunk."""
    delay = 2.0
    for attempt in range(tries):
        try:
            r = obj.getCandleData(params)
            # SmartAPI returns the rate error in the JSON body, not as an exception
            msg = str(r.get("message", "")) if isinstance(r, dict) else str(r)
            if "exceeding access rate" in msg.lower() or "access denied" in msg.lower():
                raise RuntimeError(msg or "access rate")
            return r.get("data") if isinstance(r, dict) else None
        except Exception as e:
            if attempt == tries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 32)
    return None


def candles(obj, token, interval="ONE_DAY", days=2000):
    """Pull historical candles (chunked to respect API range limits). Returns OHLCV DataFrame."""
    end = datetime.now()
    start = end - timedelta(days=days)
    step = 100 if interval != "ONE_DAY" else 1500     # per-call span (bars/days) limits vary
    frames, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=step), end)
        try:
            data = _get_candles_retry(obj, {"exchange": "NSE", "symboltoken": token, "interval": interval,
                                            "fromdate": cur.strftime("%Y-%m-%d %H:%M"),
                                            "todate": nxt.strftime("%Y-%m-%d %H:%M")})
            for c in (data or []):
                frames.append(c)
        except Exception as e:
            print(f"    ! chunk {cur.date()}: {e}")
        time.sleep(1.2)                                # historical endpoint is strict — go slow
        cur = nxt
    if not frames:
        return None
    df = pd.DataFrame(frames, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
    return df.drop_duplicates("time").set_index("time").sort_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="auth + print profile/funds, no data")
    ap.add_argument("--pull", action="store_true", help="download history for the universe")
    ap.add_argument("--interval", default="ONE_DAY", help="ONE_DAY | ONE_HOUR | FIFTEEN_MINUTE ...")
    ap.add_argument("--days", type=int, default=2000)
    ap.add_argument("--symbols", nargs="+", default=None)
    a = ap.parse_args()
    obj = connect()

    if a.check:
        prof = obj.getProfile(obj.refreshToken) if hasattr(obj, "refreshToken") else {}
        try:
            funds = obj.rmsLimit()
            print(f"  available cash: {funds.get('data', {}).get('availablecash')}")
        except Exception as e:
            print(f"  (funds read skipped: {e})")
        print("  AUTH OK — ready to pull data / trade. (No order placed.)")
        return

    if a.pull:
        syms = a.symbols or [s.replace(".NS", "").replace("^", "") for s in UNIVERSE if not s.startswith("^")]
        toks = nse_tokens(syms)
        suffix = {"ONE_DAY": "D1", "ONE_HOUR": "H1", "FIFTEEN_MINUTE": "M15", "FIVE_MINUTE": "M5"}.get(a.interval, "D1")
        ok = 0
        for s in syms:
            tk = toks.get(s)
            if not tk:
                print(f"  ! {s}: no NSE token"); continue
            df = candles(obj, tk, a.interval, a.days)
            if df is None or len(df) < 50:
                print(f"  ! {s}: low/no data"); continue
            df["tick_volume"] = df["volume"]; df["spread"] = 0.0
            out = RAW / (f"{s}_{suffix}.parquet" if suffix == "D1" else f"intraday/{s}_{suffix}.parquet")
            out.parent.mkdir(parents=True, exist_ok=True)
            df[["open", "high", "low", "close", "tick_volume", "spread"]].to_parquet(out)
            ok += 1
            print(f"  {s:<12}{len(df):>6} bars  {df.index[0].date()} -> {df.index[-1].date()}")
        print(f"\n  pulled {ok}/{len(syms)} symbols ({a.interval}). Re-run india/picker_pro.py to use the clean data.")


if __name__ == "__main__":
    main()
