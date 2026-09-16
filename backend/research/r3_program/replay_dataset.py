"""R3 HISTORICAL REPLAY DATASET - assembled from sealed memory only.

THE RULE THIS MODULE EXISTS TO ENFORCE
--------------------------------------
A replay row may contain only what was sealed on its as_of date, plus outcomes
measured strictly after it. Nothing is recomputed from current data. If the
sealed evidence for a date is absent or fails verification, that date produces
no rows at all - it is never backfilled from the live working tree.

That sounds obvious and is exactly the rule the evidence-vector probe originally
broke: it read `features/<market>/<asof>.parquet`, an ephemeral path that the
next run overwrites. A dataset built that way describes the present wearing a
past date. Here the only admissible input is
`history/<market>/<asof>/technical_features.parquet`, whose sha256 lives inside
SEALED, and the builder calls verify_seal() before reading a single row.

THE OUTCOME SIDE
----------------
Forward returns are computed from bars with index strictly greater than the
as_of timestamp. A horizon with fewer than n available bars yields None, never a
shorter window silently relabelled. On a young memory layer most long horizons
are legitimately empty; reporting that emptiness is the point, because it is the
difference between "no signal" and "no data".

SCOPE
-----
Research only. Writes under reports/research/r3/ and data/research/r3/.
R3 production writes remain 0.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.replay_dataset.v1"

HORIZONS = (1, 3, 5, 10, 20)
BARS = {"india": "data/raw/india/%s_D1.parquet",
        "usa": "usa/data/raw/us/%s_D1.parquet"}

_BARS: dict = {}


def _tkey(t) -> str:
    """The ONE canonical join key for a ticker in this module.

    Defined once, on purpose. Every alias-drift incident in this repo has come
    from two consumers each keeping a private idea of what a ticker looks like.
    """
    return str(t).upper().strip().replace(".NS", "").replace(".BO", "")


def _bars(root: Path, market: str, ticker: str) -> Optional[pd.DataFrame]:
    key = (str(root), market, ticker)
    if key in _BARS:
        return _BARS[key]
    t = str(ticker).upper().replace(".NS", "").replace(".BO", "")
    p = root / (BARS[market] % t)
    d = None
    if p.exists():
        try:
            d = pd.read_parquet(p)
            d.index = pd.to_datetime(d.index)
            d = d.sort_index()
        except Exception:
            d = None
    _BARS[key] = d
    return d


def _forward(root: Path, market: str, ticker: str, asof: str,
             mfe_window: int = 60) -> dict:
    """Outcomes measured strictly AFTER asof. Short history gives None, not a
    truncated window relabelled as a full one.

    Each horizon carries its OWN outcome_date. The mandate is explicit that a
    prediction date and an outcome date must never be merged into one field:
    once they are, nothing downstream can tell whether a row leaked, because the
    only evidence of the gap has been overwritten.
    """
    out: dict = {}
    for h in HORIZONS:
        out["fwd_%dd" % h] = None
        out["fwd_%dd_outcome_date" % h] = None
    out.update({"n_fwd_bars": 0, "asof_close": None,
                "excursion_low_pct": None, "excursion_high_pct": None,
                "time_to_low_d": None, "time_to_high_d": None,
                "excursion_window_bars": 0})
    b = _bars(root, market, ticker)
    if b is None:
        return out
    a = pd.Timestamp(asof)
    past, fut = b[b.index <= a], b[b.index > a]
    if past.empty or fut.empty:
        return out
    p0 = float(past["close"].iloc[-1])
    if not p0:
        return out
    out["n_fwd_bars"] = len(fut)
    out["asof_close"] = p0
    for h in HORIZONS:
        if len(fut) >= h:
            out["fwd_%dd" % h] = 100.0 * (float(fut["close"].iloc[h - 1]) - p0) / p0
            out["fwd_%dd_outcome_date" % h] = fut.index[h - 1].date().isoformat()

    # Excursion from the as_of CLOSE, over whatever forward window exists and
    # reported WITH its length so a 2-bar move is never read as a 60-bar one.
    #
    # These are deliberately NOT called MAE/MFE. MAE and MFE are entry-relative:
    # they measure how far a POSITION went against or in favour of its entry.
    # Most rows here are universe names that were never entered, so there is no
    # entry to be adverse to - and indeed 30 of 224 rows had a positive "MAE"
    # because the low simply never traded below the as_of close. True MAE/MFE
    # are computed separately, only for rows carrying a real entry_price.
    w = fut.iloc[:mfe_window]
    if len(w) and {"low", "high"} <= set(w.columns):
        lo, hi = w["low"].astype(float), w["high"].astype(float)
        out["excursion_low_pct"] = 100.0 * (float(lo.min()) - p0) / p0
        out["excursion_high_pct"] = 100.0 * (float(hi.max()) - p0) / p0
        out["time_to_low_d"] = int(lo.reset_index(drop=True).idxmin()) + 1
        out["time_to_high_d"] = int(hi.reset_index(drop=True).idxmax()) + 1
        out["excursion_window_bars"] = len(w)
        out["_low_abs"] = float(lo.min())
        out["_high_abs"] = float(hi.max())
    return out


def build_date(root: Path, market: str, asof: str) -> tuple[pd.DataFrame, dict]:
    """One as_of -> (rows, provenance). Refuses anything not sealed and valid."""
    from backend.memory.daily_snapshot import snapshot_dir, verify_seal, load
    from backend.research.r3_program.evidence_vector import replay_ready

    prov: dict = {"market": market, "as_of": asof, "rows": 0, "admitted": False}
    gate = replay_ready(root, market, date.fromisoformat(asof))
    prov["replay_gate"] = gate["R3_HISTORICAL_REPLAY_READY"]
    prov["blockers"] = gate["blockers"]
    if not gate["R3_HISTORICAL_REPLAY_READY"]:
        prov["refused"] = "GATE_NOT_MET"
        return pd.DataFrame(), prov

    ok, msg = verify_seal(root, market, asof)
    prov["seal_verified"] = ok
    if not ok:
        prov["refused"] = "SEAL_%s" % msg.split(":")[0]
        return pd.DataFrame(), prov

    d = snapshot_dir(root, market, asof)
    feat_p, dec_p = d / "technical_features.parquet", d / "decisions.parquet"
    if not feat_p.exists():
        prov["refused"] = "NO_SEALED_TECHNICAL"
        return pd.DataFrame(), prov

    df = pd.read_parquet(feat_p)
    df["ticker"] = df["ticker"].astype(str)
    # ONE join key, derived in one place. The India technical matrix stores
    # `AARTIIND.NS` while the decisions sidecar stores `AARTIIND`, so a join on
    # the raw column matched 0 of 56 India decisions and silently produced an
    # empty portfolio link on every India date - while USA, which has no
    # suffix, matched perfectly and made the join look correct.
    df["_tkey"] = df["ticker"].map(_tkey)
    prov["technical_rows"] = len(df)
    prov["technical_cols"] = len(df.columns)

    # sealed decisions: which of those names R2 actually acted on that day
    if dec_p.exists():
        dec = pd.read_parquet(dec_p)
        dec["ticker"] = dec["ticker"].astype(str)
        prov["decision_rows"] = len(dec)

        # `ticker` is NOT the key of this sidecar; `position_id` is. The same
        # name can be held simultaneously by a legacy R1 position and an R2 one
        # (KOTAKBANK, COALINDIA, CRM, GRMN, VLO all were on 2026-09-15). A plain
        # merge on ticker fans one feature row into two and silently inflates
        # every downstream count - USA produced 521 rows from a 516-row matrix.
        dec["_tkey"] = dec["ticker"].map(_tkey)
        eng = dec.get("engine", pd.Series([""] * len(dec))).astype(str).str.upper()
        r2 = dec[eng.str.startswith("R2")].copy()
        r1_keys = set(dec.loc[eng.str.startswith("R1"), "_tkey"])
        prov["decision_rows_r2"] = len(r2)
        prov["decision_rows_legacy_r1"] = len(dec) - len(r2)

        if r2["_tkey"].duplicated().any():
            prov["admitted"] = False
            prov["refused"] = "R2_TICKER_NOT_UNIQUE_%s" % sorted(
                r2.loc[r2["_tkey"].duplicated(), "_tkey"])[:5]
            return pd.DataFrame(), prov

        # A join that matches NOTHING is a broken key, not an empty book. It
        # must refuse rather than emit a dataset whose portfolio link is
        # uniformly absent - that reads downstream as "no positions held".
        matched = len(set(r2["_tkey"]) & set(df["_tkey"]))
        prov["decision_match"] = matched
        prov["decision_match_rate_pct"] = (
            round(100.0 * matched / len(r2), 1) if len(r2) else None)
        if len(r2) and matched == 0:
            prov["admitted"] = False
            prov["refused"] = "DECISION_JOIN_MATCHED_0_OF_%d" % len(r2)
            return pd.DataFrame(), prov

        dup = [c for c in r2.columns if c in df.columns and c not in ("ticker", "_tkey")]
        r2 = r2.rename(columns={c: "dec_%s" % c for c in dup})
        r2 = r2.drop(columns=["ticker"])
        before = len(df)
        df = df.merge(r2, on="_tkey", how="left")
        assert len(df) == before, "decision merge changed the row count"
        df["in_sealed_decisions"] = df["_tkey"].isin(set(r2["_tkey"])).astype(int)
        # kept as a flag, never as an extra row
        df["legacy_r1_open"] = df["_tkey"].isin(r1_keys).astype(int)
    else:
        df["in_sealed_decisions"] = 0
        df["legacy_r1_open"] = 0
        prov["decision_rows"] = 0
        prov["decision_rows_r2"] = 0
        prov["decision_rows_legacy_r1"] = 0

    snap = load(root, market, asof) or {}
    prov["snapshot_schema"] = snap.get("schema_version")
    prov["feature_schema_fingerprint"] = (snap.get("fingerprints") or {}).get(
        "feature_schema_fingerprint")

    fwd = pd.DataFrame([_forward(root, market, t, asof) for t in df["ticker"]])
    # On a young memory layer every long horizon is legitimately all-NA. Pin the
    # dtype so those columns stay float64 instead of object, and so concat does
    # not change its mind about them in a later pandas.
    for h in HORIZONS:
        fwd["fwd_%dd" % h] = pd.to_numeric(fwd["fwd_%dd" % h], errors="coerce").astype("float64")
    for c in ("asof_close", "excursion_low_pct", "excursion_high_pct",
              "time_to_low_d", "time_to_high_d", "_low_abs", "_high_abs"):
        if c in fwd.columns:
            fwd[c] = pd.to_numeric(fwd[c], errors="coerce").astype("float64")
    df = pd.concat([df.reset_index(drop=True), fwd.reset_index(drop=True)], axis=1)
    # The sealed matrix may already carry these. Overwrite in place rather than
    # inserting a second column of the same name - two `market` columns would
    # make every later groupby ambiguous.
    for i, (col, val) in enumerate((("as_of", asof), ("market", market))):
        if col in df.columns:
            # A sealed matrix labelled with a different date than the directory
            # it sits in is a provenance failure, not something to paper over.
            present = set(df[col].dropna().astype(str).unique())
            if present and present != {str(val)}:
                prov["admitted"] = False
                prov["refused"] = "PROVENANCE_MISMATCH_%s=%s" % (
                    col, sorted(present)[:3])
                return pd.DataFrame(), prov
            df[col] = val
        else:
            df.insert(i, col, val)

    # TRUE MAE/MFE — entry-relative, and therefore only defined for rows that
    # actually carry an entry price from the sealed decisions. For every other
    # name in the universe these stay null rather than silently reusing the
    # as_of close as a pseudo-entry, which is what makes a "maximum ADVERSE
    # excursion" come out positive.
    ep = None
    for c in ("entry_price", "dec_entry_price"):
        if c in df.columns and df[c].notna().any():
            ep = c
            break
    df["entry_mae_pct"] = pd.NA
    df["entry_mfe_pct"] = pd.NA
    if ep and "_low_abs" in df.columns:
        m = df[ep].notna() & (pd.to_numeric(df[ep], errors="coerce") > 0) \
            & df["_low_abs"].notna()
        e = pd.to_numeric(df.loc[m, ep], errors="coerce")
        df.loc[m, "entry_mae_pct"] = 100.0 * (df.loc[m, "_low_abs"] - e) / e
        df.loc[m, "entry_mfe_pct"] = 100.0 * (df.loc[m, "_high_abs"] - e) / e
    df["entry_mae_pct"] = pd.to_numeric(df["entry_mae_pct"], errors="coerce").astype("float64")
    df["entry_mfe_pct"] = pd.to_numeric(df["entry_mfe_pct"], errors="coerce").astype("float64")
    prov["entry_relative_mae_rows"] = int(df["entry_mae_pct"].notna().sum())
    df = df.drop(columns=[c for c in ("_low_abs", "_high_abs") if c in df.columns])

    # §2 identity/provenance. prediction_as_of is deliberately a SEPARATE column
    # from as_of so that a later join cannot quietly reuse one for the other.
    df["prediction_as_of"] = asof
    df["run_id"] = "%s:%s" % (market, asof)
    df["source"] = "memory-v2 sealed snapshot"
    df["feature_schema_version"] = prov.get("feature_schema_fingerprint")
    df["snapshot_schema_version"] = prov.get("snapshot_schema")

    # LEAKAGE ASSERTION. Every outcome date must strictly postdate the
    # prediction date. This is cheap and it is the one error that would
    # invalidate every number downstream, so it is checked rather than assumed.
    for h in HORIZONS:
        col = "fwd_%dd_outcome_date" % h
        bad = df[df[col].notna() & (df[col].astype(str) <= asof)]
        if len(bad):
            prov["admitted"] = False
            prov["refused"] = "LEAKAGE_%s_ON_OR_BEFORE_ASOF_n=%d" % (col, len(bad))
            return pd.DataFrame(), prov

    prov["rows"] = len(df)
    prov["admitted"] = True
    prov["outcome_coverage"] = {
        "fwd_%dd" % h: int(df["fwd_%dd" % h].notna().sum()) for h in HORIZONS}
    return df, prov


def _align_concat(frames: list) -> pd.DataFrame:
    """Union the columns explicitly before stacking.

    India and USA seal different decision columns, so a plain concat leaves
    whole columns all-NA for one market and pandas then infers their dtype from
    nothing - it currently drops them from the dtype decision and warns that a
    future version will not. Deciding the dtype here, from the frame that
    actually has the column, keeps the result stable across pandas versions
    instead of leaving a silent schema change waiting in an upgrade.
    """
    if not frames:
        return pd.DataFrame()
    cols: list = []
    for f in frames:
        for c in f.columns:
            if c not in cols:
                cols.append(c)
    # The dtype a column SHOULD have, taken from a frame that actually holds
    # values. A column of all-None arrives as `object`, not float64 - which is
    # how a numeric feature that happens to be empty for one market (India has
    # no earnings, institutional or insider coverage in sealed memory) silently
    # turns the stacked column into object and makes concat guess.
    dtypes = {}
    for c in cols:
        for f in frames:
            if c in f.columns and not f[c].isna().all():
                dtypes[c] = f[c].dtype
                break
    fixed = []
    for f in frames:
        g = f.reindex(columns=cols)
        for c, dt in dtypes.items():
            if g[c].isna().all() and g[c].dtype != dt:
                try:
                    g[c] = g[c].astype(dt)
                except (TypeError, ValueError):
                    pass
        fixed.append(g)
    return pd.concat(fixed, ignore_index=True)


def substrate_holes(df: pd.DataFrame) -> dict:
    """Which feature columns are structurally empty, per market.

    This is evidence in its own right. `sector` being 100% null for India on
    every sealed date is the known SECTOR-1 defect; `sma_200` being null in BOTH
    markets means the column exists but was never populated. A research wave that
    reads such a column gets nulls, not a signal, and the difference between
    "no relationship" and "no data" is the whole game.
    """
    if df.empty:
        return {}
    out: dict = {}
    for m, g in df.groupby("market"):
        empty = sorted(c for c in g.columns if g[c].isna().all())
        out[str(m)] = {
            "columns": len(g.columns),
            "fully_empty": len(empty),
            "fully_empty_columns": empty,
        }
    both = set.intersection(*[set(v["fully_empty_columns"]) for v in out.values()]) \
        if len(out) > 1 else set(next(iter(out.values()))["fully_empty_columns"])
    out["_empty_in_every_market"] = sorted(both)
    return out


def build(root: Path) -> tuple[pd.DataFrame, dict]:
    """Every replay-ready as_of across both markets."""
    root = Path(root)
    frames, provs = [], []
    for market in ("india", "usa"):
        d = root / "history" / market
        if not d.exists():
            continue
        for p in sorted(x for x in d.iterdir()
                        if x.is_dir() and (x / "SEALED").exists()):
            df, prov = build_date(root, market, p.name)
            provs.append(prov)
            if not df.empty:
                frames.append(df)
    out = _align_concat(frames)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dates_considered": len(provs),
        "dates_admitted": sum(1 for p in provs if p["admitted"]),
        "dates_refused": [
            {"market": p["market"], "as_of": p["as_of"],
             "reason": p.get("refused"), "blockers": p.get("blockers")}
            for p in provs if not p["admitted"]],
        "rows": len(out),
        # THE BINDING UNIT. Rows are names; dates are bets.
        "effective_units": len({(p["market"], p["as_of"])
                                for p in provs if p["admitted"]}),
        "per_date": provs,
    }
    if not out.empty:
        manifest["outcome_coverage"] = {
            "fwd_%dd" % h: int(out["fwd_%dd" % h].notna().sum()) for h in HORIZONS}
        manifest["outcome_coverage_pct"] = {
            "fwd_%dd" % h: round(100.0 * out["fwd_%dd" % h].notna().sum() / len(out), 1)
            for h in HORIZONS}
        manifest["substrate_holes"] = substrate_holes(out)
    return out, manifest
