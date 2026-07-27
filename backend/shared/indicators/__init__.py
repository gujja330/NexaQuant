"""backend.shared.indicators — Constitution Article 30 canonical indicator library.

Layer 0 (shared primitives) · one canonical implementation per computation.
Local reimplementation of any indicator here is FORBIDDEN by Article 30.
CI enforcement: validation/indicator_validation/no_local_reimplementation.py

Wave 5 Phase 9+ populates the full 16-primitive set. Currently seeded.

Note on domain naming: Constitution filesystem convention uses `NN_domain/`
for docs/ordering, but Python packages cannot start with a digit. Actual
Python packages use the domain name only (e.g. `backend.recommendation.capital_rotation`,
`backend.shared.indicators`). The layer number is tracked in the domain's
owner doc at `docs/domains/`.
"""
from __future__ import annotations

__version__ = "0.1.0"
__constitution__ = "Article 30"
__layer__ = "10_shared"
