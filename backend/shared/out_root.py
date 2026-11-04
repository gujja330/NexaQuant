"""Where a production engine's report writes land.

CEO 2026-11-04 · §E / §2.

WHY
---
Eleven test files execute production engines against the live repository
through `subprocess.run([...run.py], cwd=ROOT)`. Each engine resolves
its output paths from its own module location:

    _ROOT = Path(__file__).resolve().parents[2]
    OUT_ENSEMBLE = _ROOT / "reports" / "ensemble.json"

So every regression run rewrote real operational artifacts. Identified
by audit: `ensemble.json`, `model_factory.json`, `model_metrics.json`
and `model_registry.jsonl` from test_sprint27;
`market_intelligence.json` from test_sprint2; plus
`recommendations_v3*`, `risk_report`, `sized_positions`, `portfolio_*`,
`selected_features` and five learning artifacts from the rest.

A suite that mutates the production data it exists to validate cannot be
trusted to validate it. And it is not hypothetical: a test rewriting
`market_intelligence.json` mid-run is the most likely cause of
`test_no_critical_context_series_is_stale[india]` failing in the full
suite while passing alone - that file is in the INTERMARKET CRITICAL
series list.

HOW
---
A subprocess cannot be handed a Python argument, so the root arrives
through the environment. Production never sets it and therefore never
moves. Tests set it to a tmp_path and the engine writes there, while
still READING the real substrate - which is the point of those tests.

The alternative - restoring live files afterwards - is explicitly not
what this does. Restoration leaves a window where the live file is
wrong, loses the original on a crash, and cannot work in parallel.
"""
from __future__ import annotations

import os
from pathlib import Path

#: General redirect. Set by tests only.
OUT_ROOT_ENV = "AEGIS_OUT_ROOT"

#: The feature-store-specific variable that came first. Still honoured
#: so the earlier test_sprint25 fix keeps working, and so a caller can
#: redirect only the feature store if it ever needs to.
FEATURE_OUT_ROOT_ENV = "AEGIS_FEATURE_OUT_ROOT"


class OutRootEscape(ValueError):
    """A write resolved outside its permitted root."""


def resolved_out_root(repo_root: "Path | str") -> Path:
    """The directory this process should write reports into.

    Precedence: the specific variable, then the general one, then the
    repository root - so production, which sets neither, is unchanged.
    """
    for var in (FEATURE_OUT_ROOT_ENV, OUT_ROOT_ENV):
        v = os.environ.get(var)
        if v:
            return Path(v)
    return Path(repo_root)


def is_redirected() -> bool:
    return bool(os.environ.get(FEATURE_OUT_ROOT_ENV)
                or os.environ.get(OUT_ROOT_ENV))


def assert_within(root: "Path | str", candidate: "Path | str") -> Path:
    """Return `candidate` resolved, or raise if it escapes `root`.

    Guards the two ways a path leaves its root: an absolute path that
    simply ignores it, and `..` traversal. `resolve()` is applied to
    both sides first so a symlink cannot smuggle a write out either.
    """
    root_r = Path(root).resolve()
    cand_r = Path(candidate)
    cand_r = (root_r / cand_r).resolve() if not cand_r.is_absolute() \
        else cand_r.resolve()
    try:
        cand_r.relative_to(root_r)
    except ValueError:
        raise OutRootEscape(
            "%s resolves outside the permitted root %s" % (cand_r, root_r))
    return cand_r


def subprocess_env(out_root: "Path | str", base: "dict | None" = None) -> dict:
    """An environment that propagates the redirect to a child process."""
    env = dict(base if base is not None else os.environ)
    env[OUT_ROOT_ENV] = str(out_root)
    env[FEATURE_OUT_ROOT_ENV] = str(out_root)
    return env
