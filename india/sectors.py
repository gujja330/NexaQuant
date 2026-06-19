# india/sectors.py
"""Sector map for the Nifty-100 universe — used for sector-momentum features and the sector cap.
Approximate GICS-style buckets; precision of membership matters less than grouping like with like."""

SECTORS = {
    # Financials (banks / NBFC / insurance)
    "HDFCBANK": "Financials", "ICICIBANK": "Financials", "SBIN": "Financials",
    "KOTAKBANK": "Financials", "AXISBANK": "Financials", "INDUSINDBK": "Financials",
    "BANKBARODA": "Financials", "PNB": "Financials", "CANBK": "Financials",
    "BAJFINANCE": "Financials", "BAJAJFINSV": "Financials", "SHRIRAMFIN": "Financials",
    "CHOLAFIN": "Financials", "MUTHOOTFIN": "Financials", "PFC": "Financials",
    "RECLTD": "Financials", "SBILIFE": "Financials", "HDFCLIFE": "Financials",
    "ICICIGI": "Financials", "ICICIPRULI": "Financials", "LICI": "Financials",
    "JIOFIN": "Financials",
    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
    "LTIM": "IT", "MPHASIS": "IT", "COFORGE": "IT", "NAUKRI": "IT",
    # Energy / Oil & Gas
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy", "IOC": "Energy",
    "GAIL": "Energy", "PETRONET": "Energy",
    # Power / Utilities
    "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power",
    "ADANIGREEN": "Power", "ADANIPOWER": "Power",
    # FMCG / Consumer staples
    "ITC": "FMCG", "HINDUNILVR": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "DABUR": "FMCG", "TATACONSUM": "FMCG", "MARICO": "FMCG", "COLPAL": "FMCG",
    "GODREJCP": "FMCG", "UNITDSPR": "FMCG", "VBL": "FMCG",
    # Auto & ancillaries
    "MARUTI": "Auto", "EICHERMOT": "Auto", "HEROMOTOCO": "Auto", "TATAMOTORS": "Auto",
    "MM": "Auto", "BAJAJ-AUTO": "Auto", "TVSMOTOR": "Auto", "MOTHERSON": "Auto",
    "BOSCHLTD": "Auto",
    # Pharma & Healthcare
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "ZYDUSLIFE": "Pharma",
    "BIOCON": "Pharma", "LUPIN": "Pharma", "TORNTPHARM": "Pharma",
    "APOLLOHOSP": "Healthcare", "MAXHEALTH": "Healthcare",
    # Metals & Mining
    "TATASTEEL": "Metal", "JSWSTEEL": "Metal", "HINDALCO": "Metal", "VEDL": "Metal",
    "JINDALSTEL": "Metal", "SAIL": "Metal", "COALINDIA": "Metal",
    # Cement
    "ULTRACEMCO": "Cement", "GRASIM": "Cement", "AMBUJACEM": "Cement", "SHREECEM": "Cement",
    # Industrials / Capital goods / Infra
    "LT": "Infra", "ADANIENT": "Infra", "ABB": "Industrials", "SIEMENS": "Industrials",
    "BEL": "Industrials", "HAL": "Industrials", "POLYCAB": "Industrials",
    "HAVELLS": "Industrials", "ADANIPORTS": "Infra",
    # Telecom
    "BHARTIARTL": "Telecom",
    # Consumer discretionary / Retail / Realty / Chemicals / Transport
    "TITAN": "Consumer", "ASIANPAINT": "Consumer", "TRENT": "Consumer", "DMART": "Consumer",
    "PAGEIND": "Consumer", "INDHOTEL": "Consumer", "PIDILITIND": "Chemicals",
    "SRF": "Chemicals", "DLF": "Realty", "INDIGO": "Transport",
}


def sector_of(symbol):
    return SECTORS.get(symbol, "Other")
