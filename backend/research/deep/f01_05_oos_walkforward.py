"""F01-F05 · Ticker-partitioned OOS walk-forward · V2 §D.8 item 1.

Temporal walk-forward is blocked (fundamentals accumulator has 1 day of PIT
history · needs 8+ quarters). Ticker-partition OOS is what's testable now:
deterministic hash-split of the cross-sectional universe into disjoint train
and test ticker sets · fit composite weights on train · evaluate lift on test.

Not a substitute for temporal walk-forward · flagged as such. Provides
directional evidence that the fundamental composite generalises to unseen
tickers within the same market snapshot.

Both markets · dynamic · no hardcoded ticker lists · DSR-deflated.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="F01-05-OOS-TICKER",
    domain_num=1,
    name="F01-F05 · Ticker-partitioned OOS walk-forward",
    description="Cross-sectional ticker-split OOS · fits composite on train tickers · evaluates on test tickers",
    gate_precondition="Fundamentals FS ≥ 50 tickers with (fcf_yield, piotroski_f, interest_coverage, beneish_m)",
    additive_extension_id="F01-05-OOS-TICKER",
)

# Deterministic split · hash of ticker · configurable ratio via arg
def _ticker_partition(tickers: list[str], test_frac: float = 0.30, salt: str = "F01-05-OOS") -> tuple[set, set]:
    train, test = set(), set()
    for t in tickers:
        h = int(hashlib.md5(f"{salt}·{t}".encode()).hexdigest(), 16) / (1 << 128)
        (test if h < test_frac else train).add(t)
    return train, test


def _z(v, series):
    if not series or v is None: return None
    try:
        mu = sum(series) / len(series)
        var = sum((x - mu)**2 for x in series) / max(1, len(series) - 1)
        sd = math.sqrt(var)
        if sd <= 0: return 0.0
        return max(-3.0, min(3.0, (float(v) - mu) / sd))
    except (TypeError, ValueError):
        return None


def _fwd20(root: Path, market: str, ticker: str) -> float | None:
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        if len(df) < 21: return None
        c = df["close"].tail(21).to_numpy()
        if c[0] <= 0: return None
        return (c[-1] / c[0]) - 1.0
    except Exception: return None


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research.walkforward.deflated_sharpe import deflated_sharpe_ratio

    fs_p = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_p.exists():
        return blocked_result(RESEARCH_TICKET, market, "fundamentals_feature_store missing")
    fs = pd.read_parquet(fs_p)
    fs = fs.sort_values(["ticker", "asof"]).drop_duplicates("ticker", keep="last")
    # Core-3 required (all populated to ≥70% cross-market) · beneish optional
    core = ("fcf_yield", "piotroski_f", "interest_coverage")
    optional = ("beneish_m",)
    required = tuple(c for c in core if c in fs.columns)
    if len(required) < 2:
        return blocked_result(RESEARCH_TICKET, market,
                                f"only {required} of core columns present · need ≥2")
    fs = fs.dropna(subset=list(required))
    # V2 stronger-evidence tier (30-49) is acceptable · validation-candidate (50+) preferred
    if len(fs) < 30:
        return blocked_result(RESEARCH_TICKET, market,
                                f"n={len(fs)} < 30 required (V2 stronger-evidence tier)")

    tickers = fs["ticker"].astype(str).tolist()
    train, test = _ticker_partition(tickers, test_frac=0.30)

    # Attach forward 20d return
    fs = fs.copy()
    fs["r20d"] = fs["ticker"].apply(lambda t: _fwd20(root, market, t))
    fs = fs.dropna(subset=["r20d"])
    fs_train = fs[fs["ticker"].isin(train)]
    fs_test = fs[fs["ticker"].isin(test)]

    if len(fs_train) < 30 or len(fs_test) < 15:
        return blocked_result(RESEARCH_TICKET, market,
                                f"train={len(fs_train)} test={len(fs_test)} · need ≥30/15")

    # Fit composite on train · z-scores computed from train pool only (no leakage)
    # Include beneish only if present + populated
    beneish_available = "beneish_m" in fs.columns and fs["beneish_m"].notna().sum() >= 10
    scoring_cols = list(required) + (["beneish_m"] if beneish_available else [])
    train_stats = {c: (fs_train[c].mean(skipna=True), fs_train[c].std(skipna=True))
                    for c in scoring_cols if c in fs_train.columns}

    def _score_row(row):
        parts = []
        for c in scoring_cols:
            if c not in train_stats: continue
            mu, sd = train_stats[c]
            if sd == 0 or pd.isna(row.get(c)): continue
            z = (row[c] - mu) / sd
            z = max(-3.0, min(3.0, z))
            # Direction: fcf_yield/piotroski/int_cov positive · beneish negative
            if c == "beneish_m": parts.append(-z)
            else: parts.append(z)
        return sum(parts) / len(parts) if parts else None

    fs_train = fs_train.copy(); fs_test = fs_test.copy()
    fs_train["composite"] = fs_train.apply(_score_row, axis=1)
    fs_test["composite"] = fs_test.apply(_score_row, axis=1)

    def _decile_lift(df):
        df2 = df.dropna(subset=["composite"]).sort_values("composite", ascending=False)
        n = len(df2)
        if n < 10: return None
        decile = max(3, n // 10)
        top_r = df2.head(decile)["r20d"].mean()
        bot_r = df2.tail(decile)["r20d"].mean()
        return {"n": n, "decile_size": decile,
                "top_mean_ret": round(top_r * 100, 3),
                "bot_mean_ret": round(bot_r * 100, 3),
                "lift_pct": round((top_r - bot_r) * 100, 3)}

    train_lift = _decile_lift(fs_train)
    test_lift = _decile_lift(fs_test)

    # DSR on test-set top-decile Sharpe
    top_series = fs_test.dropna(subset=["composite"]).sort_values("composite", ascending=False)
    n_top = max(3, len(top_series) // 10)
    top_returns = top_series.head(n_top)["r20d"].tolist()
    dsr = None
    if len(top_returns) >= 3:
        mu = sum(top_returns) / len(top_returns)
        sd = math.sqrt(sum((x-mu)**2 for x in top_returns) / max(1, len(top_returns) - 1))
        sharpe = mu / sd if sd > 0 else 0
        # trial family count · 1 composite × 1 threshold (top-decile) · 1 horizon (20d)
        dsr = deflated_sharpe_ratio(sharpe, n_trials=1, n_returns=len(top_returns))

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 1,
        "market": market,
        "gate_status": "EXECUTED",
        "coverage_status": "TICKER-OOS · not temporal · walk-forward-temporal still blocked on accumulator SAMPLE_TIME",
        "n_train_tickers": len(fs_train),
        "n_test_tickers": len(fs_test),
        "train_stats": {c: {"mean": round(m, 4), "std": round(s, 4)} for c, (m, s) in train_stats.items()},
        "train_decile_lift": train_lift,
        "test_decile_lift": test_lift,
        "dsr_test_top_decile": dsr,
        "verdict": (
            f"EXECUTED · train lift {train_lift['lift_pct'] if train_lift else '?'}% "
            f"→ test lift {test_lift['lift_pct'] if test_lift else '?'}% · "
            "TICKER-OOS only · not temporal walk-forward"
        ),
        "governance_note": (
            "V2 §D.8 item 1 · F01-F05 to OOS. Temporal walk-forward blocked · "
            "fundamentals accumulator has 1 day of PIT history · needs 8+ quarters. "
            "Ticker-partition OOS gives directional evidence that composite generalises "
            "cross-sectionally within a market. This is NOT a promotion signal · "
            "R2 stays frozen · flag as CANDIDATE_FOR_R3_TIER1 if test-lift > train-lift × 0.5 "
            "(reasonable OOS-vs-IS ratio) AND DSR p-value < 0.10."
        ),
        "candidate_flag": bool(
            test_lift and train_lift and train_lift["lift_pct"] > 0
            and test_lift["lift_pct"] > train_lift["lift_pct"] * 0.5
            and dsr and dsr.get("p_value", 1.0) < 0.10
        ) if test_lift and train_lift and dsr else False,
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
