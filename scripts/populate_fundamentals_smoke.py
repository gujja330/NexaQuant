"""Small-batch smoke run of the Fundamentals populator · no network required.

Uses synthetic realistic inputs (same as validation earlier) across
the India NIFTY 50 top-10 tickers so Fundamentals FS has more than
one row · unblocks Winner Genome for a subset · does NOT claim yfinance
freshness (all rows tagged as `synthetic_smoke`).

This is a substrate-priming action per V2 §36 · gap flagged transparently.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


SEED_FIN = {
    'net_income': 750_000_000_000, 'cfo': 900_000_000_000,
    'roa_now': 0.055, 'roa_prev': 0.049,
    'total_assets_now': 15_000_000_000_000, 'total_assets_prev': 14_200_000_000_000,
    'long_term_debt_now': 2_800_000_000_000, 'long_term_debt_prev': 3_100_000_000_000,
    'current_ratio_now': 1.15, 'current_ratio_prev': 1.08,
    'shares_out_now': 6_770_000_000, 'shares_out_prev': 6_770_000_000,
    'gross_margin_now': 0.28, 'gross_margin_prev': 0.26,
    'asset_turnover_now': 0.62, 'asset_turnover_prev': 0.58,
    'dsri': 1.05, 'gmi': 0.98, 'aqi': 1.02, 'sgi': 1.12,
    'depi': 1.00, 'sgai': 0.99, 'tata': 0.02, 'lvgi': 0.97,
    'working_capital': 800_000_000_000, 'retained_earnings': 3_500_000_000_000,
    'ebit': 1_200_000_000_000, 'market_cap': 17_600_000_000_000,
    'total_liabilities': 6_500_000_000_000, 'sales': 9_800_000_000_000,
    'total_assets': 15_000_000_000_000, 'interest_expense': 220_000_000_000,
    'fcf_ttm': 550_000_000_000, 'enterprise_value': 21_500_000_000_000,
    'ebitda_ttm': 1_800_000_000_000,
    'dividends_ttm': 65_000_000_000, 'buybacks_ttm': 0, 'issuance_ttm': 0,
    'consensus_eps_now': 115.4, 'consensus_eps_3mo_ago': 108.2,
    'guidance_direction': 'RAISED',
    'actual_eps': 28.7, 'consensus_eps': 27.9,
    'insider_net_dollars_90d': 12_500_000,
    'inst_shares_qtr': 3_200_000_000, 'inst_shares_prev_qtr': 3_100_000_000,
    'net_flow_series_20d': [120, 80, -40, 65, 200, 150, -30, 90, 45, 110,
                             75, 60, -20, 130, 95, 40, 55, 165, 200, 85],
    'put_oi_single_name': 480_000, 'call_oi_single_name': 620_000,
    'short_interest_shares': 5_800_000, 'float_shares': 3_200_000_000,
    'next_earnings_date': '2026-10-15',
    'promoter_pledged_shares': 0, 'promoter_total_shares': 3_400_000_000,
    'data_sources': 'synthetic_smoke',
}


def main():
    from backend.research.fundamentals import build_feature_store
    from backend.research.fundamentals.builder import compute_row

    p = _ROOT / "reports" / "india_universe.json"
    tickers = json.loads(p.read_text(encoding="utf-8")).get("tickers", [])[:10]
    asof = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for t in tickers:
        # Vary market_cap a little so cap_bucket produces different labels
        import copy
        fin = copy.deepcopy(SEED_FIN)
        fin['market_cap'] = 17_600_000_000_000 * (0.5 + 0.1 * (hash(t) % 10))
        row = compute_row('india', t, asof, fin)
        rows.append(row)
    s = build_feature_store(_ROOT, 'india', rows)
    print(json.dumps(s, indent=2, default=str))


if __name__ == "__main__":
    main()
