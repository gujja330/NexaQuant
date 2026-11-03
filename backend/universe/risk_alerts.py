"""Risk alerts for names the shortlist excluded.

CEO 2026-11-03 · WHY THIS IS A SEPARATE MECHANISM AND NOT A SELECTOR PATCH
--------------------------------------------------------------------------
Measuring USA's 248-slot shortlist against the day's real recommendations
turned up a structural bias, not a rounding loss: of the 7 actionable
calls the shortlist dropped, 5 were SELLs. That is not bad luck. The
shortlist ranks on liquidity, momentum, trend, risk and evidence, and a
SELL candidate is by construction a weak name, so a momentum-ranked
shortlist excludes precisely what risk control exists to catch.

Exempting open positions fixed most of it - coverage went 61.1% to 83.3%
- because a name you hold is a name you must keep watching. What it did
NOT fix is the residual: AKAM, DAL and GPC are SELL signals on names the
book does not hold. Nothing is at risk there today, but a SELL signal on
an unheld name is still information, and the instruction was explicit
that it must not be silently dropped.

THE CONSTRAINT THAT SHAPES THIS MODULE
--------------------------------------
"It must not silently bypass the main selector."

So this module cannot add anything to the selection. It takes the
selected set as an input it is forbidden to modify, and emits a separate,
labelled artifact. `alerts_do_not_alter_selection` is asserted by a test
that compares the selected set byte for byte with and without the alert
pass, because an advisory channel that quietly grows the universe is the
alias-drift bug class in a new costume - a consumer holding its own
private copy of what "selected" means.

An alert is advisory. It carries `bypasses_selector: False` and
`action_taken: "NONE"` on every record, so no downstream reader can treat
it as an admission, and the delivery layer can surface it under its own
heading without it ever entering the R2 lifecycle.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pandas as pd

from backend.universe.top_selection import bare_ticker, open_position_tickers

SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.universe.risk_alerts.v1"

#: Signals that mean "reduce or exit". Normalised with spaces AND
#: underscores because the two classifiers disagree on the spelling -
#: India ships "STRONG SELL", the percentile classifier emits
#: "STRONG_SELL", and a consumer matching only one of them silently sees
#: half the SELLs. That is the alias-drift class, so both are listed.
SELL_FAMILY = {"SELL", "STRONG SELL", "STRONG_SELL", "REDUCE", "EXIT"}

#: Signals that mean "open or add". Recorded but NOT alerted on: a missed
#: BUY on an unheld, unselected name is a foregone opportunity, not a
#: risk, and conflating the two would turn this channel into a second
#: recommendation feed that bypasses the selector in substance.
BUY_FAMILY = {"BUY", "STRONG BUY", "STRONG_BUY", "ACCUMULATE"}

ALERT_EXCLUDED_SELL = "EXCLUDED_SELL_SIGNAL"
ALERT_EXCLUDED_HELD = "EXCLUDED_WHILE_HELD"

SEV_CRITICAL = "CRITICAL"
SEV_INFO = "INFO"


def _norm(sig) -> str:
    return str(sig or "").upper().strip()


def is_sell(sig) -> bool:
    return _norm(sig) in SELL_FAMILY


def is_buy(sig) -> bool:
    return _norm(sig) in BUY_FAMILY


def alerts_path(root: Path, market: str, asof: str) -> Path:
    return (Path(root) / "reports" / "universe"
            / ("risk_alerts_%s_%s.json" % (str(market).lower(),
                                           str(asof)[:10])))


def build(root: Path, market: str, *, recommendations: Sequence[dict],
          selected_tickers: Iterable[str], asof: str,
          eligible_tickers: Optional[Iterable[str]] = None,
          held: Optional[set] = None) -> dict:
    """Alerts for actionable signals on names the shortlist left out.

    `selected_tickers` is read, never written. The returned dict carries
    no selection of its own and nothing downstream may derive one from it.
    """
    mkt = str(market).lower()
    sel = {bare_ticker(t) for t in (selected_tickers or [])}
    elig = ({bare_ticker(t) for t in eligible_tickers}
            if eligible_tickers is not None else None)
    holdings = (open_position_tickers(Path(root), mkt) if held is None
                else {bare_ticker(t) for t in held})

    alerts, counted = [], {"sell": 0, "buy": 0, "hold": 0}
    for r in recommendations or []:
        tk = bare_ticker(r.get("ticker"))
        if not tk:
            continue
        sig = _norm(r.get("action") or r.get("recommendation"))
        if is_sell(sig):
            counted["sell"] += 1
        elif is_buy(sig):
            counted["buy"] += 1
        else:
            counted["hold"] += 1
        if tk in sel:
            continue                      # the selector is watching it
        if not is_sell(sig):
            continue                      # advisory covers risk, not alpha
        is_held = tk in holdings
        alerts.append({
            "ticker": tk,
            "market": mkt,
            "asof": str(asof)[:10],
            "signal": sig,
            "alert": ALERT_EXCLUDED_HELD if is_held else ALERT_EXCLUDED_SELL,
            # A SELL on a name the book holds that the shortlist still
            # excluded would mean the open-position exemption failed, so
            # it is the severe case even though it should never occur.
            "severity": SEV_CRITICAL if is_held else SEV_INFO,
            "held": is_held,
            "eligible": (None if elig is None else tk in elig),
            "confidence": r.get("calibrated_confidence"),
            "ensemble_score": r.get("ensemble_score"),
            "rationale": ("a SELL signal on a name the shortlist does not "
                          "cover; advisory only"),
            "bypasses_selector": False,
            "action_taken": "NONE",
        })

    alerts.sort(key=lambda a: (a["severity"] != SEV_CRITICAL, a["ticker"]))
    return {
        "engine": ENGINE_ID,
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": mkt,
        "asof": str(asof)[:10],
        "n_recommendations": len(recommendations or []),
        "signal_counts": counted,
        "n_selected": len(sel),
        "n_held": len(holdings),
        "n_alerts": len(alerts),
        "n_critical": sum(1 for a in alerts if a["severity"] == SEV_CRITICAL),
        "alerts": alerts,
        "contract": {
            "advisory_only": True,
            "alters_selection": False,
            "enters_r2_lifecycle": False,
            "note": ("This artifact is advisory. It adds nothing to the "
                     "selected universe and opens no position. A reader "
                     "that admits a name from here has bypassed the "
                     "selector, which is the thing this mechanism exists "
                     "to avoid."),
        },
        "known_residual": {
            "measured_utc": "2026-11-03",
            "tickers": ["AKAM", "DAL", "GPC"],
            "note": ("the three SELL signals USA's 248-slot shortlist "
                     "misses on names the book does not hold · recorded "
                     "so they are not silently dropped"),
        },
    }


def write(root: Path, market: str, report: dict) -> Path:
    p = alerts_path(root, market, report.get("asof") or "")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return p


def coverage(recommendations: Sequence[dict],
             selected_tickers: Iterable[str]) -> dict:
    """How much of the day's actionable output the shortlist covers.

    Reported by signal family, because a single blended coverage number
    hid the fact that the losses were concentrated in the SELLs.
    """
    sel = {bare_ticker(t) for t in (selected_tickers or [])}
    fam = {"BUY": [], "SELL": []}
    for r in recommendations or []:
        tk = bare_ticker(r.get("ticker"))
        sig = _norm(r.get("action") or r.get("recommendation"))
        if is_buy(sig):
            fam["BUY"].append(tk)
        elif is_sell(sig):
            fam["SELL"].append(tk)
    out = {}
    tot = cov = 0
    for k, tks in fam.items():
        c = sum(1 for t in tks if t in sel)
        out[k] = {"n": len(tks), "covered": c,
                  "missed": sorted(t for t in tks if t not in sel),
                  "coverage_pct": (round(100.0 * c / len(tks), 2)
                                   if tks else None)}
        tot += len(tks)
        cov += c
    out["ALL_ACTIONABLE"] = {
        "n": tot, "covered": cov,
        "coverage_pct": round(100.0 * cov / tot, 2) if tot else None}
    return out
