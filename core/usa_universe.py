# core/usa_universe.py
"""
USA DYNAMIC UNIVERSE — the engine decides the tradable set; never a hardcoded 40/100/500.

Pipeline (mirrors India's filter-built universe, with USA's free official source):
  NASDAQ Trader listing files (all NYSE + NASDAQ + AMEX)
    -> common stocks only        (drop ETFs, test issues, preferred / warrants / units / ADRs / notes)
    -> liquidity screen           (avg daily $-volume, price floor, recent history)
    -> ranked, cached -> data/raw/usa/universe.csv

Market-cap filtering needs shares outstanding (arrives with SEC fundamentals, Phase 4); until then
average dollar-volume is the size/tradability proxy. The full screen is a periodic batch (membership
changes slowly); daily runs read the cached universe.

Run:  python -m core.usa_universe --candidates        # show the common-stock candidate pool (fast)
      python -m core.usa_universe --build [--max N]    # liquidity-screen + cache the universe
"""
import sys, re, io, csv, glob, urllib.request, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
NASDAQ = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
OUT = ROOT / "data" / "raw" / "usa" / "universe.csv"
EXCLUDE = re.compile(r"warrant|preferred|depositary|\bright\b|\bunit(s)?\b|\bnote(s)?\b|debenture|"
                     r"\bETN\b|\bADR\b|\bADS\b|when[- ]issued|%|convertible|trust\b", re.I)
from markets.usa.config import MIN_PRICE, MIN_DOLLAR_VOL, MIN_DAYS    # single source of truth


def _read(url):
    return urllib.request.urlopen(url, timeout=30).read().decode("latin-1")


def fetch_candidates():
    """All common stocks across NYSE/NASDAQ/AMEX (ETFs, test issues, non-common types removed)."""
    syms = {}
    for sym, name, etf, test in _rows():
        if etf == "Y" or test == "Y":
            continue
        if not re.fullmatch(r"[A-Z]{1,5}", sym):          # plain tickers only (drops $, ., warrants suffixes)
            continue
        if EXCLUDE.search(name or ""):
            continue
        syms[sym] = name
    return dict(sorted(syms.items()))


def _rows():
    # nasdaqlisted: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot|ETF|NextShares
    for r in csv.reader(io.StringIO(_read(NASDAQ)), delimiter="|"):
        if len(r) >= 7 and r[0] not in ("Symbol", "") and not r[0].startswith("File"):
            yield r[0].strip(), r[1], r[6].strip(), r[3].strip()
    # otherlisted: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot|Test Issue|NASDAQ Symbol
    for r in csv.reader(io.StringIO(_read(OTHER)), delimiter="|"):
        if len(r) >= 7 and r[0] not in ("ACT Symbol", "") and not r[0].startswith("File"):
            yield r[0].strip(), r[1], r[4].strip(), r[6].strip()


def screen(cands, max_n=None):
    import yfinance as yf
    syms = list(cands)[:max_n] if max_n else list(cands)
    keep = []
    for i in range(0, len(syms), 60):
        batch = syms[i:i + 60]
        try:
            data = yf.download(batch, period="3mo", group_by="ticker", progress=False,
                               auto_adjust=False, threads=True)
        except Exception:
            continue
        for s in batch:
            try:
                sub = data[s] if isinstance(data.columns, pd.MultiIndex) else data
                sub = sub.dropna(how="all")
                if len(sub) < MIN_DAYS:
                    continue
                px = float(sub["Close"].iloc[-1])
                dvol = float((sub["Close"] * sub["Volume"]).tail(60).mean())
                if px >= MIN_PRICE and dvol >= MIN_DOLLAR_VOL:
                    keep.append({"symbol": s, "name": cands[s][:40], "price": round(px, 2),
                                 "avg_dollar_vol_musd": round(dvol / 1e6), "days": len(sub)})
            except Exception:
                pass
    df = pd.DataFrame(keep).sort_values("avg_dollar_vol_musd", ascending=False).reset_index(drop=True)
    return df


def load_universe():
    if OUT.exists():
        return pd.read_csv(OUT)["symbol"].tolist()
    return []


def main():
    cands = fetch_candidates()
    if "--candidates" in sys.argv:
        print(f"  common-stock candidates (NYSE+NASDAQ+AMEX, ex-ETF/test/preferred/ADR): {len(cands)}")
        print("  sample:", list(cands)[:12])
        return
    if "--build" in sys.argv:
        max_n = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else None
        print(f"  screening {max_n or len(cands)} of {len(cands)} candidates for liquidity "
              f"(price>=${MIN_PRICE:.0f}, $vol>=${MIN_DOLLAR_VOL/1e6:.0f}M/day)...")
        uni = screen(cands, max_n=max_n)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        uni.to_csv(OUT, index=False)
        print(f"  dynamic universe: {len(uni)} liquid common stocks -> {OUT.relative_to(ROOT)}")
        if len(uni):
            print(uni.head(12).to_string(index=False))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
