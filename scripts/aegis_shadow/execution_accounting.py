"""Reconcile simulated fills to a dated opening ledger without mutating it."""
import json
from math import isfinite
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


def reconcile(opening, fills, market, session, previous):
    if (opening.get("market"), opening.get("opening_session"), opening.get("mark_session")) != (
            market, previous, session) or not opening.get("source"):
        raise ValueError("simulator opening ledger identity or source disagrees")
    cash = opening["cash"]
    holdings = dict(opening["shares"])
    marks = opening["close_prices"]
    if not isfinite(cash) or cash < 0 or any(not isfinite(value) or value <= 0 for value in holdings.values()):
        raise ValueError("invalid cash or holdings in long-only opening ledger")
    seen = set()
    for fill in fills:
        key, ticker = fill["txn_id"], fill["ticker"]
        if not key or key in seen or fill["market"] != market or fill["fill_date"] != session:
            raise ValueError("duplicate fill or inconsistent fill identity")
        seen.add(key)
        action = fill["action"]
        if fill["side"] != "LONG" or action not in {"OPEN", "INCREASE", "CLOSE", "DECREASE"}:
            raise ValueError(f"unsupported simulator direction or action for {ticker}")
        quantity, notional, commission = (fill[field] for field in ("shares", "filled_notional", "commission_amount"))
        if not all(isfinite(value) for value in (quantity, notional, commission)) or min(quantity, notional) <= 0 or commission < 0:
            raise ValueError(f"invalid simulated fill for {ticker}")
        sign = 1 if action in {"OPEN", "INCREASE"} else -1
        updated = holdings.get(ticker, 0.0) + sign * quantity
        if updated < -1e-6:
            raise ValueError(f"simulated reduction exceeds opening holdings for {ticker}")
        if updated > 1e-6:
            holdings[ticker] = updated
        else:
            holdings.pop(ticker, None)
        cash -= sign * notional + commission
    if cash < -0.005:
        raise ValueError("simulated fills exceed available cash")
    missing = [ticker for ticker in holdings if ticker not in marks or not isfinite(marks[ticker]) or marks[ticker] <= 0]
    if missing:
        raise ValueError(f"missing completed-session marks for {', '.join(sorted(missing))}")
    notional = sum(shares * marks[ticker] for ticker, shares in holdings.items())
    return {"status": "SIMULATION_RECONCILED", "market": market, "session": session, "opening_session": previous,
            "source": opening["source"], "fill_ids": sorted(seen), "ending_cash": round(cash, 4),
            "ending_shares": holdings, "ending_equity": round(cash + notional, 4)}


def audit(context):
    work, market, session = (context[key] for key in ("work", "market", "session"))
    path = contained(context["storage"], Path("inputs") / market / "simulator_opening.json")
    report = {"status": "RESEARCH_INSUFFICIENT_EVIDENCE", "market": market, "session": session,
              "reason": "dated simulator opening ledger is unavailable"}
    if path.is_file():
        import pandas as pd

        reports = "reports" if market == "india" else "usa/reports"
        ledger = contained(work, Path(reports) / "execution_ledger.parquet")
        try:
            summary = _json(contained(work, Path(reports) / "execution_summary.json"))
            fills = pd.read_parquet(ledger)
            fills["fill_date"] = pd.to_datetime(fills["fill_date"], errors="raise").dt.strftime("%Y-%m-%d")
            rows = fills.loc[fills["fill_date"] == session].to_dict(orient="records")
            if (summary.get("market"), summary.get("asof"), summary.get("n_fills_generated")) != (
                    market, session, len(rows)):
                raise ValueError("dated execution summary disagrees with the fill ledger")
            previous = max(day for day in context["calendar"].closes if day.isoformat() < session)
            report = reconcile(_json(path), rows, market, session, previous.isoformat())
            report.update(opening_sha256=digest(path), fill_ledger_sha256=digest(ledger))
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            report.update(status="RESEARCH_INSUFFICIENT_EVIDENCE", reason=str(error))
    folder = contained(work, Path("reports/research") / market)
    folder.mkdir(parents=True, exist_ok=True)
    _atomic(folder, "shadow_execution_accounting.json", json.dumps(report, indent=2).encode())
    return report["status"] if report["status"] == "RESEARCH_INSUFFICIENT_EVIDENCE" else None
