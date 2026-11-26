import pandas as pd
import pytest

from backend.delivery.lifecycle.canonical_daily_lifecycle import _norm_ticker
from backend.delivery.telegram.detail_xlsx import _rec_to_row
from backend.ingest.ticker_health import yahoo_symbol
from backend.research import opportunity_registry
from backend.risk.dynamic_risk_v2 import _bars


@pytest.mark.parametrize("ticker", ["BRK.B", "BF.B"])
def test_usa_share_class_reaches_registry_and_price_lookup(tmp_path, ticker):
    prices = tmp_path / "usa/data/raw/us"
    prices.mkdir(parents=True)
    pandas_index = pd.to_datetime(["2026-11-23", "2026-11-25"])
    pd.DataFrame({"close": [500.0, 501.0]}, index=pandas_index).to_parquet(prices / f"{ticker}_D1.parquet")
    _rec_to_row({"ticker": ticker, "action": "BUY", "percentile_action": "BUY",
                 "investor_action": {"entry": "BUY", "if_holding": "HOLD"}},
                "usa", tmp_path, "R2", "2026-11-26")
    registry = opportunity_registry.load_all(tmp_path)
    assert ("usa", "R2", ticker) in registry
    assert ("usa", "R2", ticker.split(".")[0]) not in registry
    assert _norm_ticker(ticker) == ticker
    assert _bars(tmp_path, ticker, "usa")["close"].iloc[-1] == 501.0
    assert yahoo_symbol(tmp_path, "usa", ticker) == ticker.replace(".", "-")
