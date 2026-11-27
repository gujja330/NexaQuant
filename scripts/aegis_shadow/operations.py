"""Market-scoped operational options and bounded worker retries."""
from pathlib import Path
from subprocess import TimeoutExpired
from time import sleep

from scripts.aegis_local_state import contained
from scripts.aegis_shadow.pipeline import _json


def worker_retry(root, market):
    path = contained(root, Path(".aegis-local/unified/inputs") / market / "operations.json")
    if not path.is_file():
        return 1, 0
    data = _json(path)
    if not isinstance(data, dict) or set(data) != {"market", "research_timeout_attempts", "retry_backoff_seconds"}:
        raise ValueError("invalid operational settings schema")
    attempts, delay = data["research_timeout_attempts"], data["retry_backoff_seconds"]
    if (data["market"] != market or type(attempts) is not int or not 1 <= attempts <= 3
            or type(delay) is not int or not 0 <= delay <= 30):
        raise ValueError("invalid market, retry attempts, or backoff")
    return attempts, delay


def run_with_timeout_retry(operation, attempts, delay, *, on_timeout):
    for number in range(1, attempts + 1):
        try:
            return operation(number)
        except TimeoutExpired:
            on_timeout(number)
            if number == attempts:
                raise
            sleep(delay * number)
