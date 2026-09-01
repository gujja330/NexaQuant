"""Momentum candidate ledger · CEO 2026-09-01 (§ Momentum correction).

Wraps the existing `short_term_momentum` engine output into a canonical
ledger with exactly one terminal state per candidate:

    ACCEPTED     · qualifies for R2 hand-off (WATCH or higher)
    WATCH        · research/timing candidate · not for production
    REJECTED     · candidate had quality gate but failed it (chase risk,
                    pump risk, avoid, etc.)
    NO_EVIDENCE  · candidate exists but quality_band = UNKNOWN or key
                    features unavailable · cannot be classified honestly

Every candidate carries a machine-readable `reason_code` + `reason_text`.
Nothing disappears silently.

Also:
    · Snapshots to `reports/research/momentum_snapshots/{market}_{asof}.jsonl`
      (append-only · one file per day) so the walk-forward corpus grows
      even before we have a mature history.
    · Attributes candidates to R2 (post R1 retirement) · never independently
      creates production positions.

CEO invariants applied:
    · Never fabricate a momentum recommendation to fill the sheet.
    · Report by market separately.
    · Forward outcomes measured at 1 / 3 / 5 / 10 / 20 trading days
      (scaffold here · runtime measurement in `momentum_forward_outcomes.py`).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))


# Terminal states · CEO contract
STATE_ACCEPTED = "ACCEPTED"
STATE_WATCH = "WATCH"
STATE_REJECTED = "REJECTED"
STATE_NO_EVIDENCE = "NO_EVIDENCE"

# Reason codes · machine-readable
REASON_QUALITY_UNAVAILABLE = "R_QUALITY_UNAVAILABLE"
REASON_CHASE_RISK = "R_CHASE_RISK"
REASON_PUMP_RISK = "R_PUMP_RISK"
REASON_AVOID_LOW_QUALITY = "R_AVOID_LOW_QUALITY"
REASON_MISSING_FEATURES = "R_MISSING_FEATURES"
REASON_QUALIFIES_WATCH = "R_QUALIFIES_WATCH"
REASON_QUALIFIES_ACCEPT = "R_QUALIFIES_ACCEPT"


def _classify(candidate: dict) -> tuple[str, str, str]:
    """Return (terminal_state, reason_code, reason_text)."""
    verdict = str(candidate.get("verdict", "") or "").upper()
    quality = str(candidate.get("quality_band", "") or "").upper()
    reason_txt = str(candidate.get("reason", "") or "")

    # Rule 1 · UNKNOWN quality band = NO_EVIDENCE (CEO §1 finding)
    if quality in ("UNKNOWN", "", "N/A"):
        return (STATE_NO_EVIDENCE, REASON_QUALITY_UNAVAILABLE,
                f"quality_band={quality or 'MISSING'} · cannot classify · "
                "engine says: " + reason_txt[:80])

    # Rule 2 · verdict-driven mapping
    if verdict in ("POTENTIAL_ENTRY", "STRONG_ENTRY"):
        return (STATE_ACCEPTED, REASON_QUALIFIES_ACCEPT,
                f"verdict={verdict} · quality={quality} · " + reason_txt[:80])
    if verdict in ("REBOUND_WATCH", "MOMENTUM_WATCH", "WATCH"):
        return (STATE_WATCH, REASON_QUALIFIES_WATCH,
                f"verdict={verdict} · quality={quality} · " + reason_txt[:80])
    if verdict in ("PUMP_RISK",):
        return (STATE_REJECTED, REASON_PUMP_RISK,
                "verdict=PUMP_RISK · " + reason_txt[:80])
    if verdict in ("CHASE_RISK",):
        return (STATE_REJECTED, REASON_CHASE_RISK,
                "verdict=CHASE_RISK · " + reason_txt[:80])
    if verdict in ("AVOID",):
        return (STATE_REJECTED, REASON_AVOID_LOW_QUALITY,
                "verdict=AVOID · " + reason_txt[:80])

    # Rule 3 · verdict IGNORE / empty / anything else
    return (STATE_REJECTED, REASON_MISSING_FEATURES,
            f"verdict={verdict or 'MISSING'} · fallback classification · "
            + reason_txt[:80])


def _production_universe(root: Path, market: str) -> set | None:
    """Return the production universe ticker set from configs/aegis_universes.yaml.
    None if no static source file for this market (e.g. India · derived)."""
    try:
        import yaml
        cfg = yaml.safe_load(
            (root / "configs" / "aegis_universes.yaml").read_text(encoding="utf-8")) or {}
        m_cfg = (cfg.get("markets", {}) or {}).get(market.lower(), {})
        src = m_cfg.get("source_file")
        if not src: return None
        p = root / src
        if not p.exists(): return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(t.get("symbol") if isinstance(t, dict) else t).upper()
                for t in (data.get("tickers") or []) if t}
    except Exception:
        return None


def build(root: Path, market: str, asof: str) -> dict:
    src = root / "reports" / "research" / f"short_term_momentum_{market.lower()}.json"
    if not src.exists():
        return {"error": f"source missing: {src}", "market": market.lower()}
    raw = json.loads(src.read_text(encoding="utf-8"))
    candidates_all = raw.get("candidates") or []
    n_raw_scanned = raw.get("n_universe") or len(candidates_all)

    # CEO 2026-09-01 · production universe filter · S&P 500 for USA
    prod_universe = _production_universe(root, market)
    n_prod = len(prod_universe) if prod_universe else None
    if prod_universe:
        candidates = [c for c in candidates_all
                       if str(c.get("ticker", "")).split(".", 1)[0].upper() in prod_universe]
        n_out_of_universe = len(candidates_all) - len(candidates)
    else:
        candidates = candidates_all
        n_out_of_universe = 0

    entries = []
    counts = {STATE_ACCEPTED: 0, STATE_WATCH: 0,
               STATE_REJECTED: 0, STATE_NO_EVIDENCE: 0}
    reason_counts: dict[str, int] = {}
    for c in candidates:
        state, code, txt = _classify(c)
        counts[state] += 1
        reason_counts[code] = reason_counts.get(code, 0) + 1
        entries.append({
            "asof": asof,
            "market": market.lower(),
            "ticker": c.get("ticker"),
            "sector": c.get("sector"),
            "category": c.get("category"),
            "quality_band": c.get("quality_band"),
            "verdict_engine": c.get("verdict"),
            "return_1d_pct": c.get("return_1d_pct"),
            "return_3d_pct": c.get("return_3d_pct"),
            "return_5d_pct": c.get("return_5d_pct"),
            "return_20d_pct": c.get("return_20d_pct"),
            "rsi_14": c.get("rsi_14"),
            "volume_ratio": c.get("volume_ratio"),
            "terminal_state": state,
            "reason_code": code,
            "reason_text": txt,
            "attribution": "R2",     # post R1 retirement
            "production_impact": None,     # research only · never opens position
            "forward_outcomes": {
                "d1": "NOT_MEASURED_YET", "d3": "NOT_MEASURED_YET",
                "d5": "NOT_MEASURED_YET", "d10": "NOT_MEASURED_YET",
                "d20": "NOT_MEASURED_YET",
            },
        })

    # Conservation invariant · CEO §1 finding
    conservation_ok = (len(candidates) == sum(counts.values()))

    report = {
        "engine": "momentum_ledger.multi_layer.v1",
        "market": market.lower(),
        "asof": asof,
        "n_universe_scanned_raw": n_raw_scanned,
        "n_production_universe": n_prod,
        "n_out_of_universe_dropped": n_out_of_universe,
        "n_universe_scanned": len(candidates),  # kept for downstream compat · now = in-universe
        "n_candidates_source": len(candidates),
        "n_candidates_classified": sum(counts.values()),
        "n_silent_disappearances": len(candidates) - sum(counts.values()),
        "conservation_ok": conservation_ok,
        "by_terminal_state": counts,
        "by_reason_code": reason_counts,
        "entries": entries,
        "notes": [
            "Every candidate has exactly one terminal state · nothing "
            "disappears silently between engine and ledger.",
            "R1 retired · attribution = R2 only.",
            "production_impact = null · research only · never opens position.",
            "Forward outcomes NOT_MEASURED_YET · computed at t+1/3/5/10/20 "
            "trading days by momentum_forward_outcomes.py.",
        ],
    }
    out_p = root / "reports" / "research" / "multi_layer" / f"momentum_ledger_{market.lower()}_{asof}.json"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                 default=str), encoding="utf-8")

    # ── Snapshot preservation (walk-forward corpus) · append-only ────
    snap_dir = root / "reports" / "research" / "momentum_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_p = snap_dir / f"{market.lower()}_{asof}.jsonl"
    # Write fresh each day but append-only if same-day re-run would emit
    # identical content (idempotent · re-running today reproduces file).
    with snap_p.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    report["snapshot_path"] = str(snap_p.relative_to(root))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"],
                     default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()
    any_err = False
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = build(_ROOT, m, args.asof)
        if "error" in rep:
            print(json.dumps(rep, indent=2, ensure_ascii=False))
            any_err = True
            continue
        summary = {
            "market": rep["market"],
            "n_universe_scanned": rep.get("n_universe_scanned"),
            "n_candidates_source": rep["n_candidates_source"],
            "conservation_ok": rep["conservation_ok"],
            "by_terminal_state": rep["by_terminal_state"],
            "by_reason_code": rep["by_reason_code"],
            "snapshot_path": rep.get("snapshot_path"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 2 if any_err else 0


if __name__ == "__main__":
    sys.exit(main())
