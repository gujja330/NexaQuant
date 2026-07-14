"""NexaQuant top-level package.

Established by ENG001. Currently exposes only `nexaquant.lib` — shared utility
primitives usable by future engineering phases (ENG002+) to eliminate the
duplicated helpers audited across `india/`, `core/`, `strategy/`, `research/`.

ENG001 policy:
- This package is ADDITIVE. It does NOT rewire any existing caller.
- Migration of production files to use this package is deferred to later phases
  where each migration is preregistered, tested, and MON001-fingerprint-verified.
- Sealed production and lab modules must NOT import from this package until
  operator authorization is granted per the MON001 change-management procedure.
"""

__version__ = "0.1.0-eng001"
