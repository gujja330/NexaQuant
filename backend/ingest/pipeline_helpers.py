"""Sprint K Part 29 · pipeline speedup helpers · Lever A + Lever B.

Two composable helpers any per-ticker ingest module can use to hit the
Part 29 acceptance target (full daily run ≤ 20 minutes vs current ~60):

  Lever A · staleness_skip(path, max_age_hours)
    True when the produced artifact is fresher than the threshold. Callers
    skip the fetch entirely on hit. Cuts ~40% of tickers on a typical day.

  Lever B · parallel_map(fn, tickers, max_workers=6, rate_per_sec=10)
    ThreadPoolExecutor with a token-bucket rate limiter · exponential
    backoff on rate-limit exceptions · deterministic (returns list in the
    ORDER of tickers, not completion order).

Design constraints from § 29.4:
  · Do NOT change what data is fetched (same fields · same universe)
  · Do NOT change R1/R2 or downstream engine logic
  · Retain byte-for-byte deterministic outputs across serial vs parallel

Consumers (individual ingest modules) migrate one at a time · this
library is the shared substrate.
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock


# ─────────────────────────────────────────────────────────────
# Lever A · staleness-aware skip
# ─────────────────────────────────────────────────────────────

def staleness_skip(path: Path, max_age_hours: float = 20.0) -> bool:
    """Return True when `path` exists and its mtime is younger than
    max_age_hours (i.e., no refetch needed). Default 20h so an intraday
    rerun after midnight IST still refreshes (24h - overnight buffer).

    Callers use as:
        if staleness_skip(p, 20): continue    # skip this ticker
        ... fetch and write p ...
    """
    if not path.exists():
        return False
    try:
        age_h = (time.time() - path.stat().st_mtime) / 3600.0
        return age_h < max_age_hours
    except Exception:
        return False


def orchestrator_step_fresh(step_produces: list, max_age_hours: float = 20.0) -> bool:
    """Meta-level staleness check for the daily orchestrator. Returns True
    when EVERY output artifact of a step is fresh · orchestrator can then
    skip the entire subprocess launch.

    Called by scripts/aegis_daily_v2.py + usa/scripts/usa_daily.py:
        if orchestrator_step_fresh(step['produces'], 20): SKIP
    """
    if not step_produces: return False
    for rel in step_produces:
        p = Path(rel)
        if not p.exists(): return False
        try:
            age_h = (time.time() - p.stat().st_mtime) / 3600.0
            if age_h >= max_age_hours:
                return False
        except Exception:
            return False
    return True


# ─────────────────────────────────────────────────────────────
# Lever B · ThreadPool with rate limit + backoff
# ─────────────────────────────────────────────────────────────

class TokenBucket:
    """Simple thread-safe token-bucket rate limiter.

    take() blocks until a token is available. Used to cap yfinance requests
    at ~10/sec (yfinance's undocumented soft limit before HTTP 429)."""

    def __init__(self, rate_per_sec: float, burst: int | None = None):
        self.rate = float(rate_per_sec)
        self.capacity = int(burst or max(1, int(rate_per_sec)))
        self.tokens = float(self.capacity)
        self.last = time.monotonic()
        self._lock = Lock()

    def take(self, n: int = 1) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self.last
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last = now
                if self.tokens >= n:
                    self.tokens -= n
                    return
                need = (n - self.tokens) / self.rate
            time.sleep(max(0.001, need))


def parallel_map(fn, items, *, max_workers: int = 6,
                       rate_per_sec: float = 10.0, max_retries: int = 3,
                       progress_every: int = 50):
    """Deterministic parallel map with rate limit + exponential backoff.

    Args:
        fn:            takes one item → returns any value (or raises)
        items:         list of items (e.g., tickers)
        max_workers:   concurrent threads · default 6 (safe for yfinance)
        rate_per_sec:  token-bucket rate limit
        max_retries:   retry with exponential backoff on any Exception
        progress_every: log a heartbeat every N completions

    Returns:
        list of results in the ORDER of input items (None on final failure).
    """
    bucket = TokenBucket(rate_per_sec)

    def _worker(item):
        for attempt in range(max_retries):
            try:
                bucket.take()
                return fn(item)
            except Exception:
                if attempt == max_retries - 1:
                    return None
                # Exponential backoff with jitter
                delay = (2 ** attempt) * 0.5 + random.random() * 0.5
                time.sleep(delay)
        return None

    results = [None] * len(items)
    n_done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        # Submit preserving original index for deterministic ordering
        futures = {ex.submit(_worker, item): i for i, item in enumerate(items)}
        for fut in as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
            n_done += 1
            if progress_every > 0 and n_done % progress_every == 0:
                print(f"[parallel_map] {n_done}/{len(items)} done")
    return results


# ─────────────────────────────────────────────────────────────
# Composed helper · used by the "typical" per-ticker ingest loop
# ─────────────────────────────────────────────────────────────

def fetch_and_write(ticker: str, path_fn, fetch_fn, write_fn, *,
                          max_age_hours: float = 20.0) -> str:
    """Compose Lever A + fetch + write for one ticker. Returns status:
      "SKIP" · artifact fresh
      "OK"   · fetched + wrote
      "FAIL" · fetch/write raised
    Intended for use inside a parallel_map() call to keep worker functions
    tiny."""
    try:
        p = path_fn(ticker)
        if staleness_skip(p, max_age_hours):
            return "SKIP"
        data = fetch_fn(ticker)
        if data is None: return "FAIL"
        write_fn(ticker, data)
        return "OK"
    except Exception:
        return "FAIL"
