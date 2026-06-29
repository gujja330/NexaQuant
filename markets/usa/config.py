# markets/usa/config.py
"""USA market configuration consumed by the shared engine (core/) via USAAdapter. Editing this file
re-points the USA market without touching the engine or India. Sector map here is a starter for the
mega-caps; real per-name GICS/SIC sectors arrive with SEC fundamentals (Phase 4)."""

INDEX_TICKER = "^GSPC"          # S&P 500 benchmark
VIX_TICKER = "^VIX"
INDEX_FILE = "SPX"              # cached as data/raw/usa/SPX_D1.parquet
VIX_FILE = "USVIX"

# liquidity screen thresholds for the dynamic universe (core/usa_universe.py)
MIN_PRICE = 10.0                # USD
MIN_DOLLAR_VOL = 20e6           # USD/day average
MIN_DAYS = 40                   # minimum bars of recent history

# starter sector map (mega-caps). NOTE: the full dynamic universe (~thousands) gets real sectors
# from SEC SIC codes in Phase 4; until then unmapped names fall back to "Other".
SECTORS = {
    "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "NVDA": "Tech", "AVGO": "Tech", "ORCL": "Tech",
    "AMD": "Tech", "ADI": "Tech", "AMAT": "Tech", "ASML": "Tech",
    "AMZN": "Consumer Disc", "TSLA": "Consumer Disc", "HD": "Consumer Disc", "MCD": "Consumer Disc",
    "NKE": "Consumer Disc", "META": "Communication", "NFLX": "Communication", "DIS": "Communication",
    "T": "Telecom", "VZ": "Telecom", "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS": "Financials", "V": "Financials", "MA": "Financials", "JNJ": "Healthcare", "UNH": "Healthcare",
    "PFE": "Healthcare", "ABBV": "Healthcare", "MRK": "Healthcare", "LLY": "Healthcare",
    "XOM": "Energy", "CVX": "Energy", "PG": "Staples", "KO": "Staples", "PEP": "Staples",
    "WMT": "Staples", "COST": "Staples", "BA": "Industrials", "CAT": "Industrials", "GE": "Industrials",
    "HON": "Industrials", "UNP": "Industrials",
}
