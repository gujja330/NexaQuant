# core/market_adapter.py
"""
MARKET ADAPTER — the seam that lets ONE engine serve MANY markets.

Every market provides the same five things; the engine never knows which country it is looking at:

    adapter.get_market_data()  -> (closes, highs, lows, vols, idx, vix)   aligned daily panels
    adapter.get_universe()     -> [symbols]                                liquid, tradable names
    adapter.get_index()        -> pd.Series                                benchmark close
    adapter.get_sector(sym)    -> str
    adapter.get_calendar()     -> pd.DatetimeIndex                         trading days

- IndiaAdapter is a NON-INVASIVE wrapper over the FROZEN india/ code (load_panels, build_universe,
  sector_of). It moves nothing; India production is untouched.
- USAAdapter is NEW: S&P/Nasdaq mega-caps via yfinance, ^GSPC index, ^VIX, a sector map. Data is cached
  under data/raw/usa/ in the same schema as India so the same engine code can consume it.

This is Phase-0 of the parallel USA build: prove one interface serves both markets before any USA
recommendations are generated (paper mode comes next).
"""
import sys, glob, warnings
from abc import ABC, abstractmethod
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")


class MarketAdapter(ABC):
    name = "abstract"

    @abstractmethod
    def get_market_data(self): ...
    @abstractmethod
    def get_universe(self): ...
    @abstractmethod
    def get_index(self): ...
    @abstractmethod
    def get_sector(self, symbol): ...
    @abstractmethod
    def get_calendar(self): ...


# ----------------------------- INDIA (wraps frozen code) -----------------------------
class IndiaAdapter(MarketAdapter):
    name = "india"

    def __init__(self):
        self._md = None

    def get_market_data(self):
        if self._md is None:            # memoize — load panels once per adapter instance
            from india.feature_engine import load_panels
            self._md = load_panels()    # (closes, highs, lows, vols, idx, vix, spx)
        return self._md

    def get_universe(self):
        from india.universe import build_universe
        c, _, _, v, _, _, _ = self.get_market_data()
        return build_universe(c, v)

    def get_index(self):
        return self.get_market_data()[4]

    def get_sector(self, symbol):
        from india.sectors import sector_of
        return sector_of(symbol)

    def get_calendar(self):
        return self.get_market_data()[0].index


# ----------------------------- USA (new adapter) -----------------------------
from markets.usa import config as USA          # USA market config (markets/usa/config.py)
USA_INDEX, USA_VIX = USA.INDEX_TICKER, USA.VIX_TICKER
RAW_USA = ROOT / "data" / "raw" / "usa"


def _to_schema(df):
    """Yahoo OHLCV -> the AEGIS panel schema (lowercase + tick_volume + spread, naive date index)."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    idx = pd.to_datetime(df.index)
    try:
        idx = idx.tz_localize(None)
    except Exception:
        idx = idx.tz_convert(None) if getattr(idx, "tz", None) is not None else idx
    out = pd.DataFrame(index=idx.normalize()); out.index.name = "time"
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(df.get(c), errors="coerce")
    out["tick_volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0).astype("int64")
    out["spread"] = 0.0
    return out.dropna(subset=["close"])


class USAAdapter(MarketAdapter):
    name = "usa"

    def __init__(self):
        # use the dynamic universe if it's been built+cached, else the starter mega-caps
        from core.usa_universe import load_universe
        from core.usa_sectors import load_sectors
        uni = load_universe()
        self.symbols = uni if uni else sorted(USA.SECTORS)
        self._md = None
        self._sectors = load_sectors()          # load the sector map ONCE (not per get_sector call)

    def download(self, period="5y"):
        """Fetch + cache OHLCV for the universe + index + VIX into data/raw/usa/ (AEGIS schema)."""
        import yfinance as yf
        RAW_USA.mkdir(parents=True, exist_ok=True)
        tickers = self.symbols + [USA_INDEX, USA_VIX]
        data = yf.download(tickers, period=period, group_by="ticker", progress=False,
                           auto_adjust=False, threads=True)
        saved = 0
        for tkr in tickers:
            try:
                sub = data[tkr] if isinstance(data.columns, pd.MultiIndex) else data
                df = _to_schema(sub.dropna(how="all"))
                if df.empty:
                    continue
                fname = {USA_INDEX: "SPX", USA_VIX: "USVIX"}.get(tkr, tkr)
                df.to_parquet(RAW_USA / f"{fname}_D1.parquet"); saved += 1
            except Exception:
                pass
        return saved

    def _load(self):
        files = sorted(glob.glob(str(RAW_USA / "*_D1.parquet")))
        if not files:
            self.download()
            files = sorted(glob.glob(str(RAW_USA / "*_D1.parquet")))
        return {Path(f).stem.replace("_D1", ""): pd.read_parquet(f).sort_index() for f in files}

    def get_market_data(self):
        if self._md is not None:
            return self._md
        d = self._load()
        stocks = [s for s in d if s not in ("SPX", "USVIX")]
        closes = pd.DataFrame({s: d[s]["close"] for s in stocks}).sort_index()
        highs = pd.DataFrame({s: d[s]["high"] for s in stocks}).reindex(closes.index)
        lows = pd.DataFrame({s: d[s]["low"] for s in stocks}).reindex(closes.index)
        vols = pd.DataFrame({s: d[s]["tick_volume"] for s in stocks}).reindex(closes.index)
        idx = d["SPX"]["close"].reindex(closes.index).ffill() if "SPX" in d else closes.mean(axis=1)
        vix = d["USVIX"]["close"].reindex(closes.index).ffill() if "USVIX" in d else None
        self._md = (closes, highs, lows, vols, idx, vix, None)      # memoize
        return self._md

    def get_universe(self):
        c, _, _, v, _, _, _ = self.get_market_data()
        turn = (c * v).tail(120).mean()
        return sorted(turn[turn > 0].index)        # all our mega-caps are liquid; filter is a formality here

    def get_index(self):
        return self.get_market_data()[4]

    def get_sector(self, symbol):
        return self._sectors.get(symbol) or USA.SECTORS.get(symbol, "Other")  # cached in __init__

    def get_calendar(self):
        return self.get_market_data()[0].index


def get_adapter(market):
    return {"india": IndiaAdapter, "usa": USAAdapter}[market.lower()]()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("market", choices=["india", "usa"])
    ap.add_argument("--download", action="store_true")
    a = ap.parse_args()
    adp = get_adapter(a.market)
    if a.market == "usa" and a.download:
        print(f"  downloaded {adp.download()} USA series -> data/raw/usa/")
    c, h, l, v, idx, vix, _ = adp.get_market_data()
    uni = adp.get_universe()
    print("=" * 60)
    print(f"  MARKET ADAPTER — {adp.name.upper()}")
    print("=" * 60)
    print(f"  panel: {c.shape[1]} symbols x {len(c)} days · latest {c.index[-1].date()}")
    print(f"  universe: {len(uni)} names · sample {uni[:6]}")
    print(f"  index latest: {idx.iloc[-1]:,.1f} · vix: {'yes' if vix is not None else 'n/a'}")
    print(f"  sector of {uni[0]}: {adp.get_sector(uni[0])}")
