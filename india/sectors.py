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


# ---- Nifty 101-200 (midcaps) ----
SECTORS.update({
    "PERSISTENT": "IT", "OFSS": "IT", "LTTS": "IT", "KPITTECH": "IT", "TATAELXSI": "IT",
    "SONACOMS": "Auto", "ESCORTS": "Auto", "ASHOKLEY": "Auto", "BHARATFORG": "Auto", "MRF": "Auto",
    "BALKRISIND": "Auto", "APOLLOTYRE": "Auto", "CUMMINSIND": "Industrials", "EXIDEIND": "Auto",
    "TIINDIA": "Auto", "UNOMINDA": "Auto", "ALKEM": "Pharma", "AUROPHARMA": "Pharma",
    "GLENMARK": "Pharma", "IPCALAB": "Pharma", "LAURUSLABS": "Pharma", "AJANTPHARM": "Pharma",
    "GLAND": "Pharma", "NATCOPHARM": "Pharma", "FORTIS": "Healthcare", "LALPATHLAB": "Healthcare",
    "SYNGENE": "Pharma", "ABBOTINDIA": "Pharma", "METROPOLIS": "Healthcare", "BANDHANBNK": "Financials",
    "FEDERALBNK": "Financials", "IDFCFIRSTB": "Financials", "AUBANK": "Financials", "INDIANB": "Financials",
    "UNIONBANK": "Financials", "YESBANK": "Financials", "RBLBANK": "Financials", "LICHSGFIN": "Financials",
    "SBICARD": "Financials", "BAJAJHLDNG": "Financials", "MFSL": "Financials", "CHOLAHLDNG": "Financials",
    "SUNDARMFIN": "Financials", "MANAPPURAM": "Financials", "ABCAPITAL": "Financials", "PEL": "Financials",
    "CDSL": "Financials", "BSE": "Financials", "MCX": "Financials", "ANGELONE": "Financials",
    "IEX": "Financials", "KFINTECH": "Financials", "CAMS": "Financials", "PAYTM": "Financials",
    "NYKAA": "Consumer", "DELHIVERY": "Transport", "POLICYBZR": "Financials", "IRCTC": "Transport",
    "IRFC": "Financials", "RVNL": "Infra", "IRB": "Infra", "NHPC": "Power", "SJVN": "Power",
    "NLCINDIA": "Power", "CONCOR": "Transport", "NMDC": "Metal", "HINDZINC": "Metal",
    "NATIONALUM": "Metal", "OIL": "Energy", "MAZDOCK": "Industrials", "TATACHEM": "Chemicals",
    "DEEPAKNTR": "Chemicals", "AARTIIND": "Chemicals", "NAVINFLUOR": "Chemicals", "GNFC": "Chemicals",
    "COROMANDEL": "Chemicals", "UPL": "Chemicals", "PIIND": "Chemicals", "ATUL": "Chemicals",
    "VINATIORGA": "Chemicals", "CHAMBLFERT": "Chemicals", "BALRAMCHIN": "Chemicals", "DALBHARAT": "Cement",
    "JKCEMENT": "Cement", "RAMCOCEM": "Cement", "ACC": "Cement", "APLAPOLLO": "Metal",
    "JINDALSAW": "Metal", "RATNAMANI": "Metal", "GODREJPROP": "Realty", "OBEROIRLTY": "Realty",
    "PHOENIXLTD": "Realty", "PRESTIGE": "Realty", "LODHA": "Realty", "TORNTPOWER": "Power",
    "JSWENERGY": "Power", "IGL": "Energy", "MGL": "Energy", "GUJGASLTD": "Energy", "CESC": "Power",
    "UBL": "FMCG", "RADICO": "FMCG", "PATANJALI": "FMCG", "GODREJIND": "FMCG", "EMAMILTD": "FMCG",
    "JUBLFOOD": "Consumer", "BATAINDIA": "Consumer", "RELAXO": "Consumer", "VOLTAS": "Industrials",
    "BLUESTARCO": "Industrials", "DIXON": "Industrials", "AMBER": "Industrials", "CROMPTON": "Industrials",
    "KAJARIACER": "Consumer", "SUPREMEIND": "Industrials", "ASTRAL": "Industrials", "THERMAX": "Industrials",
    "AIAENG": "Industrials", "KEI": "Industrials", "CGPOWER": "Industrials", "KALYANKJIL": "Consumer",
    "INDUSTOWER": "Telecom", "TATACOMM": "Telecom", "PVRINOX": "Consumer", "SUNTV": "Consumer",
    "GMRAIRPORT": "Infra",
})


def sector_of(symbol):
    return SECTORS.get(symbol, "Other")
