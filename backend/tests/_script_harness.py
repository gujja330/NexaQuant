"""Supply pytest fixtures when a test file is run as a bare script.

CEO 2026-11-07.

WHY THIS EXISTS
---------------
Eleven files under backend/tests/ are run BOTH ways:

    .github/workflows/aegis-ci.yml   python backend/tests/test_sprintN.py
    local / full regression          python -m pytest ...

The write-isolation work (14ebede10) gave several of their tests an
`_OUT_ROOT` fixture, because those tests execute real production engines
as subprocesses and, without it, every regression run rewrote live
artifacts - ensemble.json, market_intelligence.json,
model_registry.jsonl and the rest.

The fixture is correct. What nobody updated was each file's own
`main()` loop, which calls `t()` with no arguments. Under pytest the
fixture is injected; as a script it is not, so every such test died
with

    TypeError: ... missing 1 required positional argument: '_OUT_ROOT'

and AEGIS CI has been red on it since that commit. Measured: 10 of the
18 bare-script files in aegis-ci.yml are affected, so fixing one step
only reveals the next.

WHAT THIS DOES
--------------
Resolves each test's own signature and supplies the same objects pytest
would. Signature-driven on purpose: a new isolated test gets its root
automatically instead of adding an eleventh place to remember.

It is NOT a pytest replacement and must never be used from a pytest
run - pytest's own fixtures are always better. It exists only so the
script path behaves like the pytest path.
"""
from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional


def make_out_root(prefix: str = "aegis_out_") -> Path:
    """A disposable report root, shaped like the real one.

    Mirrors the `_OUT_ROOT` fixture: subprocess engines resolve their own
    output paths and cannot take a Python argument, so the root reaches
    them through AEGIS_OUT_ROOT. Reads still come from the real
    repository, which is the point of those tests.
    """
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    for sub in ("reports", "usa/reports", "features"):
        (tmp / sub).mkdir(parents=True, exist_ok=True)
    return tmp


class _NullCapsys:
    """Stand-in for pytest's capsys when running as a script.

    Returns empty streams rather than pretending to capture. A test that
    asserts on captured output will fail honestly instead of passing on
    fabricated text - silently satisfying an assertion is worse than
    not running it.
    """

    class _Captured:
        out = ""
        err = ""

        def __iter__(self):
            return iter((self.out, self.err))

    def readouterr(self):
        return self._Captured()


def call_test(t: Callable, out_root: Optional[Path] = None) -> Any:
    """Invoke a test function, supplying whatever its signature asks for.

    Unknown parameters are left to fail loudly: guessing a fixture is
    how a test passes without testing anything.
    """
    params = inspect.signature(t).parameters
    if not params:
        return t()
    kwargs: dict = {}
    for name in params:
        if name in ("_OUT_ROOT", "out_root"):
            kwargs[name] = out_root if out_root is not None else make_out_root()
        elif name in ("tmp_path", "tmpdir"):
            kwargs[name] = Path(tempfile.mkdtemp(prefix="aegis_tmp_"))
        elif name == "capsys":
            kwargs[name] = _NullCapsys()
        else:
            raise TypeError(
                "%s needs fixture %r, which the script harness does not "
                "provide. Add it to backend/tests/_script_harness.call_test "
                "or run this file under pytest." % (t.__name__, name))
    return t(**kwargs)
