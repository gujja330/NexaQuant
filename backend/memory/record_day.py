"""Record one day of AEGIS historical memory, with provenance.

Reads only. Writes only under history/<market>/<asof>/. No production
artifact is touched and no production code path calls this module.

Each family is classified honestly. Where the underlying source carries no
observation/publication date, the family is recorded as PIT_BLOCKED with the
reason stated — never stamped with the asof to look available.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.memory.daily_snapshot import (
    DailySnapshot, Provenance, PIT_OK, PIT_BLOCKED, PIT_PARTIAL, seal, sha256_of)

NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_last_commit_date(root: Path, path: str, asof: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "log", "-1", "--format=%ad", "--date=short",
             "--before=%sT23:59:59+00:00" % asof, "--", path],
            text=True, stderr=subprocess.DEVNULL).strip()
        return out or None
    except Exception:
        return None


def _bars_dir(root: Path, market: str) -> Path:
    return (root / "usa" / "data" / "raw" / "us") if market == "usa" \
        else (root / "data" / "raw" / "india")


def record(root: Path, market: str, asof: date, *,
           allow_revision: bool = False) -> tuple[Path, DailySnapshot]:
    root = Path(root)
    m = market.lower()
    a = asof.isoformat()
    snap = DailySnapshot(market=m, asof=a)

    # ── universe (git provenance) ─────────────────────────────────────
    from backend.canonical.pit_provenance import (
        universe_asof, sector_asof, PIT_UNAVAILABLE, _UNIVERSE_FILE, _SECTOR_FILE)
    members, uprov = universe_asof(root, m, asof)
    if members == PIT_UNAVAILABLE:
        snap.add(Provenance(family="universe", source=_UNIVERSE_FILE[m],
                            pit_status=PIT_BLOCKED, asof=a,
                            retrieval_timestamp=NOW(),
                            blocked_reason=uprov.get("reason")), None)
        members = []
    else:
        snap.add(Provenance(
            family="universe", source="git:%s@%s" % (_UNIVERSE_FILE[m], uprov["rev"]),
            pit_status=PIT_OK, asof=a,
            observation_date=uprov.get("commit_date"),
            ingestion_date=uprov.get("commit_date"),
            source_timestamp=uprov.get("commit_date"),
            retrieval_timestamp=NOW(), n_records=len(members)), sorted(members))

    # ── sector (git provenance) ───────────────────────────────────────
    smap, sprov = sector_asof(root, m, asof)
    if smap == PIT_UNAVAILABLE:
        snap.add(Provenance(family="sector", source=_SECTOR_FILE[m],
                            pit_status=PIT_BLOCKED, asof=a,
                            retrieval_timestamp=NOW(),
                            blocked_reason=sprov.get("reason")), None)
    else:
        snap.add(Provenance(
            family="sector", source="git:%s@%s" % (_SECTOR_FILE[m], sprov["rev"]),
            pit_status=PIT_OK, asof=a,
            observation_date=sprov.get("commit_date"),
            ingestion_date=sprov.get("commit_date"),
            retrieval_timestamp=NOW(), n_records=len(smap)), smap)

    # ── prices (real per-bar dates) ───────────────────────────────────
    bd = _bars_dir(root, m)
    obs, n_sym = None, 0
    px: dict = {}
    for t in members:
        bare = t.replace(".NS", "")
        p = bd / ("%s_D1.parquet" % bare)
        if not p.exists():
            continue
        try:
            d = pd.read_parquet(p)
            d.index = pd.to_datetime(d.index)
            d = d[d.index.date <= asof]
            if d.empty:
                continue
            last = d.index[-1].date().isoformat()
            px[bare] = {"observation_date": last, "close": float(d["close"].iloc[-1])}
            n_sym += 1
            obs = max(obs, last) if obs else last
        except Exception:
            continue
    snap.add(Provenance(
        family="prices", source=str(bd.relative_to(root).as_posix()),
        pit_status=PIT_OK if n_sym else PIT_BLOCKED, asof=a,
        observation_date=obs, retrieval_timestamp=NOW(), n_records=n_sym,
        revision_status="MIXED_ADJUSTMENT_BASIS" if m == "india" else "ORIGINAL",
        blocked_reason=None if n_sym else "no bars on or before asof"), px)

    # ── technical features: the matrix R2 ACTUALLY CONSUMED ───────────
    # Read the production snapshot rather than recomputing. A rebuild is a
    # reconstruction of what we could derive today; only features/<market>/
    # <asof>.parquet is what the engine was handed on the day. If it is
    # absent there is no record of what was consumed, and that is BLOCKED —
    # not an invitation to recompute one.
    feat_p = root / "features" / m / ("%s.parquet" % a)
    if feat_p.exists():
        fdf = pd.read_parquet(feat_p)
        snap.attach_frame("technical_features.parquet", fdf.reset_index(drop=True))
        snap.add(Provenance(
            family="technical", source="features/%s/%s.parquet" % (m, a),
            pit_status=PIT_OK, asof=a, observation_date=obs or a,
            effective_date=obs, retrieval_timestamp=NOW(), n_records=len(fdf)),
            {"sidecar": "technical_features.parquet", "n_rows": int(len(fdf)),
             "n_cols": int(fdf.shape[1]),
             "source": "production feature snapshot consumed by R2"})
    else:
        snap.add(Provenance(
            family="technical", source="features/%s/%s.parquet" % (m, a),
            pit_status=PIT_BLOCKED, asof=a, retrieval_timestamp=NOW(),
            blocked_reason="no production feature snapshot for this asof; what "
                           "R2 consumed was not recorded and must not be recomputed"),
            None)

    # ── market cap ────────────────────────────────────────────────────
    if m == "india":
        snap.add(Provenance(
            family="market_cap", source="data/raw/india/fundamentals.parquet",
            pit_status=PIT_BLOCKED, asof=a, retrieval_timestamp=NOW(),
            blocked_reason="no market-cap column exists (0/228)"), None)
    else:
        ing = _git_last_commit_date(root, "usa/reports/fundamentals.json", a)
        snap.add(Provenance(
            family="market_cap", source="usa/reports/fundamentals.json",
            pit_status=PIT_PARTIAL if ing else PIT_BLOCKED, asof=a,
            ingestion_date=ing, observation_date=ing, retrieval_timestamp=NOW(),
            blocked_reason=None if ing else "no committed version on or before asof"),
            {"note": "ingestion-date provenance only; values carry no publication date"})

    # ── fundamentals / earnings ───────────────────────────────────────
    if m == "india":
        for fam in ("fundamentals", "earnings"):
            snap.add(Provenance(
                family=fam, source="data/raw/india/fundamentals.parquet",
                pit_status=PIT_BLOCKED, asof=a, retrieval_timestamp=NOW(),
                blocked_reason=("single undated cross-section; no period_end/"
                                "filing_date/announcement_date"
                                if fam == "fundamentals" else
                                "only a forward next_earnings field; no announcement history")),
                None)
    else:
        ingf = _git_last_commit_date(root, "usa/reports/fundamentals.json", a)
        inge = _git_last_commit_date(root, "usa/reports/earnings_summary.json", a)
        snap.add(Provenance(
            family="fundamentals", source="usa/reports/fundamentals.json",
            pit_status=PIT_PARTIAL if ingf else PIT_BLOCKED, asof=a,
            ingestion_date=ingf, observation_date=ingf, retrieval_timestamp=NOW(),
            blocked_reason=None if ingf else "no committed version on or before asof"),
            {"note": "ingestion-date only"})
        snap.add(Provenance(
            family="earnings", source="usa/reports/earnings_summary.json",
            pit_status=PIT_PARTIAL if inge else PIT_BLOCKED, asof=a,
            ingestion_date=inge, observation_date=inge, retrieval_timestamp=NOW(),
            blocked_reason=None if inge else "no committed version on or before asof"),
            {"note": "ingestion-date only"})

    # ── macro ─────────────────────────────────────────────────────────
    mp = root / "usa" / "data" / "raw" / "us" / "macro.parquet"
    if m == "usa" and mp.exists():
        d = pd.read_parquet(mp)
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"])
        d = d[d["date"].dt.date <= asof]
        if d.empty:
            snap.add(Provenance(family="macro", source=str(mp.name),
                                pit_status=PIT_BLOCKED, asof=a,
                                retrieval_timestamp=NOW(),
                                blocked_reason="no macro observation on or before asof"), None)
        else:
            latest = d.sort_values("date").groupby("symbol").tail(1)
            od = latest["date"].max().date().isoformat()
            snap.add(Provenance(
                family="macro", source="usa/data/raw/us/macro.parquet",
                pit_status=PIT_OK, asof=a, observation_date=od,
                retrieval_timestamp=NOW(), n_records=len(latest)),
                {r["symbol"]: {"observation_date": r["date"].date().isoformat(),
                               "close": float(r["close"])}
                 for _, r in latest.iterrows()})
    else:
        snap.add(Provenance(
            family="macro",
            source="reports/macro_summary.json" if m == "india" else "usa macro.parquet",
            pit_status=PIT_BLOCKED, asof=a, retrieval_timestamp=NOW(),
            blocked_reason=("source file does not exist; adapter stamps asof=cutoff "
                            "at row level" if m == "india" else "source absent")), None)

    snap.add(Provenance(
        family="intermarket", source="reports/macro_history.parquet",
        pit_status=PIT_BLOCKED, asof=a, retrieval_timestamp=NOW(),
        blocked_reason="regime log only (6 rows), not a feature substrate"), None)

    # ── R2 configuration + decision fingerprints ──────────────────────
    selp = root / ("reports/selected_features.json" if m == "india"
                   else "usa/reports/selected_features.json")
    sel = json.loads(selp.read_text(encoding="utf-8")) if selp.exists() else {}
    import yaml
    cfg = yaml.safe_load((root / "configs/opportunity_registry.yaml").read_text(encoding="utf-8"))
    risk = cfg.get("risk_engine", {})
    # The working copy is TODAY's config. It is only evidence for `asof` if
    # git shows it was already committed by then.
    cfg_commit = _git_last_commit_date(root, "configs/opportunity_registry.yaml", a)
    sel_commit = _git_last_commit_date(
        root, "reports/selected_features.json" if m == "india"
        else "usa/reports/selected_features.json", a)
    cfg_is_pit = bool(cfg_commit)
    snap.add(Provenance(
        family="r2_config", source="configs/opportunity_registry.yaml + selected_features.json",
        pit_status=PIT_OK if cfg_is_pit else PIT_BLOCKED, asof=a,
        observation_date=cfg_commit, ingestion_date=cfg_commit,
        effective_date=sel_commit or cfg_commit,
        blocked_reason=None if cfg_is_pit else "no committed R2 config on or before asof",
        retrieval_timestamp=NOW(),
        schema_fingerprint=sel.get("schema_fingerprint"),
        config_fingerprint=sha256_of(risk)[:12]),
        {"risk_engine": risk, "n_selected": sel.get("n_selected"),
         "selected_fingerprint": sha256_of(sel.get("selected", []))[:12],
         "schema_fingerprint": sel.get("schema_fingerprint")})

    # ── R2 scores actually emitted ────────────────────────────────────
    sc = root / "reports" / "research" / "shadow" / ("full_universe_shadow_%s.json" % m)
    sc_asof, sc_rows = None, []
    if sc.exists():
        try:
            _d = json.loads(sc.read_text(encoding="utf-8"))
            sc_asof, sc_rows = _d.get("asof"), (_d.get("rows") or [])
        except Exception:
            sc_asof, sc_rows = None, []
    if sc_rows and sc_asof == a:
        sdf = pd.DataFrame(sc_rows)
        snap.attach_frame("r2_scores.parquet", sdf)
        snap.add(Provenance(
            family="r2_scores",
            source="reports/research/shadow/full_universe_shadow_%s.json" % m,
            pit_status=PIT_OK, asof=a, observation_date=sc_asof,
            effective_date=sc_asof, retrieval_timestamp=NOW(), n_records=len(sdf)),
            {"sidecar": "r2_scores.parquet", "n_rows": int(len(sdf)),
             "columns": list(sdf.columns)})
    else:
        snap.add(Provenance(
            family="r2_scores",
            source="reports/research/shadow/full_universe_shadow_%s.json" % m,
            pit_status=PIT_BLOCKED, asof=a, observation_date=sc_asof,
            retrieval_timestamp=NOW(),
            blocked_reason=("scores describe %s, not %s" % (sc_asof, a)) if sc_rows
                           else "no R2 score artifact for this market"), None)

    lc = root / "reports" / "context" / ("canonical_lifecycle_%s.json" % m)
    dec = None
    if lc.exists():
        L = json.loads(lc.read_text(encoding="utf-8"))
        dec = {"lifecycle_asof": L.get("asof"),
               "market_data_asof": L.get("market_data_asof"),
               "counts": L.get("counts"),
               "current": [{"position_id": c.get("position_id"), "ticker": c.get("ticker"),
                            "engine": c.get("engine"), "action": c.get("action"),
                            "confidence_pct": c.get("confidence_pct"),
                            "entry_date": c.get("entry_date"), "entry_price": c.get("entry_price"),
                            "stop": c.get("stop"), "admission_status": c.get("admission_status")}
                           for c in L.get("current", [])]}
    # A lifecycle file always holds the LATEST decision state. Recording it
    # under an earlier asof would store today's decisions as history — the
    # exact substitution this layer exists to prevent. It is PIT_OK only when
    # the lifecycle genuinely describes the requested day.
    lc_asof = (dec or {}).get("lifecycle_asof")
    dec_is_pit = bool(dec) and lc_asof == a
    if dec and not dec_is_pit:
        reason = ("lifecycle describes %s, not %s; a past decision state cannot "
                  "be recovered from the current file" % (lc_asof, a))
        dec_payload = {"lifecycle_asof": lc_asof, "withheld": True,
                       "reason": reason}
    else:
        reason = None if dec else "no canonical lifecycle for this market"
        dec_payload = dec
    snap.add(Provenance(
        family="r2_decision", source="reports/context/canonical_lifecycle_%s.json" % m,
        pit_status=PIT_OK if dec_is_pit else PIT_BLOCKED, asof=a,
        observation_date=lc_asof,
        effective_date=(dec or {}).get("market_data_asof"),
        retrieval_timestamp=NOW(),
        n_records=len((dec or {}).get("current", [])) if dec_is_pit else 0,
        blocked_reason=reason), dec_payload)
    if dec_is_pit and (dec or {}).get("current"):
        snap.attach_frame("decisions.parquet", pd.DataFrame(dec["current"]))

    snap.fingerprints = {
        "schema_version": snap.schema_version,
        "feature_schema_fingerprint": sel.get("schema_fingerprint"),
        "selected_feature_fingerprint": sha256_of(sel.get("selected", []))[:12],
        "r2_config_fingerprint": sha256_of(risk)[:12],
    }
    p = seal(root, snap, allow_revision=allow_revision)
    return p, snap
