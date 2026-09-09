"""USA ACQUISITION PROFILE · measure before optimising.

USA acquisition takes ~313s of a ~470s daily run - two thirds of the
wall clock. That is worth understanding, and worth NOT guessing about:
"it must be the network" is a hypothesis, and a serial loop over 520
tickers has at least four candidate costs (network wait, retry backoff,
per-request throttle, parquet write).

This module measures each on a SAMPLE and extrapolates, so a later change
can be aimed at the dominant term instead of the obvious one.

IT CHANGES NOTHING
------------------
No behaviour is altered here. The profiler fetches its own sample into a
temporary directory and never writes to data/raw. Optimisation is a
separate decision, taken after the number is known.

WHY A SAMPLE AND NOT THE FULL RUN
----------------------------------
Profiling all 520 tickers costs another full acquisition. A sample of ~20
measures per-ticker cost to within a few percent, and the extrapolation
is reported as an estimate with its sample size attached rather than as a
measured total.
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.observability.acquisition_profile.v1"

# Read from the script being profiled rather than restated here, so the
# profile cannot silently describe different settings than production.
DEFAULTS = {"history_period": "5y", "inter_request_sleep_sec": 0.05,
            "backoff_sec": 1.5, "max_attempts": 3}


def _script_constants(root: Path) -> dict:
    out = dict(DEFAULTS)
    p = root / "usa" / "scripts" / "refresh_market_data.py"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        for key, name in (("history_period", "HISTORY_PERIOD"),
                          ("inter_request_sleep_sec", "INTER_REQUEST_SLEEP_SEC"),
                          ("backoff_sec", "BACKOFF_SEC"),
                          ("max_attempts", "MAX_ATTEMPTS")):
            if s.startswith(name + " ="):
                val = s.split("=", 1)[1].split("#")[0].strip().strip('"\'')
                try:
                    out[key] = float(val) if "." in val else (
                        int(val) if val.isdigit() else val)
                except Exception:
                    out[key] = val
    return out


def _universe(root: Path) -> list:
    """Ticker SYMBOLS · the file stores dicts, not strings.

    Reading the list raw handed yfinance a dict per call, which failed
    every fetch and reported 0.000s network time with 60 retries - a
    profile that looked like "the network is free" when nothing had been
    fetched at all. A measurement that cannot fail loudly is worse than
    no measurement.
    """
    p = root / "usa" / "reports" / "universe.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for t in (d.get("tickers") or []):
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, dict):
            sym = t.get("symbol") or t.get("ticker")
            if sym:
                out.append(str(sym))
    return out


def profile(root: Path, sample: int = 20, seed: int = 20260909) -> dict:
    import random
    import tempfile

    consts = _script_constants(root)
    uni = _universe(root)
    if not uni:
        return {"error": "USA universe not resolvable"}

    rng = random.Random(seed)
    picks = rng.sample(uni, min(sample, len(uni)))

    net, write, retries, failures = [], [], 0, []
    tmp = Path(tempfile.mkdtemp(prefix="aegis_prof_"))
    try:
        import pandas as pd
        import yfinance as yf
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}

    for sym in picks:
        t0 = time.time()
        df = None
        for attempt in range(1, int(consts.get("max_attempts", 3)) + 1):
            try:
                df = yf.Ticker(sym).history(
                    period=str(consts.get("history_period", "5y")),
                    auto_adjust=True)
                if df is not None and not df.empty:
                    break
                retries += 1
            except Exception:
                retries += 1
                df = None
        net.append(time.time() - t0)
        if df is None or df.empty:
            failures.append(sym)
            continue
        t1 = time.time()
        try:
            df.to_parquet(tmp / ("%s.parquet" % sym.replace("^", "_IDX_")))
        except Exception:
            pass
        write.append(time.time() - t1)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    n_uni = len(uni)
    sleep_s = float(consts.get("inter_request_sleep_sec", 0.05))
    med_net = statistics.median(net) if net else 0.0
    med_write = statistics.median(write) if write else 0.0

    est_net = med_net * n_uni
    est_write = med_write * n_uni
    est_sleep = sleep_s * n_uni
    est_total = est_net + est_write + est_sleep

    def share(x):
        return round(x / est_total * 100, 1) if est_total else 0.0

    if not net or med_net <= 0.0 or len(failures) == len(picks):
        return {"schema_version": SCHEMA_VERSION,
                "error": "every sampled fetch failed (%d/%d) · profile is "
                         "meaningless and is not reported as a result"
                         % (len(failures), len(picks)),
                "failures": [str(x) for x in failures][:6],
                "retries_in_sample": retries}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": "usa",
        "constants": consts,
        "universe_size": n_uni,
        "sample_size": len(picks),
        "measured": {
            "network_median_s": round(med_net, 3),
            "network_p90_s": round(sorted(net)[int(0.9 * (len(net) - 1))], 3)
                             if net else 0.0,
            "network_total_sample_s": round(sum(net), 1),
            "write_median_s": round(med_write, 4),
            "retries_in_sample": retries,
            "failures_in_sample": failures,
        },
        "extrapolated_full_run_s": {
            "network_wait": round(est_net, 1),
            "parquet_write": round(est_write, 1),
            "inter_request_sleep": round(est_sleep, 1),
            "total_estimate": round(est_total, 1),
        },
        "share_pct": {
            "network_wait": share(est_net),
            "parquet_write": share(est_write),
            "inter_request_sleep": share(est_sleep),
        },
        "structure": {
            "concurrency": "SERIAL · one ticker at a time",
            "cache": ("none · every run re-downloads the full %s history "
                      "for every ticker regardless of what is already on "
                      "disk" % consts.get("history_period")),
            "repeated_download": True,
        },
        "note": ("estimate from a %d-ticker sample · reported as an estimate, "
                 "not a measured total · no behaviour was changed and nothing "
                 "was written to data/raw" % len(picks)),
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "context" / "acquisition_profile_usa.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def render(rep: dict) -> str:
    if rep.get("error"):
        return "acquisition profile · ERROR · %s" % rep["error"]
    m, e, s = rep["measured"], rep["extrapolated_full_run_s"], rep["share_pct"]
    L = ["═" * 68, "USA ACQUISITION PROFILE  ·  %d tickers  ·  sample %d"
         % (rep["universe_size"], rep["sample_size"]), "═" * 68,
         "  per ticker   network median %.3fs · p90 %.3fs · write %.4fs"
         % (m["network_median_s"], m["network_p90_s"], m["write_median_s"]),
         "  retries in sample: %d · failures: %s"
         % (m["retries_in_sample"], m["failures_in_sample"] or "none"), "",
         "  ESTIMATED FULL RUN"]
    for k in ("network_wait", "parquet_write", "inter_request_sleep"):
        L.append("    %-22s %7.1fs   %5.1f%%" % (k, e[k], s[k]))
    L.append("    %-22s %7.1fs" % ("total estimate", e["total_estimate"]))
    L += ["", "  STRUCTURE",
          "    concurrency : %s" % rep["structure"]["concurrency"],
          "    cache       : %s" % rep["structure"]["cache"], "═" * 68]
    return "\n".join(L)


def load(root: Path) -> Optional[dict]:
    p = root / "reports" / "context" / "acquisition_profile_usa.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="USA acquisition profile")
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[2]
    rep = profile(root, sample=a.sample)
    emit(root, rep)
    print(render(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
