"""NexaQuant operational platform (OPS001).

Wraps existing systems (recommendation engine, MON001, Telegram, broker) into a
configurable pipeline with retry, timeout, notification bus, and observability.
OPS001-B adds daemon lifecycle, structured logs with rotation, PID locking,
process monitoring, cron-slot scheduling, and interrupted-pipeline recovery.

Never modifies strategy behaviour. Never modifies MON001 sealed core files.
Additive only.
"""

__version__ = "0.1.0-ops001b"
