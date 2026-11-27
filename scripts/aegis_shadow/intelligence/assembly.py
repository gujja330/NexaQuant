"""Accumulate an auditable research panel in each accepted private workspace."""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.intelligence.lab import number
from scripts.aegis_shadow.intelligence.momentum import describe
from scripts.aegis_shadow.pipeline import _atomic, _json


def _series(work, market, symbol):
    from scripts.aegis_shadow.effective_risk import _bars

    frame = _bars(work, market, symbol)
    if frame is None:
        return {}
    keys = ("open", "high", "low", "close", "volume")
    if "volume" not in frame and "tick_volume" in frame:
        frame = frame.rename(columns={"tick_volume": "volume"})
    result = {}
    for index, values in zip(frame.index, frame.loc[:, list(keys)].itertuples(index=False, name=None), strict=True):
        values = tuple(float(value) for value in values)
        if all(number(value) and value > 0 for value in values[:4]) and number(values[4]) and values[4] >= 0:
            result[index] = dict(zip(keys, values, strict=True))
    return result


def rows_for_session(market, session, asof, members, histories, benchmark, version, horizons, cost, calendar):
    days = [day for day in calendar if day <= session][-61:]
    rows = []
    for symbol in sorted(set(members)):
        bars = histories.get(symbol, {})
        if len(days) != 61 or days[-1] != session or any(day not in benchmark or day not in bars for day in days):
            continue
        evidence = describe(*([bars[day][field] for day in days] for field in ("close", "high", "low", "volume")),
                            [benchmark[day]["close"] for day in days])
        if evidence:
            price_evidence = hashlib.sha256(json.dumps([(day, bars[day], benchmark[day]) for day in days],
                                                       sort_keys=True).encode()).hexdigest()
            rows.extend(dict(evidence, security_id=f"{market}:{symbol}", ticker=symbol, session=session,
                             observed_on=session, available_on=asof, horizon=horizon, eligible=True,
                             universe_version=version, signal_close=bars[session]["close"],
                             price_window_sha256=price_evidence,
                             benchmark_signal_close=benchmark[session]["close"], modeled_round_trip_cost=cost)
                        for horizon in horizons)
    return rows


def mature(rows, histories, benchmark, calendar, session, asof):
    offsets = {day: i for i, day in enumerate(calendar)}
    result = []
    for original in rows:
        row = dict(original)
        result.append(row)
        if "outcome" in row or row["session"] not in offsets:
            continue
        offset = offsets[row["session"]]
        exit_offset = offset + row["horizon"]
        if exit_offset >= len(calendar):
            continue
        entry, exit_day = calendar[offset + 1], calendar[exit_offset]
        if exit_day > session or row["available_on"] >= entry:
            continue
        bars = histories.get(row["ticker"], {})
        if any(day not in bars or day not in benchmark for day in (row["session"], entry, exit_day)):
            continue
        if (bars[row["session"]]["close"] != row["signal_close"] or
                benchmark[row["session"]]["close"] != row["benchmark_signal_close"]):
            row["label_status"] = "PRICE_BASIS_RECONCILIATION_REQUIRED"
            continue
        row.pop("label_status", None)
        row["outcome"] = {"entry_session": entry, "matured_on": exit_day, "available_on": asof,
                          "gross_return": bars[exit_day]["close"] / bars[entry]["open"] - 1,
                          "benchmark_return": benchmark[exit_day]["close"] / benchmark[entry]["open"] - 1,
                          "round_trip_cost": row["modeled_round_trip_cost"]}
        execution_days = calendar[offset + 1:exit_offset + 1]
        if all(day in bars for day in execution_days):
            row["execution_path"] = [{"session": day, **{field: bars[day][field] for field in ("open", "high", "low", "close")}}
                                     for day in execution_days]
    return result


def quality_evidence(work, market, cutoff):
    if market == "india":
        import pandas as pd

        path = contained(work, Path("data/raw/india/fundamentals.parquet"))
        if not path.is_file():
            return {}
        snapshots = pd.read_parquet(path).to_dict(orient="index")
        fields = ("eps_observed_at_utc", "returnOnEquity", "profitMargins")
    else:
        path = contained(work, Path("usa/reports/fundamentals.json"))
        if not path.is_file():
            return {}
        snapshots = _json(path)["tickers"]
        fields = ("as_of_utc", "roe", "profit_margin")
    fingerprint = digest(path)
    result = {}
    for symbol, snapshot in snapshots.items():
        stamp, roe, margin = (snapshot.get(field) for field in fields)
        if not isinstance(stamp, str) or not all(number(value) for value in (roe, margin)):
            continue
        try:
            observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if observed.utcoffset() is not None and observed <= cutoff:
            result[symbol] = {"as_of_utc": stamp, "roe": roe, "profit_margin": margin, "source_sha256": fingerprint}
    return result


