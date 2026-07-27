"""Daily runner for Repository Intelligence scanner."""
from __future__ import annotations

import json, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.repository_intelligence.scanner import scan_repository


def main() -> int:
    out = scan_repository(_ROOT)
    p = _ROOT / "reports" / "repository_intelligence.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[repo_intel] findings={out['n_findings']} by_category={out['by_category']} -> {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
