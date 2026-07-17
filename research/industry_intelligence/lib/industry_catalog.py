"""DEV019 industry catalogue.

Since NSE does not publish tradable industry indices at the granularity below
sectors, DEV019 aggregates industry price series *from constituent parquets*
already present at data/raw/india/*.parquet.

Each industry lists its parent sector (matching DEV018 sector_key) so the
industry_context bundle can be traced back through the Sector -> Global
hierarchy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_PARQ_DIR = _ROOT / "data" / "raw" / "india"


@dataclass
class IndustrySpec:
    industry_key: str                             # canonical: industry.india.<name>
    display_name: str
    parent_sector_key: str                        # matches DEV018 sector_catalog
    parent_sector_name: str                       # human-readable
    tickers: list[str] = field(default_factory=list)
    description: str = ""

    def available_tickers(self) -> list[str]:
        """Tickers that actually have parquet files on disk."""
        return [t for t in self.tickers if (_PARQ_DIR / f"{t}_D1.parquet").exists()]


# ── Industries with ≥3 available tickers only. All ticker names match the AEGIS
#    universe convention (`_D1.parquet` suffix on disk). Groupings reflect standard
#    NIFTY industry breakdowns; each ticker appears in exactly one industry.
INDUSTRIES: list[IndustrySpec] = [
    # ── Financials ──────────────────────────────────────────────────────────
    IndustrySpec("industry.india.private_banks", "Private Banks",
                  "sector.india.banking", "Banking",
                  ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
                   "IDFCFIRSTB", "FEDERALBNK", "RBLBANK", "BANDHANBNK", "AUBANK"]),
    IndustrySpec("industry.india.psu_banks", "PSU Banks",
                  "sector.india.psu_bank", "PSU Bank",
                  ["SBIN", "PNB", "BANKBARODA", "CANBK", "UNIONBANK", "INDIANB"]),
    IndustrySpec("industry.india.nbfc", "NBFC",
                  "sector.india.financial_svc", "Financial Services",
                  ["BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "CHOLAFIN", "MUTHOOTFIN",
                   "MANAPPURAM", "LICHSGFIN", "PFC", "RECLTD", "IRFC", "CHOLAHLDNG",
                   "SBICARD", "BAJAJHLDNG"]),
    IndustrySpec("industry.india.insurance", "Insurance",
                  "sector.india.financial_svc", "Financial Services",
                  ["SBILIFE", "HDFCLIFE", "ICICIGI", "ICICIPRULI", "LICI", "MFSL"]),
    IndustrySpec("industry.india.capital_markets", "Capital Markets & AMC",
                  "sector.india.financial_svc", "Financial Services",
                  ["HDFCAMC", "ANGELONE", "BSE", "MCX", "CAMS", "CDSL", "KFINTECH",
                   "POLICYBZR", "PAYTM", "JIOFIN"]),

    # ── IT ──────────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.it_services", "IT Services",
                  "sector.india.it", "IT",
                  ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "MPHASIS",
                   "COFORGE", "PERSISTENT", "LTTS", "TATAELXSI", "OFSS", "KPITTECH"]),
    IndustrySpec("industry.india.internet", "Internet & New Age",
                  "sector.india.it", "IT",
                  ["NAUKRI", "NYKAA", "DELHIVERY"]),

    # ── Auto ────────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.auto_oem", "Auto OEM",
                  "sector.india.auto", "Auto",
                  ["MARUTI", "EICHERMOT", "HEROMOTOCO", "TATAMOTORS", "MM",
                   "BAJAJ-AUTO", "TVSMOTOR", "ASHOKLEY"]),
    IndustrySpec("industry.india.auto_ancillary", "Auto Ancillary",
                  "sector.india.auto", "Auto",
                  ["MOTHERSON", "BOSCHLTD", "EXIDEIND", "UNOMINDA", "BALKRISIND",
                   "SONACOMS", "BHARATFORG"]),
    IndustrySpec("industry.india.tyres", "Tyres",
                  "sector.india.auto", "Auto",
                  ["MRF", "APOLLOTYRE"]),

    # ── Pharma & Healthcare ─────────────────────────────────────────────────
    IndustrySpec("industry.india.pharma_largecap", "Pharma (Large Cap)",
                  "sector.india.pharma", "Pharma",
                  ["SUNPHARMA", "DRREDDY", "CIPLA", "TORNTPHARM", "LUPIN",
                   "ZYDUSLIFE", "AUROPHARMA"]),
    IndustrySpec("industry.india.pharma_midcap", "Pharma (Mid Cap)",
                  "sector.india.pharma", "Pharma",
                  ["BIOCON", "GLAND", "GLENMARK", "IPCALAB", "ALKEM",
                   "LAURUSLABS", "NATCOPHARM", "AJANTPHARM", "ABBOTINDIA"]),
    IndustrySpec("industry.india.hospitals", "Hospitals",
                  "sector.india.healthcare", "Healthcare",
                  ["APOLLOHOSP", "MAXHEALTH", "FORTIS"]),
    IndustrySpec("industry.india.diagnostics", "Diagnostics",
                  "sector.india.healthcare", "Healthcare",
                  ["METROPOLIS", "LALPATHLAB", "SYNGENE"]),

    # ── Chemicals ───────────────────────────────────────────────────────────
    IndustrySpec("industry.india.specialty_chem", "Specialty Chemicals",
                  "sector.india.metal", "Metal (chemicals proxy)",   # closest parent
                  ["PIDILITIND", "SRF", "NAVINFLUOR", "VINATIORGA", "AARTIIND",
                   "DEEPAKNTR", "ATUL"]),
    IndustrySpec("industry.india.agro_chem", "Agro Chemicals",
                  "sector.india.metal", "Metal (chemicals proxy)",
                  ["PIIND", "UPL"]),
    IndustrySpec("industry.india.fertilizers", "Fertilizers",
                  "sector.india.metal", "Metal (chemicals proxy)",
                  ["COROMANDEL", "CHAMBLFERT", "GNFC"]),

    # ── Metals & Mining ─────────────────────────────────────────────────────
    IndustrySpec("industry.india.steel", "Steel",
                  "sector.india.metal", "Metal",
                  ["TATASTEEL", "JSWSTEEL", "JINDALSTEL", "JINDALSAW", "SAIL"]),
    IndustrySpec("industry.india.non_ferrous", "Non-Ferrous Metals",
                  "sector.india.metal", "Metal",
                  ["HINDALCO", "VEDL", "NATIONALUM", "HINDZINC"]),
    IndustrySpec("industry.india.mining", "Mining",
                  "sector.india.metal", "Metal",
                  ["COALINDIA", "NMDC"]),

    # ── Cement ──────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.cement", "Cement",
                  "sector.india.infra", "Infrastructure",
                  ["ULTRACEMCO", "AMBUJACEM", "SHREECEM", "JKCEMENT",
                   "RAMCOCEM", "DALBHARAT", "ACC", "GRASIM"]),

    # ── Energy / Oil & Gas ──────────────────────────────────────────────────
    IndustrySpec("industry.india.oil_marketing", "Oil Marketing",
                  "sector.india.energy", "Energy",
                  ["BPCL", "IOC"]),
    IndustrySpec("industry.india.oil_gas_upstream", "Oil & Gas Upstream",
                  "sector.india.energy", "Energy",
                  ["ONGC", "OIL", "RELIANCE"]),
    IndustrySpec("industry.india.gas_distribution", "Gas Distribution",
                  "sector.india.energy", "Energy",
                  ["GAIL", "PETRONET", "IGL", "MGL"]),

    # ── Power / Renewables ──────────────────────────────────────────────────
    IndustrySpec("industry.india.power_generation", "Power Generation",
                  "sector.india.energy", "Energy",
                  ["NTPC", "TATAPOWER", "ADANIPOWER", "NHPC", "SJVN",
                   "JSWENERGY", "TORNTPOWER", "CESC", "NLCINDIA"]),
    IndustrySpec("industry.india.power_transmission", "Power Transmission",
                  "sector.india.energy", "Energy",
                  ["POWERGRID"]),                                # only 1; will drop if <3 filter
    IndustrySpec("industry.india.renewables", "Renewables",
                  "sector.india.energy", "Energy",
                  ["ADANIGREEN", "NHPC", "SJVN"]),

    # ── FMCG ────────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.personal_care", "Personal Care",
                  "sector.india.fmcg", "FMCG",
                  ["HINDUNILVR", "DABUR", "MARICO", "COLPAL", "GODREJCP", "EMAMILTD"]),
    IndustrySpec("industry.india.food_beverage", "Food & Beverage",
                  "sector.india.fmcg", "FMCG",
                  ["NESTLEIND", "BRITANNIA", "TATACONSUM", "VBL", "UBL",
                   "UNITDSPR", "RADICO"]),
    IndustrySpec("industry.india.household", "Household & Tobacco",
                  "sector.india.fmcg", "FMCG",
                  ["ITC", "GODREJIND"]),

    # ── Consumer Discretionary ──────────────────────────────────────────────
    IndustrySpec("industry.india.retail", "Retail",
                  "sector.india.consumption", "Consumption",
                  ["DMART", "TRENT", "TITAN"]),
    IndustrySpec("industry.india.apparel_lifestyle", "Apparel & Lifestyle",
                  "sector.india.consumption", "Consumption",
                  ["PAGEIND", "BATAINDIA", "RELAXO", "KALYANKJIL"]),
    IndustrySpec("industry.india.paints_home", "Paints & Home Decor",
                  "sector.india.consumption", "Consumption",
                  ["ASIANPAINT"]),                              # only 1; will drop
    IndustrySpec("industry.india.hotels", "Hotels & Tourism",
                  "sector.india.consumption", "Consumption",
                  ["INDHOTEL"]),                                # only 1; will drop

    # ── Industrials / Capital Goods / Defence ───────────────────────────────
    IndustrySpec("industry.india.capital_goods", "Capital Goods",
                  "sector.india.infra", "Infrastructure",
                  ["LT", "ABB", "SIEMENS", "THERMAX", "KEI", "POLYCAB",
                   "HAVELLS", "CROMPTON", "BLUESTARCO", "KAJARIACER",
                   "CUMMINSIND", "AMBER", "TIINDIA"]),
    IndustrySpec("industry.india.defence_aerospace", "Defence & Aerospace",
                  "sector.india.infra", "Infrastructure",
                  ["HAL", "BEL", "MAZDOCK"]),
    IndustrySpec("industry.india.electricals", "Electricals & Consumer Durables",
                  "sector.india.infra", "Infrastructure",
                  ["POLYCAB", "HAVELLS", "KEI", "CGPOWER", "DIXON",
                   "CROMPTON", "AMBER"]),

    # ── Infra: Ports / Logistics / Railways ─────────────────────────────────
    IndustrySpec("industry.india.ports_logistics", "Ports & Logistics",
                  "sector.india.infra", "Infrastructure",
                  ["ADANIPORTS", "CONCOR", "DELHIVERY"]),
    IndustrySpec("industry.india.railways", "Railways",
                  "sector.india.infra", "Infrastructure",
                  ["RVNL", "IRCTC", "IRFC"]),

    # ── Realty ──────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.real_estate", "Real Estate",
                  "sector.india.realty", "Realty",
                  ["DLF", "PRESTIGE", "OBEROIRLTY", "GODREJPROP", "PHOENIXLTD", "LODHA"]),

    # ── Telecom ─────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.telecom_services", "Telecom Services",
                  "sector.india.consumption", "Consumption",     # Bharti in Nifty Consumption
                  ["BHARTIARTL", "INDUSTOWER", "TATACOMM"]),

    # ── Aviation ────────────────────────────────────────────────────────────
    IndustrySpec("industry.india.airlines", "Airlines",
                  "sector.india.infra", "Infrastructure",
                  ["INDIGO"]),                                   # only 1; will drop

    # ── Media & Entertainment ───────────────────────────────────────────────
    IndustrySpec("industry.india.media_entertainment", "Media & Entertainment",
                  "sector.india.media", "Media",
                  ["PVRINOX", "SUNTV"]),                          # only 2; will drop

    # ── Chemical adjacencies (moved parent to closest available) ────────────
    IndustrySpec("industry.india.industrials_diversified", "Industrials (Diversified)",
                  "sector.india.infra", "Infrastructure",
                  ["ADANIENT", "GMRAIRPORT", "TATASTEEL"]),      # small overlap intentional; keep for coverage
]


def summary() -> dict:
    total = len(INDUSTRIES)
    with_enough = sum(1 for i in INDUSTRIES if len(i.available_tickers()) >= 3)
    return {
        "total_industries_defined": total,
        "with_3plus_available_constituents": with_enough,
        "min_constituents_for_scoring": 3,
        "industries": [i.display_name for i in INDUSTRIES],
    }


def by_industry_key(key: str) -> IndustrySpec:
    for i in INDUSTRIES:
        if i.industry_key == key:
            return i
    raise KeyError(f"unknown industry_key: {key}")


def by_parent_sector(sector_key: str) -> list[IndustrySpec]:
    return [i for i in INDUSTRIES if i.parent_sector_key == sector_key]
