"""The bar window is cut at the asof BEFORE it is sized. CEO 2026-11-04.

TWO DEFECTS IN THREE LINES
--------------------------
`adapt_prices` read `df.tail(90)` and then dropped bars after the cutoff.

1. 90 bars, while the feature registry declares `sma_200` and
   `price_above_sma200`. Measured on the live repository: 0% populated
   in BOTH markets, every day. The raw parquets were never the
   constraint - India holds a median 1448 bars per symbol, USA 1254, and
   230/230 India and 899/908 USA symbols have at least 200. The cap
   alone produced the zero. After the fix: 98.7% India, 96.9% USA.

2. `tail()` ran before the cutoff filter, so a historical asof kept the
   newest 90 bars and then discarded all of them for being past the
   cutoff. At a six-month-back asof India returned ZERO bars. That is
   the mechanism behind every R3 replay wave reporting INSUFFICIENT
   HISTORY. After the fix the same asof returns 59,800 rows.

tmp_path-isolated except for the two explicitly read-only live checks.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend.canonical.adapters import (DEFAULT_LOOKBACK_BARS,
                                        MAX_FEATURE_WINDOW_BARS, adapt_prices)
from backend.canonical.model import INDIA_PROFILE, USA_PROFILE

_LIVE = Path(__file__).resolve().parents[2]


def _bars(n, end=date(2026, 11, 3), start_price=100.0, dupes=0, drop=()):
    """n business-day bars ending at `end`, oldest first.

    `drop` removes bars at those positions AFTER generation, which is how
    a real feed looks when a session is missing from the middle of a
    history. Generating straight into a skip loops forever.
    """
    rows, d, made = [], end, 0
    while made < n + len(drop):
        if d.weekday() < 5:
            rows.append({"date": d, "open": start_price, "high": start_price + 1,
                         "low": start_price - 1, "close": start_price + made,
                         "volume": 1000 + made})
            made += 1
        d -= timedelta(days=1)
    rows.reverse()
    if drop:
        rows = [r for i, r in enumerate(rows) if i not in set(drop)]
    for _ in range(dupes):
        rows.append(dict(rows[-1], close=-999.0))     # same date, later row
    return pd.DataFrame(rows)


def _write(root, market, sym, df):
    d = (root / "data" / "raw" / "india") if market == "india" else \
        (root / "usa" / "data" / "raw" / "us")
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / ("%s_D1.parquet" % sym), index=False)


def _profile(market):
    return INDIA_PROFILE if market == "india" else USA_PROFILE


def _counts(ds):
    out = {}
    for r in ds.rows:
        out[r.symbol] = out.get(r.symbol, 0) + 1
    return out


class TestTheWindowCoversTheLongestFeature:
    def test_the_default_window_exceeds_the_longest_declared_feature(self):
        assert DEFAULT_LOOKBACK_BARS > MAX_FEATURE_WINDOW_BARS, (
            "a 200-bar feature behind a smaller window can never populate")
        assert MAX_FEATURE_WINDOW_BARS == 200

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_250_bars_yield_enough_for_sma_200(self, tmp_path, market):
        _write(tmp_path, market, "AAA", _bars(250))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert _counts(ds)["AAA"] >= MAX_FEATURE_WINDOW_BARS

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_sma_200_actually_computes_from_the_adapted_window(self, tmp_path,
                                                               market):
        """End to end: the window feeds the technical computer."""
        from backend.feature_store.features import technical
        _write(tmp_path, market, "AAA", _bars(250))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        feats = technical.compute({"bar": ds}, ["AAA"], date(2026, 11, 3),
                                   market)
        assert feats["AAA"]["sma_200"] is not None
        assert feats["AAA"]["price_above_sma200"] in (0, 1)


class TestInsufficientHistoryIsExplicit:
    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_short_symbol_is_counted_and_named(self, tmp_path, market):
        _write(tmp_path, market, "SHORT", _bars(40))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert "SHORT" in ds.notes
        assert "fewer than 200" in ds.notes

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_short_symbol_still_yields_its_bars(self, tmp_path, market):
        """Insufficient for sma_200 is not insufficient for everything."""
        _write(tmp_path, market, "SHORT", _bars(40))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert _counts(ds)["SHORT"] == 40

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_sma_200_abstains_rather_than_fabricating(self, tmp_path, market):
        from backend.feature_store.features import technical
        _write(tmp_path, market, "SHORT", _bars(40))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        feats = technical.compute({"bar": ds}, ["SHORT"], date(2026, 11, 3),
                                   market)
        assert feats["SHORT"]["sma_200"] is None
        assert feats["SHORT"]["price_above_sma200"] is None

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_one_bar_symbol_is_reported_not_crashed(self, tmp_path, market):
        """AVB, EA, EQR and WBD each hold exactly one bar in the live repo."""
        _write(tmp_path, market, "ONEBAR", _bars(1))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert _counts(ds)["ONEBAR"] == 1
        assert "ONEBAR" in ds.notes

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_file_with_no_date_column_is_skipped_not_stamped(self, tmp_path,
                                                               market):
        """It used to be emitted carrying the cutoff as its date."""
        _write(tmp_path, market, "NODATE",
               pd.DataFrame({"open": [1.0], "high": [2.0], "low": [0.5],
                             "close": [1.5], "volume": [10]}))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert "NODATE" not in _counts(ds)
        assert "no date column" in ds.notes


class TestCutoffPrecedesWindowSelection:
    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_historical_asof_still_returns_a_full_window(self, tmp_path,
                                                           market):
        """THE regression. tail-then-filter returned zero here."""
        _write(tmp_path, market, "AAA", _bars(500))
        ds = adapt_prices(tmp_path, _profile(market),
                          cutoff=date(2026, 5, 1))
        assert _counts(ds).get("AAA", 0) >= MAX_FEATURE_WINDOW_BARS, (
            "a historical asof lost its window - tail ran before the cutoff")

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_historical_asof_sees_no_future_bar(self, tmp_path, market):
        cutoff = date(2026, 5, 1)
        _write(tmp_path, market, "AAA", _bars(500))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=cutoff)
        assert ds.rows
        assert max(r.date for r in ds.rows) <= cutoff

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_the_window_is_the_last_n_bars_at_or_before_the_cutoff(
            self, tmp_path, market):
        cutoff = date(2026, 5, 1)
        _write(tmp_path, market, "AAA", _bars(500))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=cutoff,
                          lookback_bars=10)
        got = sorted(r.date for r in ds.rows)
        assert len(got) == 10
        assert got[-1] <= cutoff
        # contiguous business days ending at or before the cutoff
        assert got == sorted(set(got))

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_a_cutoff_before_all_history_yields_nothing_and_says_so(
            self, tmp_path, market):
        _write(tmp_path, market, "AAA", _bars(50))
        ds = adapt_prices(tmp_path, _profile(market),
                          cutoff=date(2020, 1, 1))
        assert ds.n_rows == 0
        assert "AAA" in ds.notes


class TestMessyInputs:
    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_duplicate_dates_keep_one_bar_per_date(self, tmp_path, market):
        _write(tmp_path, market, "AAA", _bars(30, dupes=3))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        dates = [r.date for r in ds.rows]
        assert len(dates) == len(set(dates)), "duplicate dates survived"

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_the_last_row_wins_for_a_duplicated_date(self, tmp_path, market):
        """A re-ingest appends a corrected bar; the correction must win."""
        _write(tmp_path, market, "AAA", _bars(30, dupes=1))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        newest = max(ds.rows, key=lambda r: r.date)
        assert newest.close == -999.0

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_unparseable_dates_are_dropped_not_defaulted(self, tmp_path,
                                                         market):
        """The whole column is strings - one of them is junk.

        Mixing a str into a date column makes a dtype pyarrow refuses to
        write, so the fixture has to be string-typed throughout, which is
        also how a CSV-sourced feed actually arrives.
        """
        df = _bars(10)
        df["date"] = [d.isoformat() for d in df["date"]]
        df.loc[0, "date"] = "not-a-date"
        _write(tmp_path, market, "AAA", df)
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert _counts(ds)["AAA"] == 9

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_bars_come_back_in_date_order(self, tmp_path, market):
        df = _bars(40).sample(frac=1.0, random_state=7)   # shuffled on disk
        _write(tmp_path, market, "AAA", df)
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        dates = [r.date for r in ds.rows]
        assert dates == sorted(dates)

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_missing_bars_in_the_middle_are_tolerated(self, tmp_path, market):
        _write(tmp_path, market, "AAA", _bars(60, drop=(10, 11, 12)))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2026, 11, 3))
        assert _counts(ds)["AAA"] == 60


class TestBothMarketsShareOneContract:
    def test_neither_market_is_special_cased_in_the_window_logic(self):
        """No ticker-specific or market-specific hardcoding."""
        import ast
        import backend.canonical.adapters as ad
        tree = ast.parse(Path(ad.__file__).read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "adapt_prices")
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        code = "\n".join(ast.unparse(n) for n in body)
        # `market.name` legitimately appears as the raw-directory choice
        # and as the value stamped onto output rows/datasets. What must
        # not exist is a SECOND branch on it - one comparison only.
        assert code.count("market.name ==") == 1, (
            "window selection must not branch on the market beyond "
            "choosing the raw directory")
        # Ticker literals are STRING CONSTANTS, so look for them in the
        # AST rather than as substrings. "EA" otherwise matches the
        # middle of MAX_FEATURE_WINDOW_BARS - a two-letter grep cannot
        # tell a symbol from a syllable.
        tickers = {"AVB", "EA", "EQR", "WBD", "PSKY", "RELIANCE", "TCS"}
        literals = {n.value for n in ast.walk(fn)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert not (literals & tickers), (
            "ticker-specific hardcoding: %s" % sorted(literals & tickers))

    def test_the_deprecated_alias_still_counts_bars(self, tmp_path):
        _write(tmp_path, "india", "AAA", _bars(300))
        ds = adapt_prices(tmp_path, INDIA_PROFILE, cutoff=date(2026, 11, 3),
                          lookback_days=12)
        assert _counts(ds)["AAA"] == 12


class TestLiveRepositoryReadOnly:
    @pytest.mark.parametrize("market,profile",
                             [("india", INDIA_PROFILE), ("usa", USA_PROFILE)])
    def test_the_live_window_reaches_200_for_almost_every_symbol(self, market,
                                                                 profile):
        ds = adapt_prices(_LIVE, profile, cutoff=date(2026, 11, 3))
        if not ds.rows:
            pytest.skip("no raw bars for %s" % market)
        c = _counts(ds)
        ok = sum(1 for v in c.values() if v >= MAX_FEATURE_WINDOW_BARS)
        assert ok / len(c) > 0.95, (
            "only %d/%d %s symbols reach %d bars"
            % (ok, len(c), market, MAX_FEATURE_WINDOW_BARS))

    @pytest.mark.parametrize("market,profile",
                             [("india", INDIA_PROFILE), ("usa", USA_PROFILE)])
    def test_a_six_month_back_asof_is_not_starved_on_live_data(self, market,
                                                               profile):
        """India returned 0 bars here before the ordering fix."""
        cutoff = date(2026, 5, 2)
        ds = adapt_prices(_LIVE, profile, cutoff=cutoff)
        if not ds.rows:
            pytest.skip("no raw bars for %s" % market)
        assert max(r.date for r in ds.rows) <= cutoff
        c = _counts(ds)
        ok = sum(1 for v in c.values() if v >= MAX_FEATURE_WINDOW_BARS)
        assert ok / len(c) > 0.95


class TestSmaBoundaryCases:
    """199 / 200 / 260 / insufficient · the exact threshold behaviour."""

    @staticmethod
    def _sma200(tmp_path, market, n_bars, asof=date(2026, 11, 3)):
        from backend.feature_store.features import technical
        _write(tmp_path, market, "AAA", _bars(n_bars, end=asof))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=asof)
        feats = technical.compute({"bar": ds}, ["AAA"], asof, market)
        return ds, feats["AAA"]

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_199_bars_abstain(self, tmp_path, market):
        ds, f = self._sma200(tmp_path, market, 199)
        assert _counts(ds)["AAA"] == 199
        assert f["sma_200"] is None, "199 bars cannot produce a 200-bar mean"
        assert f["price_above_sma200"] is None
        assert "AAA" in ds.notes

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_exactly_200_bars_produce_sma_200(self, tmp_path, market):
        ds, f = self._sma200(tmp_path, market, 200)
        assert _counts(ds)["AAA"] == 200
        assert f["sma_200"] is not None
        assert f["price_above_sma200"] in (0, 1)
        assert "AAA" not in (ds.notes or "")

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_260_bars_produce_sma_200_over_the_last_200(self, tmp_path,
                                                        market):
        """The window is 260 but the mean must use exactly 200 bars."""
        ds, f = self._sma200(tmp_path, market, 260)
        assert _counts(ds)["AAA"] == 260
        closes = sorted((r.date, r.close) for r in ds.rows)
        expected = sum(c for _, c in closes[-200:]) / 200.0
        assert abs(f["sma_200"] - round(expected, 4)) < 1e-3

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_more_than_the_window_is_truncated_to_the_window(self, tmp_path,
                                                             market):
        ds, f = self._sma200(tmp_path, market, 400)
        assert _counts(ds)["AAA"] == DEFAULT_LOOKBACK_BARS
        assert f["sma_200"] is not None

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_zero_bars_is_missing_not_zero(self, tmp_path, market):
        from backend.feature_store.features import technical
        _write(tmp_path, market, "AAA", _bars(5, end=date(2026, 11, 3)))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=date(2019, 1, 1))
        feats = technical.compute({"bar": ds}, ["AAA"], date(2019, 1, 1),
                                   market)
        assert feats.get("AAA", {}).get("sma_200") is None
        assert feats.get("AAA", {}).get("close") is None


class TestHistoricalSmaUsesOnlyBarsAvailableThen:
    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_the_historical_mean_matches_a_hand_computation(self, tmp_path,
                                                            market):
        """SMA-200 at a past asof must equal the mean of the 200 bars at
        or before that asof - not of the newest 200 bars on disk."""
        from backend.feature_store.features import technical
        asof = date(2026, 5, 1)
        _write(tmp_path, market, "AAA", _bars(500, end=date(2026, 11, 3)))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=asof)
        f = technical.compute({"bar": ds}, ["AAA"], asof, market)["AAA"]
        closes = sorted((r.date, r.close) for r in ds.rows)
        assert closes[-1][0] <= asof
        expected = sum(c for _, c in closes[-200:]) / 200.0
        assert abs(f["sma_200"] - round(expected, 4)) < 1e-3

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_two_different_asofs_give_two_different_means(self, tmp_path,
                                                           market):
        """If the historical value equalled today's, the cutoff is inert."""
        from backend.feature_store.features import technical
        _write(tmp_path, market, "AAA", _bars(500, end=date(2026, 11, 3)))
        out = {}
        for asof in (date(2026, 5, 1), date(2026, 11, 3)):
            ds = adapt_prices(tmp_path, _profile(market), cutoff=asof)
            out[asof] = technical.compute({"bar": ds}, ["AAA"], asof,
                                           market)["AAA"]["sma_200"]
        assert out[date(2026, 5, 1)] != out[date(2026, 11, 3)]


