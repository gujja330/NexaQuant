"""AEGIS · exit advisor · four advisory exit policies, both markets.

CEO 2026-11-26.

WHY THIS EXISTS
---------------
AEGIS had no profit-taking exit. A position closed only when its stop was
hit, and the stop is a trailing level a fixed distance under the price.
Measured on the 2026-11-26 workbooks:

    India  24 of 48 held positions >= +10%, median 31 days held
    USA    SAIC +17.5% after 104 days with a stop BELOW entry
    India  KOTAKBANK +28.2% after 114 days with a stop BELOW entry

Each recommendation carries suggested_holding_period_days - 60 for USA,
90 for India - and nothing overrode it once the move was made. Two engines
that could have acted did not: apply_dynamic_exits --enforce produced 154
decisions and enforced 0, and capital_rotation reported n_positions=0.

WHAT IT DOES
------------
For every CURRENT row it evaluates, in order of precedence:

    1  SIGNAL EXIT   today's R2 view of a HELD name is REDUCE / EXIT / SELL
    2  TAKE PROFIT   the price has reached the stored target
    3  LOCK          a profit tier is crossed and the stop sits below it
    4  ROTATE        held long, going nowhere, and a clearly better
                     unheld BUY exists today

and records the first that applies.

ADVISORY ONLY - BY DESIGN
-------------------------
Nothing here sells, moves a stop, or writes the registry. It annotates the
row (exit_advice, exit_advice_detail, suggested_stop) and the Reason text,
and writes an audit file. Enforcement is a strategy change and is
deliberately not implemented: it needs the CEO's explicit approval per
market, after the replay in scripts/exit_policy_replay.py has been read.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ADVICE_SIGNAL_EXIT = "SIGNAL EXIT"
ADVICE_TAKE_PROFIT = "TAKE PROFIT"
ADVICE_LOCK = "LOCK PROFIT"
ADVICE_ROTATE = "ROTATE"
ADVICE_HOLD = "HOLD"
ADVICE_DYN_STOP = "DYNAMIC STOP"
ADVICE_DYN_TP = "DYNAMIC TAKE PROFIT"
ADVICE_TIME = "TIME EXIT"

DEFAULTS = {
    "enabled": {"india": True, "usa": True},
    # [trigger P&L %, floor the stop should hold, as % over entry]
    "profit_lock_tiers": [[10.0, 0.0], [20.0, 10.0], [30.0, 20.0]],
    "take_profit_fraction": 0.5,
    "rotation_min_days": 30,
    "rotation_stall_band_pct": [-3.0, 5.0],
    "rotation_score_margin": 10.0,
    "signal_exit_if_holding": ["REDUCE", "EXIT"],
    "signal_exit_actions": ["SELL", "STRONG SELL", "STRONG_SELL"],
    # A target written at entry is stale within weeks - on 2026-11-26 it
    # flagged 27 of India's 48 positions, PNB's 117.92 against 148.61.
    "static_target_take_profit": False,
    # Volatility-scaled triple barrier per market, from
    # scripts/exit_policy_replay.py. Only a market whose nested
    # cross-validation was SUPPORTED is switched on.
    "dynamic": {},
}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _norm(t) -> str:
    return str(t or "").upper().strip().removesuffix(".NS").removesuffix(".BO")


def load_config(root: Path) -> dict:
    cfg = dict(DEFAULTS)
    p = Path(root) / "configs" / "opportunity_registry.yaml"
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg.update(((d.get("risk_engine") or {}).get("exit_advisor") or {}))
    except Exception:
        pass
    return cfg


def calibrate(root: Path, market: str, cfg: dict, asof: str) -> dict:
    """SELF-CALIBRATING barriers. CEO 2026-11-26: "everything should be dynamic".

    With `calibration: auto`, the dynamic barrier parameters are read from
    the latest exit-policy replay instead of numbers copied into config:

      replay fresh and TB held-out verdict SUPPORTED -> use its policy
      replay fresh and NOT SUPPORTED                 -> barriers OFF
      replay missing or older than max_age_days      -> config values

    Enforcement is never switched here - this only moves advisory levels.
    """
    from datetime import date
    m = market.lower()
    dcfg = dict((cfg.get("dynamic") or {}).get(m) or {})
    if dcfg.get("calibration") != "auto":
        dcfg["params_source"] = "config"
        return dcfg
    p = Path(root) / "reports" / "research" / ("exit_policy_replay_%s.json" % m)
    try:
        rep = json.loads(p.read_text(encoding="utf-8"))
        age = (date.fromisoformat(str(asof)[:10])
               - date.fromisoformat(str(rep.get("asof"))[:10])).days
    except Exception:
        dcfg["params_source"] = "config (no replay found)"
        return dcfg
    if age > int(dcfg.get("max_age_days", 35)):
        dcfg["params_source"] = "config (replay %d days old)" % age
        return dcfg
    pol = rep.get("recommended_policy")
    if not pol:
        dcfg["enabled"] = False
        dcfg["params_source"] = "replay %s: %s - barriers off" % (
            rep.get("asof"), rep.get("tb_verdict") or "no supported policy")
        return dcfg
    dcfg.update({"enabled": True, "h": pol["h"], "k_sl": pol["k_sl"],
                 "k_tp": pol.get("k_tp") or 1.0,
                 "params_source": "replay %s: %s (%s)" % (
                     rep.get("asof"), pol.get("label"), pol.get("evidence"))})
    return dcfg


def load_todays_views(root: Path, market: str) -> dict:
    """{ticker: {action, if_holding, entry, score}} from today's SSOT."""
    rel = ("usa/reports/recommendations.json" if market.lower() == "usa"
           else "reports/recommendations.json")
    try:
        d = json.loads((Path(root) / rel).read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for r in d.get("recommendations") or []:
        ia = r.get("investor_action") or {}
        out[_norm(r.get("ticker"))] = {
            "action": str(r.get("action") or "").upper(),
            "if_holding": str(ia.get("if_holding") or "").upper(),
            "entry": str(ia.get("entry") or "").upper(),
            "score": _num(r.get("composite_decision_score")),
        }
    return out


def advise(row: dict, views: dict, held: set, cfg: dict) -> dict:
    """The single advisory for one CURRENT row. Pure: no I/O."""
    entry, cur = _num(row.get("entry_price")), _num(row.get("current_price"))
    stop, target = _num(row.get("stop")), _num(row.get("target"))
    pnl, days = _num(row.get("pnl_pct")), _num(row.get("holding_days"))
    tk = _norm(row.get("ticker"))
    view = views.get(tk) or {}

    # 1 · the engine itself has turned on the name
    if (view.get("if_holding") in set(cfg["signal_exit_if_holding"])
            or view.get("action") in set(cfg["signal_exit_actions"])):
        return {"exit_advice": ADVICE_SIGNAL_EXIT,
                "exit_advice_detail": "today's R2 view: %s / if holding %s"
                % (view.get("action") or "?", view.get("if_holding") or "?"),
                "suggested_stop": None}

    # 2 · dynamic triple barrier (USA, replay-validated) - see _dynamic()
    dyn = row.get("_dyn")
    if dyn:
        return dyn

    # 2b · the stored target has been reached (off by default: stale)
    if cfg.get("static_target_take_profit") and cur and target and target > 0 and entry and target > entry and cur >= target:
        frac = float(cfg["take_profit_fraction"])
        size = "all" if frac >= 1 else "%d%%" % round(frac * 100)
        return {"exit_advice": ADVICE_TAKE_PROFIT,
                "exit_advice_detail": "target %.2f reached at %.2f · book %s"
                % (target, cur, size),
                "suggested_stop": None}

    # 3 · a profit tier is crossed and the stop does not protect it
    if entry and pnl is not None:
        for trigger, lock in sorted(cfg["profit_lock_tiers"], reverse=True):
            if pnl >= trigger:
                floor = round(entry * (1 + lock / 100.0), 4)
                if stop is None or stop < floor:
                    return {"exit_advice": ADVICE_LOCK,
                            "exit_advice_detail": "up %.1f%% · raise stop to %.2f "
                            "(locks %+.0f%%) · current stop %s"
                            % (pnl, floor, lock,
                               "%.2f" % stop if stop is not None else "none"),
                            "suggested_stop": floor}
                break

    # 4 · held long, stalled, and something clearly better is available
    lo, hi = cfg["rotation_stall_band_pct"]
    if (days is not None and days >= cfg["rotation_min_days"]
            and pnl is not None and lo <= pnl <= hi
            and view.get("if_holding") not in {"ADD"}):
        mine = view.get("score")
        best = None
        for t, v in views.items():
            if t in held or v.get("entry") != "BUY" or v.get("score") is None:
                continue
            if best is None or v["score"] > best[1]:
                best = (t, v["score"])
        if best and (mine is None or best[1] - mine >= cfg["rotation_score_margin"]):
            return {"exit_advice": ADVICE_ROTATE,
                    "exit_advice_detail": "held %dd at %+.1f%% · rotate -> %s "
                    "(score %.1f vs %s)"
                    % (days, pnl, best[0], best[1],
                       "%.1f" % mine if mine is not None else "n/a"),
                    "suggested_stop": None}

    return {"exit_advice": ADVICE_HOLD, "exit_advice_detail": "",
            "suggested_stop": None}


def _dynamic(row: dict, dcfg: dict, root: Path, market: str, asof: str):
    """Triple barrier from THIS stock's volatility at entry. None = no call.

    sigma comes only from bars on or before the entry date (point in time),
    so the barriers are the same ones the replay scored.
    """
    from backend.research.exit_policy_replay import load_bars, pit_sigma_atr

    entry, cur = _num(row.get("entry_price")), _num(row.get("current_price"))
    ed = str(row.get("entry_date") or "")[:10]
    if not (entry and cur and ed):
        return None
    df = load_bars(root, market, row.get("ticker"))
    if df is None:
        return None
    sigma, _atr = pit_sigma_atr(df, ed)
    if sigma is None:
        return None
    import math
    h = int(dcfg.get("h", 10))
    span = sigma * math.sqrt(h)
    sl = entry * math.exp(-float(dcfg.get("k_sl", 1.0)) * span)
    tp = entry * math.exp(float(dcfg.get("k_tp", 1.0)) * span)
    bars_held = int((df.index > ed).sum()) if asof is None else int(
        ((df.index > ed) & (df.index <= str(asof)[:10])).sum())
    pct = lambda x: (x / entry - 1) * 100
    # TREND NOTE · CEO 2026-11-26 "profit rising can be held longer".
    # The replay found that holding strong-trend positions past the
    # barrier beat the fixed exit in only 1 of 4 comparable held-out
    # blocks, so it is NOT the rule. It is information: when a position
    # is in profit with a clean trend (Kaufman efficiency since entry),
    # the flag says so and the decision stays with the operator.
    from backend.research.exit_policy_replay import efficiency_ratio
    _fwd = df[(df.index > ed) & (df.index <= str(asof)[:10])]["close"].astype(float).tolist()
    _er = efficiency_ratio(entry, _fwd) if _fwd else 0.0
    _er_min = float(dcfg.get("trend_note_er_min", 0.5))
    _note = ("" if not (_er >= _er_min and cur > entry) else
             " · STRONG TREND (efficiency %.2f) - holding longer is your call, "
             "trail it at %.2f" % (_er, max(sl, cur - 2 * _atr)))
    if cur <= sl:
        return {"exit_advice": ADVICE_DYN_STOP,
                "exit_advice_detail": "at %+.1f%% · below its volatility stop %.2f "
                "(%+.1f%%, 1.0 sigma x sqrt(%dd))" % (pct(cur), sl, pct(sl), h),
                "suggested_stop": round(sl, 4)}
    if cur >= tp:
        return {"exit_advice": ADVICE_DYN_TP,
                "exit_advice_detail": "at %+.1f%% · reached its volatility target %.2f "
                "(%+.1f%%) · book it%s" % (pct(cur), tp, pct(tp), _note),
                "suggested_stop": None}
    if bars_held >= h:
        return {"exit_advice": ADVICE_TIME,
                "exit_advice_detail": "%d trading days held, horizon %dd · "
                "barriers %+.1f%% / %+.1f%% never hit · free the capital%s"
                % (bars_held, h, pct(sl), pct(tp), _note),
                "suggested_stop": round(sl, 4)}
    return None


def annotate(root: Path, market: str, asof: str, rows: list) -> dict:
    """Annotate CURRENT rows in place and write the audit. Never raises."""
    m = market.lower()
    cfg = load_config(root)
    if not (cfg.get("enabled") or {}).get(m, False):
        return {"market": m, "enabled": False}
    try:
        views = load_todays_views(root, m)
        dcfg = calibrate(root, m, cfg, asof)
        held = {_norm(r.get("ticker")) for r in rows if isinstance(r, dict)}
        counts, flagged = {}, []
        for r in rows:
            if not isinstance(r, dict):
                continue
            r.pop("_dyn", None)
            if dcfg.get("enabled"):
                try:
                    d = _dynamic(r, dcfg, root, m, asof)
                except Exception:
                    d = None
                if d:
                    r["_dyn"] = d
            a = advise(r, views, held, cfg)
            r.pop("_dyn", None)
            r.update(a)
            counts[a["exit_advice"]] = counts.get(a["exit_advice"], 0) + 1
            if a["exit_advice"] != ADVICE_HOLD:
                # Advice FIRST, so a one-line cell still shows it.
                r["reason"] = ("%s · %s | %s"
                               % (a["exit_advice"], a["exit_advice_detail"],
                                  r.get("reason") or "")).rstrip(" |")
                flagged.append({"ticker": r.get("ticker"),
                                "position_id": r.get("position_id"), **a,
                                "pnl_pct": r.get("pnl_pct"),
                                "holding_days": r.get("holding_days")})
        out = {"market": m, "asof": asof, "mode": "ADVISORY",
               "enforced": 0, "n_rows": len(rows), "counts": counts,
               "params_source": dcfg.get("params_source"),
               "dynamic_params": {k: dcfg.get(k) for k in ("enabled", "h", "k_sl", "k_tp")},
               "n_views": len(views), "flagged": flagged,
               "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        p = Path(root) / "reports" / "context" / ("exit_advisory_%s.json" % m)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        return out
    except Exception as e:                      # advisory must never break delivery
        return {"market": m, "error": "%s: %s" % (type(e).__name__, e)}
