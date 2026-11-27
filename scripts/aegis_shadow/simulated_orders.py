"""Generate deterministic research-only orders from portfolio instructions."""
import hashlib
import json
from math import isfinite
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.execution_accounting import reconcile
from scripts.aegis_shadow.pipeline import _atomic, _json

BOOK = Path(".shadow-simulator-book.json")


def _identity(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def simulate(opening, portfolio, diff, episodes, market, asof, session, previous, costs, risk, policy, source):
    if any((document.get("market"), document.get("asof")) != (market, asof) for document in (portfolio, diff)):
        raise ValueError("portfolio and instruction dates disagree")
    if (opening.get("market"), opening.get("opening_session"), opening.get("mark_session")) != (market, previous, session):
        raise ValueError("opening evidence does not match market or sessions")
    shares, marks, prices = (opening[name] for name in ("shares", "close_prices", "opening_prices"))
    basis = dict(opening["cost_basis"])
    cash = opening["cash"]
    def valid(number):
        return type(number) in (int, float) and isfinite(number) and number > 0

    if (type(cash) not in (int, float) or not isfinite(cash) or cash < 0 or
            any(not all(valid(value) for value in (quantity, prices.get(symbol), basis.get(symbol)))
                for symbol, quantity in shares.items())):
        raise ValueError("opening capital or holding cost basis is invalid")
    capital = cash + sum(quantity * prices[symbol] for symbol, quantity in shares.items())
    if not valid(capital):
        raise ValueError("opening equity must be positive")
    target = {row["ticker"]: row for row in portfolio["snapshot"]["positions"]}
    if len(target) != len(portfolio["snapshot"]["positions"]):
        raise ValueError("duplicate portfolio target identity")
    commission, slip = (costs[name] / 10000 for name in ("commission_bps", "min_slippage_bps"))
    if not all(isfinite(value) and 0 <= value < 1 for value in (commission, slip)):
        raise ValueError("configured commission or slippage is invalid")
    instructions = sorted(diff["instructions"], key=lambda item: (item["action"] not in {"CLOSE", "DECREASE"}, item["ticker"]))
    seen, orders, fills, realized = set(), [], [], 0.0
    for instruction in instructions:
        ticker, action = instruction["ticker"], instruction["action"]
        if ticker in seen:
            raise ValueError("duplicate portfolio instruction")
        seen.add(ticker)
        if action == "HOLD":
            continue
        if action not in {"OPEN", "INCREASE", "CLOSE", "DECREASE"}:
            raise ValueError(f"unsupported portfolio action for {ticker}")
        position = target.get(ticker, {})
        weight = position.get("weight", 0)
        if not isfinite(weight) or weight < 0 or abs(weight - instruction["new_weight"]) > 1e-5:
            raise ValueError(f"target weight or direction disagrees for {ticker}")
        quantity = shares.get(ticker, 0)
        pid = opening.get("episodes", {}).get(ticker) if quantity else episodes.get(ticker)
        mark = marks.get(ticker)
        if not pid or not valid(mark):
            raise ValueError(f"episode or completed-session simulation mark is missing for {ticker}")
        desired = weight * capital / mark
        delta = desired - quantity
        if ((action == "OPEN" and (quantity or delta <= 0)) or (action == "INCREASE" and (not quantity or delta <= 0))
                or (action == "CLOSE" and (not quantity or weight != 0))
                or (action == "DECREASE" and (delta >= 0 or desired <= 0))):
            raise ValueError(f"action contradicts opening and target quantities for {ticker}")
        price = mark * (1 + slip if delta > 0 else 1 - slip)
        notional = abs(delta) * price
        fee = notional * commission
        decision = _identity(market, asof, session, pid, ticker, action, weight, policy, source)
        order = _identity(decision, quantity, desired, capital, price, fee)
        orders.append({"order_id": order, "decision_id": decision, "episode_id": pid, "ticker": ticker,
                       "action": action, "side": "LONG", "opening_quantity": quantity,
                       "target_quantity": desired, "estimated_price": price, "estimated_fee": fee,
                       "authorized_capital": capital, "reason": instruction.get("reason")})
        fills.append({"txn_id": _identity(order, "hypothetical"), "market": market, "ticker": ticker,
                      "fill_date": session, "action": action, "side": "LONG", "shares": abs(delta),
                      "fill_price": price, "filled_notional": notional, "commission_amount": fee})
        if delta > 0:
            basis[ticker] = (quantity * basis.get(ticker, 0) + notional + fee) / desired
        else:
            realized += notional - fee - abs(delta) * basis[ticker]
    if set(shares) | set(target) != seen:
        raise ValueError("portfolio diff does not account for all opening and target holdings")
    result = reconcile(opening, fills, market, session, previous)
    ending = result["ending_shares"]
    equity = result["ending_equity"]
    if equity <= 0 or result["ending_cash"] + 0.005 < equity * portfolio["snapshot"]["cash_reserve_target"]:
        raise ValueError("simulated positions violate the configured cash reserve after costs")
    sectors = {}
    for symbol, quantity in ending.items():
        weight = quantity * marks[symbol] / equity
        sector = target.get(symbol, {}).get("sector") or opening.get("sectors", {}).get(symbol)
        if not sector or sector.lower() == "unknown" or weight > risk["per_ticker_cap"] + 1e-5:
            raise ValueError(f"simulated position cap or sector evidence failed for {symbol}")
        sectors[sector] = sectors.get(sector, 0) + weight
    if any(weight > risk["per_sector_cap"] + 1e-5 for weight in sectors.values()):
        raise ValueError("simulated sector cap exceeded")
    return dict(result, classification="HYPOTHETICAL_RESEARCH_FILLS", policy_sha256=policy, orders=orders, fills=fills,
                opening_equity=capital, realized_pnl=realized,
                unrealized_pnl=sum(quantity * (marks[symbol] - basis[symbol]) for symbol, quantity in ending.items()),
                ending_cost_basis={symbol: basis[symbol] for symbol in ending},
                ending_marks={symbol: marks[symbol] for symbol in ending},
                ending_episodes={symbol: opening.get("episodes", {}).get(symbol) or episodes[symbol] for symbol in ending},
                ending_sectors={symbol: target.get(symbol, {}).get("sector") or opening.get("sectors", {}).get(symbol)
                                for symbol in ending})


def roll_opening(book, market, previous, session, prices):
    """Carry a certified hypothetical account into the next reviewed session."""
    if (book.get("schema"), book.get("market"), book.get("session")) != ("aegis.shadow.simulator_book.v1", market, previous):
        raise ValueError("simulator book does not cover the prior scheduled session")
    marks = book["ending_marks"]
    if any(prices(symbol, previous) != mark for symbol, mark in marks.items()):
        raise ValueError("prior simulated mark was revised or its price basis is unverified")
    return {"market": market, "opening_session": previous, "mark_session": session,
            "source": "accepted shadow simulator book", "cash": book["ending_cash"], "shares": book["ending_shares"],
            "opening_prices": marks, "close_prices": {}, "cost_basis": book["ending_cost_basis"],
            "episodes": book["ending_episodes"], "sectors": book["ending_sectors"]}


def _close_at(work, market, symbol, session):
    from scripts.aegis_shadow.effective_risk import _bars

    bars = _bars(work, market, symbol)
    if bars is None or session not in bars.index:
        raise ValueError(f"missing simulator mark for {symbol} on {session}")
    price = float(bars.loc[session, "close"])
    if not isfinite(price) or price <= 0:
        raise ValueError(f"invalid simulator mark for {symbol} on {session}")
    return price


def rollover_diff(opening, portfolio, threshold_bps):
    if not isfinite(threshold_bps) or not 0 <= threshold_bps <= 10000:
        raise ValueError("invalid configured rebalance threshold")
    positions = portfolio["snapshot"]["positions"]
    targets = {row["ticker"]: row["weight"] for row in positions}
    if len(targets) != len(positions) or any(not isfinite(weight) or weight < 0 for weight in targets.values()):
        raise ValueError("rollover rejects duplicate targets or unsupported short exposure")
    shares, marks = opening["shares"], opening["close_prices"]
    equity = opening["cash"] + sum(quantity * opening["opening_prices"][symbol] for symbol, quantity in shares.items())
    if equity <= 0:
        raise ValueError("rollover requires positive opening equity")
    instructions = []
    for symbol in sorted(set(shares) | set(targets)):
        current = shares.get(symbol, 0) * marks[symbol] / equity
        desired = targets.get(symbol, 0)
        if current and not desired:
            action = "CLOSE"
        elif not current and desired:
            action = "OPEN"
        elif abs(desired - current) <= threshold_bps / 10000:
            action = "HOLD"
        else:
            action = "INCREASE" if desired > current else "DECREASE"
        instructions.append({"ticker": symbol, "action": action, "new_weight": desired,
                             "reason": "Portfolio target reconciled against accepted simulated holdings"})
    return {"market": portfolio["market"], "asof": portfolio["asof"], "instructions": instructions}


def emit(context):
    work, market, asof, session = (context[key] for key in ("work", "market", "asof", "session"))
    source = contained(context["storage"], Path("inputs") / market / "simulator_opening.json")
    report = {"market": market, "session": session, "status": "RESEARCH_INSUFFICIENT_EVIDENCE",
              "reason": "reviewed simulation opening evidence is unavailable"}
    book_path = contained(work, BOOK)
    accepted_checksum = context.get("simulator_book_sha256")
    if source.is_file() or accepted_checksum:
        import yaml

        try:
            reports = "reports" if market == "india" else "usa/reports"
            snapshot = contained(work, Path(reports) / "portfolio_v3.json")
            diff = contained(work, Path(reports) / "portfolio_diff.json")
            costs, risk = (contained(work, Path("configs") / name) for name in ("execution_config.yaml", "risk_budget.yaml"))
            cfg = [yaml.safe_load(path.read_text(encoding="utf-8"))["market_defaults"][market] for path in (costs, risk)]
            lifecycle = _json(contained(work, Path(f"reports/context/canonical_lifecycle_{market}.json")))
            rows = [row for row in lifecycle["current"] if row.get("engine") == "R2" and row.get("market_data_asof") == session]
            episodes = {row["ticker"]: row["position_id"] for row in rows}
            if len(rows) != len(episodes):
                raise ValueError("ambiguous episode mapping for portfolio order generation")
            previous = max(day.isoformat() for day in context["calendar"].closes if day.isoformat() < session)
            portfolio_doc, diff_doc = _json(snapshot), _json(diff)
            book = None
            if accepted_checksum:
                if digest(book_path) != accepted_checksum:
                    raise ValueError("copied simulator book differs from accepted state")
                book = _json(book_path)
            if book and book["session"] == session:
                report = dict(book["report"], replayed_accepted_session=True)
            else:
                opening = (_json(source) if book is None else roll_opening(
                    book, market, previous, session, lambda symbol, day: _close_at(work, market, symbol, day)))
                if book:
                    for ticker in set(opening["shares"]) | {row["ticker"] for row in portfolio_doc["snapshot"]["positions"]}:
                        opening["close_prices"][ticker] = _close_at(work, market, ticker, session)
                    config = contained(work, Path("configs/portfolio_config.yaml"))
                    threshold = yaml.safe_load(config.read_text(encoding="utf-8"))["market_defaults"][market]["rebalance_threshold_bps"]
                    diff_doc = rollover_diff(opening, portfolio_doc, threshold)
                source_id = _identity(sorted(portfolio_doc["snapshot"]["positions"], key=lambda row: row["ticker"]),
                                      sorted(diff_doc["instructions"], key=lambda row: row["ticker"]))
                report = simulate(opening, portfolio_doc, diff_doc, episodes, market, asof, session,
                                  previous, *cfg, _identity(digest(costs), digest(risk)), source_id)
                prior_ids = set(book["accepted_transaction_ids"]) if book else set()
                today = set(report["fill_ids"])
                if prior_ids & today:
                    raise ValueError("duplicate transaction in simulated account history")
                updated = {key: value for key, value in report.items() if key.startswith("ending_")}
                updated.update(schema="aegis.shadow.simulator_book.v1", market=market, session=session,
                               report=report, policy_sha256=report["policy_sha256"],
                               accepted_transaction_ids=sorted(prior_ids | today),
                               cumulative_realized_pnl=(book.get("cumulative_realized_pnl", 0) if book else 0) + report["realized_pnl"],
                               cumulative_fees=(book.get("cumulative_fees", 0) if book else 0) + sum(fill["commission_amount"] for fill in report["fills"]))
                _atomic(work, BOOK.name, json.dumps(updated, sort_keys=True, indent=2, allow_nan=False).encode())
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            report["reason"] = str(error)
    folder = contained(work, Path("reports/research") / market)
    folder.mkdir(parents=True, exist_ok=True)
    _atomic(folder, "shadow_simulated_orders.json", json.dumps(report, indent=2, allow_nan=False).encode())
    if report["status"] == "SIMULATION_RECONCILED":
        context["simulator_ready"] = digest(book_path)
    return "RESEARCH_INSUFFICIENT_EVIDENCE" if report["status"] == "RESEARCH_INSUFFICIENT_EVIDENCE" else None
