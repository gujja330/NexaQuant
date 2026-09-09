"""AEGIS RUN CONTRACT · fail-closed data & decision lineage.

    SOURCE -> DATA -> FEATURES -> SCORE -> DECISION -> LIFECYCLE -> DELIVERY

Every arrow is a contract. A downstream stage REFUSES to run when its
upstream contract is invalid. There is no "use the latest file" path.
"""
from backend.pipeline.contract.run_context import RunContext, new_run_id