def assemble(context, *, journal=None):
    import yaml

    work, market, session, asof = (context[key] for key in ("work", "market", "session", "asof"))
    source = contained(work, Path("reports/context/security_master_india.json" if market == "india" else "usa/reports/universe.json"))
    if not source.is_file():
        return None
    evidence = _json(source)
    if market == "india":
        if evidence.get("session") != session:
            return None
        members = set(evidence["configured"]) - set(evidence.get("data_pending", []))
        benchmark_id = "NSEI"
    else:
        members = {item["symbol"] for item in evidence["tickers"]}
        benchmark_id = "_IDX_GSPC"
    config = contained(work, Path("configs/execution_config.yaml"))
    costs = yaml.safe_load(config.read_text(encoding="utf-8"))["market_defaults"][market]
    cost = 2 * (costs["commission_bps"] + costs["min_slippage_bps"]) / 10000
    if not number(cost) or cost < 0:
        raise ValueError("invalid modeled research costs")
    folder = contained(work, Path("reports/research/intelligence") / market)
    folder.mkdir(parents=True, exist_ok=True)
    path = contained(folder, Path("prepared_panel.json"))
    old = _json(path) if path.is_file() else {}
    if old and (old.get("market"), old.get("benchmark_id")) != (market, benchmark_id):
        raise ValueError("retained panel has a different market or benchmark")
    historical = old.get("rows", [])
    histories, rejected = {}, {}
    held = {row["ticker"] for row in (journal or {}).get("positions", {}).values() if row.get("ticker")}
    pending = {row["ticker"] for row in historical if "outcome" not in row}
    for symbol in sorted(members | pending | held):
        try:
            histories[symbol] = _series(work, market, symbol)
        except (KeyError, OSError, TypeError, ValueError) as error:
            rejected[symbol] = str(error)
    benchmark = _series(work, market, benchmark_id)
    calendar = sorted(day.isoformat() for day in context["calendar"].closes)
    refreshed = rows_for_session(market, session, asof, members | held, histories, benchmark, digest(source), (5, 20, 60), cost, calendar)
    day = date.fromisoformat(session)
    cutoff = datetime.combine(day, context["calendar"].closes[day], context["calendar"].timezone)
    quality = quality_evidence(work, market, cutoff)
    sectors = {item["symbol"]: item.get("sector") for item in evidence["tickers"]} if market == "usa" else {}
    for row in refreshed:
        row["eligible"] = row["ticker"] in members
        sector = sectors.get(row["ticker"])
        if isinstance(sector, str) and sector.casefold() not in {"unknown", "", "n/a"}:
            row["sector"] = sector
        value = quality.get(row["ticker"])
        row["quality_evidence"] = value
        row["strategy_flags"] = dict(row["strategy_flags"], quality_momentum=(
            value["roe"] > 0 and value["profit_margin"] > 0 and row["momentum_medium"] > 0 if value else None))
    seen = {(row["security_id"], row["session"], row["horizon"]) for row in historical}
    historical.extend(row for row in refreshed if (row["security_id"], row["session"], row["horizon"]) not in seen)
    lineage = old.get("capture_provenance", {})
    if session not in lineage:
        reports = "reports" if market == "india" else "usa/reports"
        available = [source, config, contained(work, Path(reports) / "recommendations.json"),
                     contained(work, Path(f"features/{market}/{asof}.parquet"))]
        if journal and journal.get("observation_path"):
            available.append(contained(work, Path(journal["observation_path"])))
        lineage[session] = {"captured_on": asof, "files": {item.relative_to(work).as_posix(): digest(item)
                                                        for item in available if item.is_file()}}
    result = {"schema": "aegis.shadow.research_panel.v1", "market": market, "benchmark_id": benchmark_id,
              "source": "Private observed membership and completed OHLCV", "minimum_observations": 30,
              "through": session, "rejected": rejected, "capture_provenance": lineage,
              "rows": mature(historical, histories, benchmark, calendar, session, asof)}
    _atomic(folder, path.name, json.dumps(result, sort_keys=True, indent=2, allow_nan=False).encode())
    return result
