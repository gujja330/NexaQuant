"""R3 SUPERVISED DECISION PROGRAMME · Phases 4, 5, 9, 11, 13.

This one module carries the meta-label branch, the severe-loss branch,
calibration, adversarial validation and the incremental-decision-value
gate, because they are one pipeline and splitting them would let a model
be scored one way here and another way there.

    fit -> ticker-disjoint OOS -> calibrate -> adversarial -> DECIDE

THE QUESTION
------------
R3 never generates a BUY. R2 decides what is eligible; R3 says only

    TAKE · AVOID · ABSTAIN

about a candidate R2 has already produced. So the baseline is not "no
position" - it is TAKE EVERYTHING R2 OFFERS, net of cost. A model must
beat that, on names it never trained on, or it is worthless no matter how
well it ranks.

BASELINE HIERARCHY · simplest first, and the simplest wins ties
----------------------------------------------------------------
    0  R2 alone (take all)
    1  a one-variable rule on R2 confidence
    2  logistic regression
    3  bounded LightGBM

A complex model must beat the simple one by more than noise to be
preferred. Equal performance means the simple model wins - this is the
mandate's stop condition 16, enforced in code rather than in prose.

ABSTAIN IS A FIRST-CLASS OUTPUT
--------------------------------
A model that does not know is required to say so. The abstention band is
fixed in advance at the middle two deciles of predicted risk; it is never
tuned after seeing out-of-sample results, because tuning a threshold on
the test set is how a dead model gets resurrected.

RESEARCH ONLY · no production surface · R3 never writes to R2.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.r3_program import core

SCHEMA_VERSION = "aegis.r3.decision_models.v1"
FAMILY = "R3K_META_LABEL_V1"

R2_FEATURES = ["confidence_pct", "vol_20d_pct", "momentum_20d_pct",
               "momentum_60d_pct", "ma200_dist_pct", "ma50_dist_pct", "rsi_14"]
FUND_FEATURES = ["roe_pct", "sales_growth_pct", "profit_growth_pct",
                 "debt_to_equity", "roe_trend_pp", "sales_growth_accel_pp",
                 "h3_last_surprise_pct"]

MIN_EVENTS = 40
MIN_EVENT_TICKERS = 20
MIN_DATE_UNITS = 3               # temporal claims need time points
ABSTAIN_BAND = (0.4, 0.6)        # fixed in advance · never tuned on results

# Horizons are those named in the mandate. Testing several is not fishing
# so long as every one is declared up front and counted in the
# multiple-testing family - which they are, below.
TARGETS = {
    "severe_loss_5d": "fwd_5d_pct in the worst decile of the cohort",
    "profitable_5d": "fwd_5d_pct > 0",
    "severe_loss_10d": "fwd_10d_pct in the worst decile of the cohort",
    "profitable_10d": "fwd_10d_pct > 0",
}
TARGET_HORIZON = {"severe_loss_5d": "fwd_5d_pct", "profitable_5d": "fwd_5d_pct",
                  "severe_loss_10d": "fwd_10d_pct",
                  "profitable_10d": "fwd_10d_pct"}


def _prep(root: Path, market: str, target: str) -> dict:
    from backend.research.r3_program.unsupervised import _attach_fundamentals
    rows = core.load_pop(root, market, fwd_key=TARGET_HORIZON[target],
                         features=R2_FEATURES)
    if len(rows) < 100:
        return {"error": "cohort too small: %d" % len(rows)}
    _attach_fundamentals(root, market, rows)
    sev = core.severe_cut(rows)
    for r in rows:
        r["y"] = (1 if r["fwd"] <= sev else 0) if target.startswith("severe") \
            else (1 if r["fwd"] > 0 else 0)
    return {"rows": rows, "severe_cut_pct": round(sev, 3)}


def _oof(rows: list, feats: list, model: str) -> Optional[list]:
    """Out-of-fold predictions on TICKER-DISJOINT folds."""
    import numpy as np
    idx = [i for i, r in enumerate(rows)
           if any(r.get(f) is not None for f in feats)]
    if len(idx) < 80:
        return None
    X = np.array([[(rows[i].get(f) if rows[i].get(f) is not None
                    else float("nan")) for f in feats] for i in idx], dtype=float)
    y = np.array([rows[i]["y"] for i in idx])
    folds = np.array(core.ticker_folds([rows[i] for i in idx], 5))
    pred = np.full(len(idx), np.nan)
    for k in range(5):
        tr = np.where(folds != k)[0]
        te = np.where(folds == k)[0]
        if len(te) == 0 or len(set(y[tr])) < 2:
            return None
        if model == "logistic":
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
            m = make_pipeline(SimpleImputer(strategy="median"),
                              StandardScaler(),
                              LogisticRegression(max_iter=2000, C=1.0))
            m.fit(X[tr], y[tr])
            pred[te] = m.predict_proba(X[te])[:, 1]
        else:
            import lightgbm as lgb
            m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                                   learning_rate=0.05, n_estimators=200,
                                   min_child_samples=20, reg_lambda=1.0,
                                   verbose=-1, random_state=20260908)
            m.fit(X[tr], y[tr])
            pred[te] = m.predict_proba(X[te])[:, 1]
    out = [None] * len(rows)
    for i, p in zip(idx, pred):
        out[i] = float(p)
    return out


def _oof_date_disjoint(rows: list, feats: list, model: str) -> Optional[list]:
    """Leave-one-DATE-out · the only fold structure that tests time.

    Ticker-disjoint folds answer "does this work on a company it has not
    seen". They cannot answer "does this work on a day it has not seen",
    because every fold still contains every date. Where a cohort has real
    date spread, holding out whole dates is the test that matters, and it
    is the one that killed Wave 1D.
    """
    import numpy as np
    idx = [i for i, r in enumerate(rows)
           if any(r.get(f) is not None for f in feats)]
    if len(idx) < 80:
        return None
    dates = sorted({rows[i]["date"] for i in idx})
    big = [d for d in dates
           if sum(1 for i in idx if rows[i]["date"] == d) >= 15]
    if len(big) < 5:
        return None
    X = np.array([[(rows[i].get(f) if rows[i].get(f) is not None
                    else float("nan")) for f in feats] for i in idx], dtype=float)
    y = np.array([rows[i]["y"] for i in idx])
    dcol = [rows[i]["date"] for i in idx]
    pred = np.full(len(idx), np.nan)
    for d in big:
        te = [j for j, dd in enumerate(dcol) if dd == d]
        tr = [j for j, dd in enumerate(dcol) if dd != d]
        if not te or len(tr) < 60 or len(set(y[tr])) < 2:
            continue
        if model == "logistic":
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
            m = make_pipeline(SimpleImputer(strategy="median"),
                              StandardScaler(),
                              LogisticRegression(max_iter=2000, C=1.0))
        else:
            import lightgbm as lgb
            m = lgb.LGBMClassifier(objective="binary", num_leaves=7, max_depth=3,
                                   learning_rate=0.05, n_estimators=200,
                                   min_child_samples=20, reg_lambda=1.0,
                                   verbose=-1, random_state=20260908)
        m.fit(X[tr], y[tr])
        pred[te] = m.predict_proba(X[te])[:, 1]
    out = [None] * len(rows)
    for i, pv in zip(idx, pred):
        out[i] = None if pv != pv else float(pv)
    return out


def _score(rows: list, pred: list) -> dict:
    keep = [i for i, p in enumerate(pred) if p is not None]
    y = [rows[i]["y"] for i in keep]
    p = [pred[i] for i in keep]
    if len(set(y)) < 2:
        return {"error": "single class"}
    return {"n": len(keep), "event_rate_pct": round(sum(y) / len(y) * 100, 1),
            "auc": core.auc(y, p), "pr_auc": core.pr_auc(y, p),
            "brier": core.brier(y, p),
            "brier_base_rate": round(
                sum((v - sum(y) / len(y)) ** 2 for v in y) / len(y), 4),
            "ece": core.ece(y, p), "calibration": core.calibration_line(y, p)}


def _policy(rows: list, pred: list, target: str) -> dict:
    """Turn a probability into TAKE / AVOID / ABSTAIN and price it."""
    band_lo, band_hi = ABSTAIN_BAND
    have = [(r, p) for r, p in zip(rows, pred) if p is not None]
    if not have:
        return {}
    ps = sorted(p for _, p in have)
    lo = ps[int(band_lo * (len(ps) - 1))]
    hi = ps[int(band_hi * (len(ps) - 1))]
    for r, p in have:
        if target.startswith("severe"):
            r["_act"] = "AVOID" if p > hi else "TAKE" if p < lo else "ABSTAIN"
        else:
            r["_act"] = "TAKE" if p > hi else "AVOID" if p < lo else "ABSTAIN"
    sub = [r for r, _ in have]
    dv = core.decision_value(sub, lambda r: r.get("_act", "ABSTAIN"))
    dv["abstain_band_quantiles"] = list(ABSTAIN_BAND)
    dv["band_fixed_in_advance"] = True

    def stat(sel):
        g = [sub[i] for i in sel if i < len(sub)]
        t = [r["fwd"] for r in g if r.get("_act") == "TAKE"]
        a = [r["fwd"] for r in g]
        if len(t) < 10 or not a:
            return None
        return (sum(t) / len(t)) - (sum(a) / len(a))
    dv["delta_mean_ci95_ticker_bootstrap"] = core.ticker_bootstrap_ci(sub, stat)
    return dv


def _adversarial(rows: list, feats: list, model: str, target: str) -> dict:
    """Phase 11 · does the result survive reasonable perturbation."""
    base = _oof(rows, feats, model)
    if base is None:
        return {}
    b = _score(rows, base)
    if b.get("auc") is None:
        return {}
    tests = {}

    def run(sub, label):
        if len(sub) < 100 or len({r["ticker"] for r in sub}) < 20:
            tests[label] = {"skipped": "n=%d" % len(sub)}
            return
        p = _oof(sub, feats, model)
        if p is None:
            tests[label] = {"skipped": "not computable"}
            return
        s = _score(sub, p)
        tests[label] = {"auc": s.get("auc"),
                        "delta_vs_full": (round(s["auc"] - b["auc"], 4)
                                          if s.get("auc") is not None else None),
                        "n": s.get("n")}

    # strongest single name / date / sector removed
    by_t = {}
    for r in rows:
        by_t.setdefault(r["ticker"], []).append(r)
    top_t = max(by_t, key=lambda t: len(by_t[t]))
    run([r for r in rows if r["ticker"] != top_t], "drop_largest_ticker")
    by_d = {}
    for r in rows:
        by_d.setdefault(r["date"], []).append(r)
    top_d = max(by_d, key=lambda d: len(by_d[d]))
    run([r for r in rows if r["date"] != top_d], "drop_largest_date")
    secs = {r.get("sector") for r in rows if r.get("sector")}
    if secs:
        top_s = max(secs, key=lambda s: sum(1 for r in rows if r.get("sector") == s))
        run([r for r in rows if r.get("sector") != top_s], "drop_largest_sector")
    # extreme outcomes removed
    fs = sorted(r["fwd"] for r in rows)
    lo, hi = fs[int(0.02 * len(fs))], fs[int(0.98 * len(fs))]
    run([r for r in rows if lo <= r["fwd"] <= hi], "drop_extreme_outcomes")
    # feature ablation · R2 features only
    p = _oof(rows, R2_FEATURES, model)
    if p is not None:
        s = _score(rows, p)
        tests["ablate_to_r2_features"] = {
            "auc": s.get("auc"),
            "delta_vs_full": (round(s["auc"] - b["auc"], 4)
                              if s.get("auc") is not None else None)}
    # model simplification
    if model != "logistic":
        p = _oof(rows, feats, "logistic")
        if p is not None:
            s = _score(rows, p)
            tests["simplify_to_logistic"] = {
                "auc": s.get("auc"),
                "delta_vs_full": (round(s["auc"] - b["auc"], 4)
                                  if s.get("auc") is not None else None)}
    deltas = [v.get("delta_vs_full") for v in tests.values()
              if isinstance(v, dict) and v.get("delta_vs_full") is not None]
    worst = min(deltas) if deltas else None
    return {"baseline_auc": b["auc"], "perturbations": tests,
            "worst_delta_auc": worst,
            "fragile": bool(worst is not None and worst < -0.05),
            "fragility_rule": "a drop of more than 0.05 AUC under any single "
                              "reasonable perturbation marks the result FRAGILE"}


def run_target(root: Path, market: str, target: str) -> dict:
    prep = _prep(root, market, target)
    if prep.get("error"):
        return {"market": market, "target": target, "error": prep["error"]}
    rows = prep["rows"]
    sub = core.substrate_assessment(rows)
    n_ev = sum(r["y"] for r in rows)
    ev_tk = len({r["ticker"] for r in rows if r["y"] == 1})

    rep = {
        "schema_version": SCHEMA_VERSION,
        "experiment_family_id": FAMILY,
        "experiment_id": "%s_%s_%s" % (FAMILY, market.lower(), target),
        "status": "RESEARCH ONLY · R3 never writes to R2",
        "market": market.lower(), "target": target,
        "target_definition": TARGETS[target],
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of_range": [min(r["date"] for r in rows), max(r["date"] for r in rows)],
        "feature_definition": {"r2_block": R2_FEATURES, "fundamental_block": FUND_FEATURES},
        "pit_methodology": "features as-of prediction date · fundamentals at 45d assumed lag",
        "publication_lag_assumption_days": 45,
        "substrate": sub,
        "date_concentration": core.date_concentration(rows),
        "sector_validity": core.sector_validity(rows),
        "severe_cut_pct": prep["severe_cut_pct"],
        "n_events": n_ev, "n_event_tickers": ev_tk,
        "train_test_methodology": "5-fold ticker-disjoint out-of-fold",
        "embargo": "not applicable · folds are ticker-disjoint, not temporal",
        "oos_status": "TICKER_DISJOINT_ONLY",
        "baseline": "R2 alone · take every candidate, net of %.2f%% cost"
                    % core.DEFAULT_COST_PCT,
    }

    # ── gates BEFORE any model is fitted ────────────────────────────────
    if n_ev < MIN_EVENTS or ev_tk < MIN_EVENT_TICKERS:
        rep["disposition"] = "INSUFFICIENT_SUBSTRATE"
        rep["reason"] = ("%d events across %d names · below the %d/%d floor. "
                         "A model fitted here would produce a number, not "
                         "evidence." % (n_ev, ev_tk, MIN_EVENTS, MIN_EVENT_TICKERS))
        return rep
    dc = rep["date_concentration"]
    if dc["single_episode"]:
        rep["disposition"] = "INSUFFICIENT_SUBSTRATE"
        rep["reason"] = (
            "SINGLE EPISODE · %.1f%% of rows fall on %s. Those forward "
            "windows overlap almost entirely, so this cohort contains one "
            "realisation of the market wearing %d names. A ticker-disjoint "
            "model can score well here while having seen exactly one market "
            "move; no out-of-sample decision claim is possible. Names are "
            "not dates."
            % (dc["top_2_dates_share_pct"],
               " and ".join(list(dc["rows_by_date"])[:2]), sub["n_tickers"]))
        rep["note_on_engineering"] = (
            "the pipeline itself is built and exercised · only the evidence "
            "is blocked, and it unblocks as the prequential ledger accrues "
            "dates")
        return rep
    if sub["effective_date_units"] < MIN_DATE_UNITS:
        rep["temporal_warning"] = (
            "%d independent date unit(s) · no temporal or drift claim is "
            "possible from this cohort. Ticker-disjoint folds test whether "
            "the model generalises across NAMES; they cannot test whether it "
            "generalises across TIME, which is what production requires."
            % sub["effective_date_units"])

    # ── the baseline hierarchy · simplest first ─────────────────────────
    ladder = {}
    conf = [r.get("confidence_pct") for r in rows]
    have_conf = [i for i, c in enumerate(conf) if c is not None]
    if len(have_conf) >= 100:
        cs = sorted(conf[i] for i in have_conf)
        med = cs[len(cs) // 2]
        p1 = [None] * len(rows)
        for i in have_conf:
            v = (conf[i] - min(cs)) / max(1e-9, (max(cs) - min(cs)))
            p1[i] = 1.0 - v if target == "severe_loss_10d" else v
        ladder["1_confidence_rule"] = {
            "scores": _score(rows, p1),
            "note": "R2 confidence alone, rescaled · median %.2f" % med,
            # Rung 1 is priced as a policy exactly like every other rung.
            # If R2's own confidence is the best rung, that is the finding -
            # and it still has to prove it changes a decision.
            "decision_value": _policy(rows, p1, target)}
    for name, model, feats in (("2_logistic_r2", "logistic", R2_FEATURES),
                               ("3_lgbm_r2", "lgbm", R2_FEATURES),
                               ("4_lgbm_r2_plus_fundamentals", "lgbm",
                                R2_FEATURES + FUND_FEATURES)):
        p = _oof(rows, feats, model)
        if p is None:
            ladder[name] = {"error": "not computable"}
            continue
        ladder[name] = {"scores": _score(rows, p), "n_features": len(feats)}
        ladder[name]["decision_value"] = _policy(rows, p, target)
    rep["baseline_ladder"] = ladder

    # ── pick the SIMPLEST model that is not beaten ──────────────────────
    scored = {k: v for k, v in ladder.items()
              if isinstance(v.get("scores"), dict) and v["scores"].get("auc")}
    if not scored:
        rep["disposition"] = "INSUFFICIENT_SUBSTRATE"
        rep["reason"] = "no model in the ladder was computable"
        return rep
    order = sorted(scored)
    best_auc = max(scored[k]["scores"]["auc"] for k in order)
    chosen = next(k for k in order
                  if scored[k]["scores"]["auc"] >= best_auc - 0.02)
    rep["model_selection"] = {
        "auc_by_rung": {k: scored[k]["scores"]["auc"] for k in order},
        "best_auc": best_auc, "chosen": chosen,
        "rule": ("the simplest rung within 0.02 AUC of the best is chosen · "
                 "complexity must EARN its place, and here it did not have to"
                 if chosen != max(order, key=lambda k: scored[k]["scores"]["auc"])
                 else "the best rung is also the one chosen")}

    chosen_feats = (R2_FEATURES + FUND_FEATURES if "fundamentals" in chosen
                    else R2_FEATURES)
    chosen_model = "logistic" if "logistic" in chosen else "lgbm"
    pdd = _oof_date_disjoint(rows, chosen_feats, chosen_model)
    if pdd is not None:
        sdd = _score(rows, pdd)
        tick_auc = scored[chosen]["scores"]["auc"]
        rep["date_disjoint_validation"] = {
            "auc_ticker_disjoint": tick_auc,
            "auc_date_disjoint": sdd.get("auc"),
            "delta": (round(sdd["auc"] - tick_auc, 4)
                      if sdd.get("auc") is not None else None),
            "n_scored": sdd.get("n"),
            "note": ("whole dates held out · this asks whether the model "
                     "works on a DAY it has not seen, which ticker-disjoint "
                     "folds cannot test")}
        rep["date_disjoint_validation"]["survives"] = bool(
            sdd.get("auc") is not None and sdd["auc"] >= 0.55)
    else:
        rep["date_disjoint_validation"] = {
            "computable": False,
            "reason": "fewer than 5 dates carry 15+ rows · cannot hold out "
                      "whole dates without destroying the training set"}

    rep["adversarial"] = _adversarial(rows, chosen_feats, chosen_model, target)

    # ── PHASE 13 · the final gate ───────────────────────────────────────
    dv = (ladder.get(chosen) or {}).get("decision_value") or {}
    ci = dv.get("delta_mean_ci95_ticker_bootstrap") or {}
    rep["incremental_decision_value"] = dv
    auc_ok = scored[chosen]["scores"]["auc"] >= 0.55
    fragile = (rep.get("adversarial") or {}).get("fragile")
    if not dv:
        rep["disposition"] = "INSUFFICIENT_SUBSTRATE"
        rep["reason"] = "decision value not computable"
    elif not auc_ok:
        rep["disposition"] = "REJECTED"
        rep["reason"] = ("chosen model AUC %.4f does not separate outcomes "
                         "out-of-sample" % scored[chosen]["scores"]["auc"])
    elif not ci or not ci.get("excludes_zero"):
        rep["disposition"] = "REJECTED"
        rep["reason"] = (
            "the policy changes the mean outcome by %s pp, but the "
            "ticker-bootstrap 95%% CI %s spans zero · the decision is not "
            "distinguishable from taking every R2 candidate"
            % (dv.get("delta_mean_pp"),
               [ci.get("lo"), ci.get("hi")] if ci else "n/a"))
    elif fragile:
        rep["disposition"] = "REJECTED"
        rep["reason"] = ("FRAGILE · worst single-perturbation AUC change %s"
                         % rep["adversarial"].get("worst_delta_auc"))
    elif rep["date_disjoint_validation"].get("survives") is False:
        rep["disposition"] = "REJECTED"
        rep["reason"] = (
            "collapses when whole DATES are held out · ticker-disjoint AUC "
            "%s falls to %s on unseen days. The model learned the episodes "
            "in the sample, not a relationship that carries forward."
            % (rep["date_disjoint_validation"].get("auc_ticker_disjoint"),
               rep["date_disjoint_validation"].get("auc_date_disjoint")))
    elif sub["effective_date_units"] < MIN_DATE_UNITS:
        rep["disposition"] = "CONDITIONAL"
        rep["reason"] = (
            "survives ticker-disjoint validation and adds decision value, but "
            "rests on %d independent date unit(s). It generalises across "
            "names; nothing here shows it generalises across time. Cannot be "
            "promoted until the prequential ledger supplies real dates."
            % sub["effective_date_units"])
    else:
        rep["disposition"] = "CONDITIONAL"
        rep["reason"] = ("passes OOS, adversarial and decision-value gates · "
                         "requires explicit authorisation before any overlay")
    return rep


def run(root: Path, market: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_family_id": FAMILY,
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "multiple_testing_family_size": len(TARGETS) * 4,
        "family_note": ("4 declared targets x 4 ladder rungs = 16 trials "
                        "per market · every rung is reported, never only "
                        "the best"),
        "correction_method": ("ticker-bootstrap CI on the decision delta · a "
                              "point estimate is never the conclusion"),
        "by_target": {t: run_target(root, market, t) for t in TARGETS},
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "research" / "r3" / f"decision_models_{rep['market']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = root / "reports" / "research" / "r3" / f"decision_models_{market.lower()}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 supervised decision programme")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = run(root, m)
        emit(root, rep)
        for t, r in rep["by_target"].items():
            if r.get("error"):
                print(f"R3-K:{m}:{t} · {r['error']}")
                continue
            print(f"R3-K:{m}:{t} · {r.get('disposition')}")
            print(f"    {r.get('reason','')[:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