class TestLiveHistoricalCoverage:
    """Section B · measured per market, read-only."""

    @pytest.mark.parametrize("market,profile,n_expected_files",
                             [("india", INDIA_PROFILE, 230),
                              ("usa", USA_PROFILE, 908)])
    def test_historical_rows_match_source_availability(self, market, profile,
                                                       n_expected_files,
                                                       n_bars=DEFAULT_LOOKBACK_BARS):
        """rows == sum over symbols of min(bars_at_asof, window).

        The India figure is 230 x 260 = 59,800 exactly, because every
        India file holds at least 792 bars. USA falls short of that
        product only by its known thin tickers.
        """
        asof = date(2026, 5, 2)
        ds = adapt_prices(_LIVE, profile, cutoff=asof)
        if not ds.rows:
            pytest.skip("no raw bars for %s" % market)
        c = _counts(ds)
        assert ds.n_rows == sum(c.values())
        assert ds.n_rows <= len(c) * n_bars
        assert max(r.date for r in ds.rows) <= asof
        # no symbol exceeds the window
        assert max(c.values()) <= n_bars


class Test52WeekWindowIsHonest:
    """A feature named 52-week uses 252 bars or abstains. CEO 2026-11-04.

    The gate was `len(w52) >= 60`, so a sixty-bar range - under three
    months - was published as a 52-WEEK high, low and range position.
    Combined with the adapter's 90-bar cap, EVERY ticker in both markets
    reported a 90-day range under a 52-week name. Not null, not flagged,
    just wrong, at 98-99% coverage.
    """

    @staticmethod
    def _f(tmp_path, market, n_bars, asof=date(2026, 11, 3)):
        from backend.feature_store.features import technical
        _write(tmp_path, market, "AAA", _bars(n_bars, end=asof))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=asof)
        return technical.compute({"bar": ds}, ["AAA"], asof, market)["AAA"]

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_the_constant_is_one_trading_year(self, market):
        from backend.feature_store.features.technical import BARS_52W
        assert BARS_52W == 252

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_60_bars_no_longer_pass_as_52_weeks(self, tmp_path, market):
        f = self._f(tmp_path, market, 60)
        assert f["distance_from_52w_high_pct"] is None
        assert f["distance_from_52w_low_pct"] is None
        assert f["position_in_52w_range"] is None

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_112_bars_abstain(self, tmp_path, market):
        """FDXF held 112 bars and was still labelled 52-week."""
        assert self._f(tmp_path, market, 112)["position_in_52w_range"] is None

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_251_bars_abstain(self, tmp_path, market):
        assert self._f(tmp_path, market, 251)["distance_from_52w_high_pct"] is None

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_exactly_252_bars_publish(self, tmp_path, market):
        f = self._f(tmp_path, market, 252)
        assert f["distance_from_52w_high_pct"] is not None
        assert f["distance_from_52w_low_pct"] is not None
        assert f["position_in_52w_range"] is not None

    @pytest.mark.parametrize("market", ["india", "usa"])
    def test_the_published_range_uses_252_bars_not_the_whole_window(
            self, tmp_path, market):
        """The window is 260; the 52-week range must span exactly 252."""
        from backend.feature_store.features import technical
        asof = date(2026, 11, 3)
        _write(tmp_path, market, "AAA", _bars(400, end=asof))
        ds = adapt_prices(tmp_path, _profile(market), cutoff=asof)
        f = technical.compute({"bar": ds}, ["AAA"], asof, market)["AAA"]
        closes = [c for _, c in sorted((r.date, r.close) for r in ds.rows)]
        w = closes[-252:]
        last, hi, lo = closes[-1], max(w), min(w)
        assert abs(f["distance_from_52w_high_pct"]
                   - round((last / hi - 1) * 100, 3)) < 2e-3
        assert abs(f["position_in_52w_range"]
                   - round((last - lo) / (hi - lo), 4)) < 2e-3

    @pytest.mark.parametrize("market,profile",
                             [("india", INDIA_PROFILE), ("usa", USA_PROFILE)])
    def test_no_live_ticker_publishes_a_short_52_week_range(self, market,
                                                            profile):
        """Read-only. Every published value must have had 252 bars."""
        from backend.feature_store.features import technical
        asof = date(2026, 11, 3)
        ds = adapt_prices(_LIVE, profile, cutoff=asof)
        if not ds.rows:
            pytest.skip("no raw bars for %s" % market)
        counts = _counts(ds)
        syms = [s for s, n in counts.items() if n >= 30]
        feats = technical.compute({"bar": ds}, syms, asof, market)
        offenders = [s for s in syms
                     if feats.get(s, {}).get("position_in_52w_range") is not None
                     and counts[s] < 252]
        assert offenders == [], (
            "%d ticker(s) publish a 52-week range from fewer than 252 bars: %s"
            % (len(offenders), offenders[:6]))
