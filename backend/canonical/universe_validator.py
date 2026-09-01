"""Universe bounds validator · CEO 2026-09-01 (Section 2).

Enforces the per-market production universe constraint declared in
`configs/aegis_universes.yaml`. USA must be S&P 500 · India retains its
current bounds. Silent widening beyond the declared range is a contract
violation that fails the reconciler.

Public entry points:
    validate(root, market) -> ValidationResult
    load_config(root)      -> dict
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    market: str
    ok: bool
    verdict: str                            # OK · FAIL · WARN
    n_tickers: int
    active_label: str
    detail: str
    violations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "market": self.market, "ok": self.ok, "verdict": self.verdict,
            "n_tickers": self.n_tickers, "active_label": self.active_label,
            "detail": self.detail, "violations": self.violations,
        }


def _load_yaml(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_config(root: Path) -> dict:
    cfg_p = root / "configs" / "aegis_universes.yaml"
    if not cfg_p.exists():
        return {}
    return _load_yaml(cfg_p)


def validate(root: Path, market: str) -> ValidationResult:
    cfg = load_config(root)
    m_cfg = (cfg.get("markets", {}) or {}).get(market.lower(), {})
    if not m_cfg:
        return ValidationResult(
            market=market, ok=False, verdict="FAIL",
            n_tickers=0, active_label="",
            detail=f"no config entry for market={market}",
            violations=["no_config"],
        )

    src_file = m_cfg.get("source_file")
    if not src_file:
        # No static source · policy: pass with WARN
        return ValidationResult(
            market=market, ok=True, verdict="WARN",
            n_tickers=0, active_label=m_cfg.get("active_universe_label", ""),
            detail=f"no static source file · derived universe · policy=WARN",
            violations=[],
        )

    src_p = root / src_file
    if not src_p.exists():
        return ValidationResult(
            market=market, ok=False, verdict="FAIL",
            n_tickers=0, active_label="",
            detail=f"source file missing: {src_file}",
            violations=["source_missing"],
        )

    data = json.loads(src_p.read_text(encoding="utf-8"))
    tickers = data.get("tickers") or []
    n = len(tickers)
    active_label = str(data.get("active_universe") or "").lower()

    lo = int(m_cfg.get("n_tickers_min", 0))
    hi = int(m_cfg.get("n_tickers_max", 10 ** 9))
    expected_label = str(m_cfg.get("active_universe_label", "")).lower()
    disallowed = [str(x).lower() for x in (m_cfg.get("disallowed_labels") or [])]

    violations: list[str] = []
    if expected_label and active_label != expected_label:
        violations.append(f"label_mismatch: expected={expected_label} got={active_label}")
    if active_label in disallowed:
        violations.append(f"disallowed_label: {active_label}")
    if n < lo:
        violations.append(f"n_tickers_below_min: {n} < {lo}")
    if n > hi:
        violations.append(f"n_tickers_above_max: {n} > {hi}")

    ok = not violations
    return ValidationResult(
        market=market, ok=ok,
        verdict="OK" if ok else "FAIL",
        n_tickers=n, active_label=active_label,
        detail=f"n={n} label={active_label} range=[{lo},{hi}] expected={expected_label}",
        violations=violations,
    )


if __name__ == "__main__":
    import sys
    _ROOT = Path(__file__).resolve().parents[2]
    for m in ("usa", "india"):
        r = validate(_ROOT, m)
        print(json.dumps(r.as_dict(), indent=2, ensure_ascii=False))
