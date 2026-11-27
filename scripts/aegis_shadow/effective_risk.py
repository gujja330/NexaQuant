"""Point-in-time risk binding for the private runner."""
import argparse
import json
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


def _price(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def stop_levels(close, atr, entry, prior, policy):
    """Apply configured ATR parameters and measure lifts against the prior stop."""
    high_vol = 100 * atr / close > policy["high_vol_atr_pct"]
    standard = close - atr * policy["atr_multiplier"]
    candidate = close - atr * policy["high_vol_scale"] if high_vol else standard
    kind = "vol_scaled" if high_vol else "atr"
    eligible = _price(entry) and (close / entry - 1) * 100 >= policy["trailing_lift_min_pct"]
    if eligible and standard > candidate:
        candidate = standard
    proposal = round(candidate, 4)
    if not _price(proposal):
        return None, "unavailable"
    if _price(prior):
        if policy["monotonic"] and proposal < prior:
            return prior, "held"
        if eligible and proposal > prior:
            kind = "trailing"
    return proposal, kind


def _bars(work, market, ticker):
    import pandas as pd
    from backend.research._paths import price_parquet_path

    ticker = ticker.removesuffix(".NS").removesuffix(".BO") if market == "india" else ticker
    path = price_parquet_path(work, market, ticker)
    if path is None:
        return None
    bars = pd.read_parquet(contained(work, path.relative_to(work)))
    index = pd.to_datetime(bars.index).strftime("%Y-%m-%d")
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("duplicate or unordered price sessions")
    return bars.set_axis(index)


def calculate(work, market, asof, session, previous, next_session=None, *, observation_close=None, now=None):
    import yaml
    from backend.risk.dynamic_risk_v2 import _atr
    from backend.research.opportunity_registry import active_opportunities, load_all

    config = contained(work, Path("configs/opportunity_registry.yaml"))
    policy = yaml.safe_load(config.read_text(encoding="utf-8"))["risk_engine"]
    policy = dict(policy, monotonic=policy["monotonic_stops"].get(market) is True)
    path = contained(work, Path(f"reports/context/dynamic_risk_{market}.json"))
    prior_doc = _json(path) if path.is_file() else {}
    if prior_doc.get("schema") != "aegis.shadow.effective_risk.v1" or prior_doc.get("market") != market:
        prior_doc = {}
    prior_session = prior_doc.get("calculation_session")
    prior_rows = {row["opportunity_id"]: row for row in prior_doc.get("updates", [])}
    intervals_path = contained(work, Path(".shadow-risk-intervals.json"))
    intervals = _json(intervals_path) if intervals_path.is_file() else None
    clock = now or datetime.now(timezone.utc)
    zone = ZoneInfo("Asia/Kolkata" if market == "india" else "America/New_York")
    prior_stamp = prior_doc.get("authorized_utc")
    authorized_at = datetime.fromisoformat(prior_stamp) if prior_stamp else None
    authorized_before_close = (authorized_at is not None and authorized_at.utcoffset() is not None and
                               (authorized_at < observation_close if observation_close else
                                authorized_at.astimezone(zone).date().isoformat() < session))
    updates, unavailable = [], {}
    for episode in active_opportunities(load_all(work)):
        if episode.market != market or episode.runner != "R2":
            continue
        pid = episode.opportunity_id
        try:
            bars = _bars(work, market, episode.ticker)
            if bars is None or session not in bars.index:
                raise ValueError("completed-session bar missing")
            day = bars.loc[:session].tail(15)
            if len(day) != 15 or not all(_price(float(value)) for column in ("high", "low", "close") for value in day[column]):
                raise ValueError("ATR requires 15 valid comparable daily bars")
            close = float(day["close"].iloc[-1])
            atr = _atr(day)
            if atr is None or not isfinite(atr) or atr < 0:
                raise ValueError("invalid ATR")
            entry = float(bars.loc[episode.created_date, "close"]) if episode.created_date in bars.index and episode.created_date <= session else None
            prior = prior_rows.get(pid, {})
            prior_level = None
            anchor_session, anchor_close = None, None
            authority_revision = None
            if prior and prior_session not in {session, previous} and policy["monotonic"]:
                from scripts.aegis_shadow.recover_daily import _complete_bars
                from scripts.aegis_shadow.risk_intervals import resolve

                authority = resolve(intervals, market, pid, episode.ticker, session) if intervals else None
                if not authority:
                    raise ValueError("current stop continuity requires an authorized gap carry-forward")
                verified = {"bar_source": authority.get("bar_source"), "bars": {}}
                _complete_bars(work, market, verified, episode.ticker, [session])
                if verified["bars"].get(session) != {"close": close, "price_basis": authority["price_basis"]}:
                    raise ValueError("authorized gap stop has no verified current price basis")
                prior_level, anchor_session, anchor_close = authority["stop"], session, close
                authority_revision = authority["revision_id"]
            if prior and prior_session in {session, previous}:
                if prior_session == session:
                    prior_level = prior.get("previous_authorized_stop")
                    anchor_session, anchor_close = prior.get("effective_anchor_session"), prior.get("effective_anchor_close")
                    authority_revision = prior.get("authority_revision")
                elif prior_doc.get("proposal_effective_from_session") == session and authorized_before_close:
                    prior_level = prior.get("proposed_stop")
                    anchor_session, anchor_close = prior_session, prior["current_price"]
                elif policy["monotonic"]:
                    raise ValueError("previous stop proposal lacks timely authorization for this session")
                if _price(prior_level) and (anchor_session not in bars.index
                        or float(bars.loc[anchor_session, "close"]) != anchor_close or prior["ticker"] != episode.ticker):
                    # A revised observation can invalidate the prior price basis.
                    raise ValueError("previous authorized stop price basis requires reconciliation")
            proposed, kind = stop_levels(close, atr, entry, prior_level, policy)
            if proposed is None:
                raise ValueError("configured proposal is not a positive stop")
            updates.append({"opportunity_id": pid, "ticker": episode.ticker, "entry_price": entry,
                            "current_price": close, "atr14": atr, "previous_authorized_stop": prior_level,
                            "new_stop": prior_level if _price(prior_level) else proposed,
                            "stop_type": "effective_prior" if _price(prior_level) else "prospective",
                            "proposed_stop": proposed, "proposal_type": kind,
                            "effective_for_observation": _price(prior_level),
                            "effective_anchor_session": anchor_session, "effective_anchor_close": anchor_close,
                            "authority_revision": authority_revision,
                            "reason": "Configured ATR proposal applies after the calculation session"})
        except (KeyError, OSError, TypeError, ValueError) as error:
            unavailable[pid] = str(error)
    output = {"schema": "aegis.shadow.effective_risk.v1", "market": market, "asof": asof,
              "calculation_session": session, "proposal_effective_from_session": next_session,
              "authorized_utc": clock.astimezone(timezone.utc).isoformat(),
              "policy_sha256": digest(config), "monotonic": policy["monotonic"],
              "n_trailing_lifted": sum(row["proposal_type"] == "trailing" for row in updates),
              "updates": updates, "unavailable": unavailable}
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic(path.parent, path.name, json.dumps(output, indent=2, allow_nan=False).encode())


def _target_authority(work, market, session, observation_close):
    path = contained(work, Path(".shadow-exit-authority.json"))
    if not path.is_file():
        return {}
    doc = _json(path)
    if doc.get("market") != market or doc.get("schema") != "aegis.shadow.exit_authority.v1":
        raise ValueError("target authority market or schema disagrees")
    eligible = {}
    seen = set()
    for row in doc["targets"]:
        pid = row["episode_id"]
        if pid in seen or not row.get("source") or not row.get("authority_id"):
            raise ValueError("target authority is duplicate or missing source")
        seen.add(pid)
        authorized = datetime.fromisoformat(row["authorized_utc"])
        effective, through = (date.fromisoformat(row[key]).isoformat() for key in ("effective_from", "effective_through"))
        if authorized.utcoffset() is None or effective > through or not _price(row.get("target")):
            raise ValueError("target authority has invalid timing or level")
        if observation_close is not None and effective <= session <= through and authorized < observation_close:
            eligible[pid] = row
    return eligible


def evaluate_exits(work, market, asof, session, observation_close=None):
    from backend.research import opportunity_registry as registry
    from scripts.apply_dynamic_exits import apply_market

    risk = _json(contained(work, Path(f"reports/context/dynamic_risk_{market}.json")))
    if (risk.get("market"), risk.get("asof"), risk.get("calculation_session")) != (market, asof, session):
        raise ValueError("exit evaluator received mismatched risk evidence")
    levels = {row["opportunity_id"]: row for row in risk["updates"]}
    targets = _target_authority(work, market, session, observation_close)
    result = apply_market(work, market, asof, enforce=False)
    positions = registry.load_all(work)
    count = 0
    for decision in result["decisions"]:
        level = levels.get(decision["opportunity_id"])
        if decision.get("runner") != "R2":
            continue
        if level is None or decision.get("price_basis_date") != session or decision.get("current_price") != level["current_price"]:
            decision.update(action="SKIP", reason="Verified completed-session risk or price evidence unavailable")
            continue
        event = None
        if (decision.get("event") == "EXIT_STOP" and level["effective_for_observation"]
                and decision.get("stop_price") == level["new_stop"]):
            event = "EXIT_STOP"
        authority = targets.get(decision["opportunity_id"])
        if authority and authority.get("ticker") == level["ticker"]:
            target = authority["target"]
            entry = level["entry_price"]
            if _price(entry) and target > entry and authority.get("reference_entry_price") == entry:
                decision.update(t1_price=target, t2_price=None, target_authority_id=authority["authority_id"])
                if event is None and level["current_price"] >= target:
                    event = "EXIT_TARGET"
            else:
                decision["target_authority_rejection"] = "Authorized target and comparable entry price disagree"
        if event is None:
            continue
        episode = registry.close(work, decision["opportunity_id"], asof,
                                 f"{event} | SHADOW_UNCONFIRMED | {session}",
                                 registry=positions)
        if episode is None or episode.status != "CLOSED" or episode.closed_date != asof:
            raise ValueError("private registry rejected authorized stop transition")
        decision.update(event=event, action="ENFORCED", trigger_date=session, execution_status="UNCONFIRMED",
                        reason="Dated stop or explicit target authority matched completed-close evidence")
        count += 1
    path = contained(work, Path(f"reports/audit/dynamic_exit_decisions_{market}_{asof}.json"))
    result.update(mode="shadow_point_in_time", n_enforced=count,
                  notes=["Only a prior effective stop or explicitly authorized target can close an episode.",
                         "Holding triggers remain advisory."],
                  n_audit_only=sum(row["action"].startswith("AUDIT_ONLY") for row in result["decisions"]))
    _atomic(path.parent, path.name, json.dumps(result, indent=2, allow_nan=False).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("risk", "exits"))
    parser.add_argument("market", choices=("india", "usa"))
    parser.add_argument("asof")
    parser.add_argument("session")
    parser.add_argument("--previous")
    parser.add_argument("--next-session")
    parser.add_argument("--observation-close", type=datetime.fromisoformat)
    args = parser.parse_args()
    work = Path(__file__).resolve().parents[2]
    if work.name != "work" or "unified" not in work.parts or ".aegis-local" not in work.parts:
        raise ValueError("effective risk requires a private unified workspace")
    if args.mode == "risk":
        calculate(work, args.market, args.asof, args.session, args.previous, args.next_session,
                  observation_close=args.observation_close)
    else:
        evaluate_exits(work, args.market, args.asof, args.session, args.observation_close)


if __name__ == "__main__":
    main()
