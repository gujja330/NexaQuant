"""Read-only Phase 3 analyses. Writes only to the specified research directory."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.research._paths import price_parquet_path


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def day(value):
    return str(value or "")[:10]


def symbol(value):
    return str(value or "").strip().upper().removesuffix(".NS").removesuffix(".BO")


def number(value):
    return isinstance(value, (float, int)) and pd.notna(value)


def stats(values):
    values = pd.Series(list(values), dtype=float).dropna()
    wins, losses = values[values > 0], values[values < 0]
    return {
        "n": len(values), "mean_pct": float(values.mean()) if len(values) else None,
        "wins": len(wins), "win_pct": 100 * len(wins) / len(values) if len(values) else None,
        "gross_profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
    }


def workbook_rows(path, sheet):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = book[sheet].values
        headers = next(row for row in rows if "Position ID" in row and "Ticker" in row)
        return [dict(zip(headers, row)) for row in rows if row[headers.index("Position ID")]]
    finally:
        book.close()


def registry(root):
    rows = {}
    for line in (root / "reports/research/opportunity_registry.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            rows[item["market"], item["opportunity_id"]] = item
    return rows


def reconcile(root, exits, episodes):
    loss = load(root / "reports/research/loss_patterns_india.json")
    lookup = defaultdict(list)
    for (market, oid), row in episodes.items():
        if market == "india" and row["status"] == "CLOSED":
            key = symbol(row["ticker"]), row["runner"], day(row["created_date"]), day(row["closed_date"])
            lookup[key].append(oid)
    realized = {row["Position ID"]: row for row in exits
                if row["Record Type"] == "REALIZED EXIT" and row["Engine"] == "R2"}
    linked = set()
    results = []
    for row in loss["exits"]:
        key = symbol(row["ticker"]), row["runner"], day(row["entry_date"]), day(row["exit_date"])
        ids = lookup.get(key, [])
        oid = ids[0] if len(ids) == 1 else None
        trade = realized.get(oid, {})
        if trade:
            linked.add(oid)
        results.append({
            "position_id": oid, "ticker": key[0], "runner": key[1], "entry_date": key[2],
            "exit_date": key[3], "loss_return_pct": row["pnl_pct"], "loss_is_win": row["is_win"],
            "loss_category": row["category"], "workbook_return_pct": trade.get("P&L %"),
            "workbook_record_type": trade.get("Record Type"),
            "registry_reason": episodes.get(("india", oid), {}).get("closed_reason"),
            "disposition": "matched" if trade else "ambiguous_registry_key" if len(ids) > 1
            else "loss_attribution_only" if oid else "registry_key_unresolved",
        })
    for oid, trade in realized.items():
        if oid not in linked:
            results.append({"position_id": oid, "ticker": trade["Ticker"], "runner": trade["Engine"],
                            "entry_date": day(trade["Entry Date"]), "exit_date": day(trade["Exit Date"]),
                            "workbook_return_pct": trade["P&L %"], "workbook_record_type": trade["Record Type"],
                            "disposition": "workbook_only"})
    return results, {
        "loss_report_asof": loss["asof"], "loss_count": loss["n_positions"],
        "loss_wins_over_half_percent": loss["n_wins"],
        "loss_mean_pct": stats(row["pnl_pct"] for row in loss["exits"])["mean_pct"],
        "realized_workbook": stats(row["P&L %"] for row in realized.values()),
        "joined": dict(Counter(row["disposition"] for row in results)),
    }


def prices(path):
    if not path or not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    frame.columns = frame.columns.str.lower()
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    frame.index = index.tz_localize(None).normalize()
    return frame.sort_index() if "close" in frame and frame.index.is_unique else pd.DataFrame()


def point(frame, timestamp, column="close"):
    if column not in frame or timestamp not in frame.index:
        return None
    value = frame.at[timestamp, column]
    return float(value) if number(value) and value > 0 else None


def aligned(quote, close):
    return number(quote) and close is not None and abs(quote / close - 1) <= 0.005


def episode_returns(root, market, current, exits, bars):
    benchmark = price_parquet_path(root, market, "NSEI" if market == "india" else "_IDX_GSPC")
    broad = prices(benchmark)
    bank = prices(price_parquet_path(root, market, "NSEBANK")) if market == "india" else pd.DataFrame()
    results = []
    for population, rows in (("CURRENT", current), ("REALIZED EXIT", exits)):
        for row in rows:
            start = pd.to_datetime(day(row["Entry Date"]), errors="coerce")
            end = pd.to_datetime(day(row["Market Data As-of"] if population == "CURRENT" else row["Exit Date"]),
                                 errors="coerce")
            quoted_end = row["Last Price"] if population == "CURRENT" else row["Exit Price"]
            frame = bars(market, symbol(row["Ticker"]))
            p0, p1 = point(frame, start), point(frame, end)
            b0, b1 = point(broad, start), point(broad, end)
            same = aligned(row["Entry Price"], p0) and aligned(quoted_end, p1)
            stock = 100 * (p1 / p0 - 1) if same else None
            market_roi = 100 * (b1 / b0 - 1) if b0 and b1 and end >= start else None
            # Financial Services also includes nonbank names. Nifty Bank is an
            # explicitly labelled exposure proxy, not a matched sector benchmark.
            k0, k1 = (point(bank, start), point(bank, end)) if row["Sector"] == "Financial Services" else (None, None)
            results.append({
                "market": market, "position_id": row["Position ID"], "ticker": row["Ticker"],
                "engine": row["Engine"], "sector": row["Sector"], "population": population,
                "start": day(row["Entry Date"]), "end": str(end.date()) if pd.notna(end) else None,
                "same_date_close_agreement": same, "stock_saved_close_return_pct": stock,
                "broad_price_index_pct": market_roi,
                "excess_pp": stock - market_roi if stock is not None and market_roi is not None else None,
                "nifty_bank_proxy_pct": 100 * (k1 / k0 - 1) if k0 and k1 else None,
            })
    return results


def forward(root, bars, end):
    """Use sealed India scores and the next benchmark session close as entry."""
    sessions = prices(price_parquet_path(root, "india", "NSEI"))["close"].dropna()
    sessions = sessions.loc[:end]
    result = []
    for path in sorted(root.glob("history/india/*/r2_scores.parquet")):
        if not (path.parent / "SEALED").exists():
            continue
        signal = pd.Timestamp(path.parent.name)
        if signal > end:
            continue
        start = sessions.index.searchsorted(signal, side="right")
        frame = pd.read_parquet(path)
        for row in frame.itertuples(index=False):
            if not row.would_be_new and not row.disagreement_flag:
                continue
            ticker = symbol(row.ticker)
            stock = bars("india", ticker)
            if start >= len(sessions):
                continue
            p0 = point(stock, sessions.index[start])
            if not p0:
                continue
            cohort = "would_be_new" if row.would_be_new else "disagreement"
            for horizon in (3, 5, 10, 15, 20, 30, 45, 60, 90):
                finish = start + horizon
                if finish >= len(sessions):
                    continue
                period = sessions.index[start:finish + 1]
                if "close" not in stock:
                    continue
                close = stock["close"].reindex(period)
                if close.isna().any() or (close <= 0).any():
                    continue
                roi = 100 * (float(close.iloc[-1]) / p0 - 1)
                broad = 100 * (sessions.iloc[finish] / sessions.iloc[start] - 1)
                delta = close / close.cummax() - 1
                result.append({
                    "ticker": ticker, "signal": day(signal), "entry": day(period[0]), "exit": day(period[-1]),
                    "cohort": cohort, "horizon_sessions": horizon,
                    "calendar_segment": "november" if signal.month == 11 else "pre_november",
                    "gross_return_pct": roi, "net_after_20bps_pct": roi - 0.20, "excess_pp": roi - broad,
                    "close_path_mfe_pct": 100 * (float(close.max()) / p0 - 1),
                    "close_path_drawdown_pct": 100 * float(delta.min()),
                })
    return result


def targets(root, current, bars, asof):
    state = load(root / "reports/context/canonical_lifecycle_india.json")
    stored = {r["position_id"]: r for r in state["current"]}
    decisions = load(root / f"reports/audit/dynamic_exit_decisions_india_{asof}.json")
    decisions = {r["opportunity_id"]: r for r in decisions["decisions"]}
    result = []
    for row in current:
        oid = row["Position ID"]
        record, decision = stored.get(oid, {}), decisions.get(oid, {})
        target, last = record.get("target"), row["Last Price"]
        end = day(row["Market Data As-of"])
        frame = bars("india", symbol(row["Ticker"]))
        high = None
        if "high" in frame and end:
            # The entry-session high could have preceded the close-entry.
            window = frame.loc[(frame.index > pd.Timestamp(row["Entry Date"])) &
                               (frame.index <= pd.Timestamp(end)), "high"]
            high = float(window.max()) if len(window.dropna()) else None
        result.append({
            "position_id": oid, "ticker": row["Ticker"], "engine": row["Engine"],
            "close_date": end, "workbook_return_pct": row["P&L %"], "last": last,
            "entry": row["Entry Price"], "stop": row["Stop"], "displayed_target": row["Target"],
            "stored_target": target, "prior_high_on_saved_basis": high,
            "target_disposition": "withheld_at_or_below_last" if number(target) and number(last) and target <= last
            else "calculation_unavailable" if not number(target) else "display_eligible",
            "target_high_comparison": high >= target if high is not None and number(target) else None,
            "bridge_t1": decision.get("t1_price"), "bridge_t2": decision.get("t2_price"),
            "bridge_verdict": decision.get("event"), "bridge_reason": decision.get("reason"),
            "bridge_asof": decision.get("asof"), "bridge_action": decision.get("action"),
        })
    return result


def exit_trial(path, entry, model):
    """Model daily stop orders using only information known before each session."""
    peak = entry
    for dt, row in path.iterrows():
        stop = entry * 0.95
        if model == "breakeven_after_8pct" and peak >= entry * 1.08:
            stop = entry
        if model == "trail_8pct":
            stop = max(stop, peak * 0.92)
        if model != "fixed" and min(row.open, row.low) <= stop:
            return dt, min(float(row.open), stop), "stop"
        peak = max(peak, float(row.high))
    return path.index[-1], float(path["close"].iloc[-1]), "horizon"


def exit_trials(root, market, rows, bars, asof):
    """Run matched fixed-session and stop experiments off documented entry dates."""
    bench = prices(price_parquet_path(root, market, "NSEI" if market == "india" else "_IDX_GSPC"))
    if bench.empty:
        return []
    sessions = bench.loc[:asof, "close"].dropna()
    result = []
    for row in rows:
        if row["Engine"] != "R2":
            continue
        stock = bars(market, symbol(row["Ticker"]))
        if not {"open", "high", "low", "close"} <= set(stock):
            continue
        start = pd.to_datetime(day(row["Entry Date"]), errors="coerce")
        if start not in sessions.index:
            continue
        first = sessions.index.get_loc(start)
        entry = point(stock, start)
        if not aligned(row["Entry Price"], entry):
            continue
        for horizon in (3, 5, 10, 15, 20, 30, 45, 60, 90):
            last = first + horizon
            if last >= len(sessions):
                continue
            future = stock.reindex(sessions.index[first + 1:last + 1])[["open", "high", "low", "close"]]
            if future.isna().any().any() or (future <= 0).any().any():
                continue
            for rule in ("fixed", "initial_stop_5pct", "breakeven_after_8pct", "trail_8pct") if horizon == 20 else ("fixed",):
                exited, fill, reason = exit_trial(future, entry, rule)
                holding = sessions.index.get_loc(exited) - first
                path = future.loc[:exited]
                before_exit = path["high"].iloc[:-1]
                high = max(entry, fill, float(before_exit.max())) if len(before_exit) else max(entry, fill)
                roi = 100 * (fill / entry - 1)
                # At a triggered stop, the day's benchmark close would be after
                # the unknown fill time, so only compare fixed close exits.
                excess = roi - 100 * (sessions.at[exited] / sessions.at[start] - 1) if reason == "horizon" else None
                result.append({
                    "market": market, "position_id": row["Position ID"], "ticker": row["Ticker"],
                    "entry": day(start), "exit": day(exited), "rule": rule, "test_horizon": horizon,
                    "capital_days": holding, "exit_reason": reason, "gap_aware_fill": fill,
                    "net_return_pct": roi - 0.20, "close_benchmark_excess_pp": excess,
                    "mfe_lower_bound_pct": 100 * (high / entry - 1),
                    "calendar_segment": "november" if start.month == 11 else "pre_november",
                })
    return result


def capital_trials(root, bars, asof, start):
    """Exploratory bounded-capital replay of sealed scores at next-session closes."""
    bench = prices(price_parquet_path(root, "india", "NSEI"))
    marks = bench.loc[start:asof, "close"].dropna()
    schedule = {}
    for path in sorted(root.glob("history/india/*/r2_scores.parquet")):
        if not (path.parent / "SEALED").exists():
            continue
        signal = pd.Timestamp(path.parent.name)
        if signal < marks.index[0] or signal > asof:
            continue
        index = marks.index.searchsorted(signal, side="right")
        if index >= len(marks):
            continue
        table = pd.read_parquet(path, columns=["ticker", "ensemble_score"]).dropna()
        schedule[marks.index[index]] = {
            symbol(row.ticker): float(row.ensemble_score)
            for row in table.itertuples(index=False)
        }
    snapshots, findings = [], []
    for slots in (10, 20):
        for rule in ("hold_20", "rotate_one_on_score_gap"):
            cash, turnover, fees = 1.0, 0.0, 0.0
            holdings = {}
            daily = []
            blocked = None
            for i, dt in enumerate(marks.index):
                close = {t: point(bars("india", t), dt) for t in holdings}
                if any(value is None for value in close.values()):
                    blocked = {"date": day(dt), "unpriced": [t for t, value in close.items() if value is None]}
                    break
                scores = schedule.get(dt, {})
                candidates = sorted(scores, key=lambda t: (-scores[t], t))
                exited = set()
                sell = [t for t, (_, opened) in holdings.items() if i - opened >= 20]
                if rule == "rotate_one_on_score_gap" and len(holdings) == slots and not sell:
                    incoming = next((t for t in candidates if t not in holdings
                                     and point(bars("india", t), dt)), None)
                    weakest = min((t for t in holdings if t in scores),
                                  key=lambda t: (scores[t], t), default=None)
                    if incoming and weakest and scores[incoming] - scores[weakest] >= 0.20:
                        sell.append(weakest)
                for ticker in sell:
                    qty, _ = holdings.pop(ticker)
                    value = qty * close[ticker]
                    cash += value * 0.999
                    fees += value * 0.001
                    turnover += value
                    exited.add(ticker)
                equity = cash + sum(qty * close[t] for t, (qty, _) in holdings.items())
                for ticker in candidates:
                    if len(holdings) >= slots or cash <= 1e-12:
                        break
                    if scores[ticker] <= 0 or ticker in holdings or ticker in exited:
                        continue
                    fill = point(bars("india", ticker), dt)
                    if fill is None:
                        continue
                    budget = min(equity / slots, cash)
                    value = budget / 1.001
                    holdings[ticker] = (value / fill, i)
                    close[ticker] = fill
                    cash -= budget
                    fees += budget - value
                    turnover += value
                equity = cash + sum(qty * close[t] for t, (qty, _) in holdings.items())
                daily.append({"date": day(dt), "equity": equity, "cash": cash, "occupied_slots": len(holdings)})
            snapshots.extend({**row, "slots": slots, "rule": rule, "start": start} for row in daily)
            path = pd.DataFrame(daily)
            last = pd.Timestamp(daily[-1]["date"])
            findings.append({
                "slots": slots, "rule": rule, "sessions": len(daily), "start": start, "last": day(last),
                "blocked": blocked, "net_return_pct": 100 * (daily[-1]["equity"] - 1),
                "benchmark_price_return_pct": 100 * (marks.at[last] / marks.iloc[0] - 1),
                "max_drawdown_pct": 100 * float((path["equity"] / path["equity"].cummax() - 1).min()),
                "mean_cash_pct": 100 * float((path["cash"] / path["equity"]).mean()),
                "traded_notional_per_initial_capital": turnover, "fees_per_initial_capital": fees,
            })
    return snapshots, findings


def opportunity_trials(root, bars, asof):
    """Independent diagnostic screens over point-in-time saved features."""
    bench = prices(price_parquet_path(root, "india", "NSEI")).loc[:asof, "close"].dropna()
    rows = []
    for path in sorted(root.glob("history/india/*/technical_features.parquet")):
        if not (path.parent / "SEALED").exists():
            continue
        signal = pd.Timestamp(path.parent.name)
        start = bench.index.searchsorted(signal, side="right")
        if start + 5 >= len(bench):
            continue
        features = pd.read_parquet(path).drop_duplicates(subset="ticker", keep=False).set_index("ticker")
        quality = features["fund_quality_score"] >= features["fund_quality_score"].quantile(0.75)
        strength = features["return_20d_pct"] - features["sector_return_1m_pct"]
        flags = pd.DataFrame({
            "sector_relative_strength": (strength > 0) & (strength >= strength.quantile(0.75)),
            "sector_leader_positive_momentum": features["sector_is_leader"].eq(True) & features["return_5d_pct"].gt(0),
            "quality_pullback": quality & features["return_5d_pct"].between(-5, 0, inclusive="left")
            & features["price_above_sma50"].eq(True),
            "breakout_volume_screen": features["distance_from_52w_high_pct"].abs().le(2)
            & features["volume_ratio_5v20"].ge(1.25) & features["return_5d_pct"].gt(0),
            "positive_earnings_surprise": features["earn_last_surprise_pct"].gt(0),
            "post_correction_rebound": features["return_20d_pct"].lt(-5) & features["return_5d_pct"].gt(1),
        }).fillna(False)
        for ticker, tags in flags.iterrows():
            rules = ["all_sealed_features", *[name for name, matched in tags.items() if matched]]
            frame = bars("india", symbol(ticker))
            entry = point(frame, bench.index[start])
            if not entry:
                continue
            for horizon in (5, 20):
                finish = start + horizon
                if finish >= len(bench):
                    continue
                exit_close = point(frame, bench.index[finish])
                if not exit_close:
                    continue
                stock = 100 * (exit_close / entry - 1)
                broad = 100 * (bench.iloc[finish] / bench.iloc[start] - 1)
                for rule in rules:
                    rows.append({
                        "signal": day(signal), "ticker": symbol(ticker), "rule": rule, "horizon": horizon,
                        "entry": day(bench.index[start]), "exit": day(bench.index[finish]),
                        "net_pct": stock - 0.20, "net_excess_pp": stock - 0.20 - broad,
                        "segment": "november" if signal.month == 11 else "pre_november",
                    })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--asof", type=date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    @lru_cache(maxsize=None)
    def bars(market, ticker):
        return prices(price_parquet_path(root, market, ticker))

    def write(name, rows):
        pd.DataFrame(rows).to_csv(out / name, index=False, encoding="utf-8-sig")

    episode_data, trials, summary = [], [], {}
    reg = registry(root)
    for market in ("india", "usa"):
        path = root / f"reports/telegram/aegis_{market}_{args.asof}.xlsx"
        if not path.exists():
            path = root / f"reports/telegram/aegis_history_{market}.xlsx"
        current = workbook_rows(path, "CURRENT")
        exits = workbook_rows(path, "EXIT HISTORY")
        realized = [r for r in exits if r["Record Type"] == "REALIZED EXIT"]
        rows = episode_returns(root, market, current, realized, bars)
        episode_data.extend(rows)
        trials.extend(exit_trials(root, market, current + realized, bars, pd.Timestamp(args.asof)))
        summary[market] = {}
        for population in ("CURRENT", "REALIZED EXIT"):
            selected = [row for row in rows if row["population"] == population and row["engine"] == "R2"]
            paired = [row for row in selected if row["excess_pp"] is not None]
            summary[market][population] = {
                "total_episodes": len(selected), "paired_price_proxy": stats(row["excess_pp"] for row in paired),
                "paired_stock": stats(row["stock_saved_close_return_pct"] for row in paired),
                "paired_benchmark": stats(row["broad_price_index_pct"] for row in paired),
            }
        if market == "india":
            reconciliation, summary["performance_reconciliation"] = reconcile(root, exits, reg)
            write("india-performance-reconciliation.csv", reconciliation)
            write("india-target-audit.csv", targets(root, current, bars, args.asof))
    write("episode-benchmark-attribution.csv", episode_data)
    write("historical-entry-exit-trials.csv", trials)
    trial_groups = defaultdict(list)
    for row in trials:
        trial_groups[row["market"], row["test_horizon"], row["rule"], row["calendar_segment"]].append(row)
    write("historical-entry-exit-summary.csv", [
        {"market": key[0], "horizon": key[1], "rule": key[2], "segment": key[3],
         **stats(r["net_return_pct"] for r in group),
         "mean_holding_sessions": sum(r["capital_days"] for r in group) / len(group),
         "mean_exit_mfe_lower_bound_pct": sum(r["mfe_lower_bound_pct"] for r in group) / len(group),
         "mean_close_excess_pp": stats(r["close_benchmark_excess_pp"] for r in group)["mean_pct"]}
        for key, group in sorted(trial_groups.items())
    ])

    rows = forward(root, bars, pd.Timestamp(args.asof))
    write("india-sealed-forward-observations.csv", rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row["cohort"], row["horizon_sessions"], row["calendar_segment"]].append(row)
    grid = [{"cohort": key[0], "horizon_sessions": key[1], "calendar_segment": key[2],
             "distinct_tickers": len({r["ticker"] for r in group}),
             "distinct_signal_dates": len({r["signal"] for r in group}),
             **stats(r["net_after_20bps_pct"] for r in group),
             "mean_excess_pp": sum(r["excess_pp"] for r in group) / len(group)}
            for key, group in sorted(groups.items())]
    write("india-sealed-horizon-comparison.csv", grid)
    paths, capital = [], []
    for start in ("2026-09-01", "2026-11-01"):
        portfolio_paths, results = capital_trials(root, bars, pd.Timestamp(args.asof), start)
        paths.extend(portfolio_paths)
        capital.extend(results)
    write("india-capital-trial-paths.csv", paths)
    summary["exploratory_capital_trials"] = capital
    opportunity = opportunity_trials(root, bars, pd.Timestamp(args.asof))
    pd.DataFrame(opportunity).to_parquet(out / "india-opportunity-observations.parquet", index=False)
    opportunity_groups = defaultdict(list)
    for row in opportunity:
        opportunity_groups[row["rule"], row["horizon"], row["segment"]].append(row)
    write("india-opportunity-comparison.csv", [
        {"rule": key[0], "horizon": key[1], "segment": key[2],
         "distinct_signal_dates": len({r["signal"] for r in group}),
         **stats(r["net_pct"] for r in group),
         "mean_net_excess_pp": stats(r["net_excess_pp"] for r in group)["mean_pct"]}
        for key, group in sorted(opportunity_groups.items())
    ])
    summary["interpretation"] = "Observational saved-close proxies. Basis matching to workbook is not independent trade verification; overlapping signals are not independent observations."
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
