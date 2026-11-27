"""Process-local circuit breaker for private market-data workers."""
from dataclasses import dataclass, field
import json
from pathlib import Path
from time import monotonic, sleep

from scripts.aegis_local_state import contained
from scripts.aegis_shadow.pipeline import _json


class ProviderCircuitOpen(OSError):
    pass


def policy(root, market):
    path = contained(root, Path(".aegis-local/unified/inputs") / market / "provider_policy.json")
    default = {"market": market, "attempts": 1, "timeout_seconds": 15, "failure_threshold": 3,
               "cooldown_seconds": 60, "backoff_seconds": 1}
    data = _json(path) if path.is_file() else default
    bounds = {"attempts": (1, 3), "timeout_seconds": (1, 120), "failure_threshold": (1, 20),
              "cooldown_seconds": (1, 600), "backoff_seconds": (0, 30)}
    if (not isinstance(data, dict) or set(data) != set(default) or data["market"] != market or
            any(type(data[key]) is not int or not low <= data[key] <= high for key, (low, high) in bounds.items())):
        raise ValueError("invalid private price provider policy")
    return data


def failure_category(error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if type(error).__name__ == "YFRateLimitError" or status == 429:
        return "RATE_LIMITED"
    if isinstance(error, TimeoutError) or type(error).__name__ in {"Timeout", "ConnectTimeout", "ReadTimeout"}:
        return "NETWORK_TIMEOUT"
    if isinstance(error, ConnectionError) or type(error).__name__ == "ConnectionError" or (isinstance(status, int) and 500 <= status <= 599):
        return "TEMPORARY_PROVIDER_FAILURE"
    return None


@dataclass
class PriceCircuit:
    config: dict
    clock: object = monotonic
    pause: object = sleep
    consecutive: int = 0
    reopen_at: float = 0
    counts: dict = field(default_factory=dict)

    def call(self, method, *args, **kwargs):
        kwargs["timeout"] = min(kwargs.get("timeout") or self.config["timeout_seconds"], self.config["timeout_seconds"])
        for number in range(1, self.config["attempts"] + 1):
            if self.clock() < self.reopen_at:
                self.counts["CIRCUIT_OPEN"] = self.counts.get("CIRCUIT_OPEN", 0) + 1
                raise ProviderCircuitOpen("private Yahoo price circuit is cooling down")
            try:
                result = method(*args, **kwargs)
            except Exception as error:
                category = failure_category(error)
                if category is None:
                    raise
                self.counts[category] = self.counts.get(category, 0) + 1
                self.consecutive += 1
                if category == "RATE_LIMITED" or self.consecutive >= self.config["failure_threshold"]:
                    self.reopen_at = self.clock() + self.config["cooldown_seconds"]
                    raise
                if number == self.config["attempts"]:
                    raise
                self.pause(number * self.config["backoff_seconds"])
            else:
                if getattr(result, "empty", False):
                    self.counts["EMPTY_RESPONSE"] = self.counts.get("EMPTY_RESPONSE", 0) + 1
                else:
                    self.consecutive = 0
                return result


def install(config):
    import yfinance as yf

    circuit = PriceCircuit(config)
    download = yf.download
    history = yf.Ticker.history
    # Both adapters use blocking calls. Disable parallel yfinance download
    # workers so they cannot race the process-local circuit state.
    def bounded_download(*args, **kwargs):
        kwargs["threads"] = False
        if circuit.clock() < circuit.reopen_at:
            circuit.counts["CIRCUIT_OPEN"] = circuit.counts.get("CIRCUIT_OPEN", 0) + 1
            raise ProviderCircuitOpen("private Yahoo price circuit is cooling down")
        kwargs["timeout"] = min(kwargs.get("timeout") or config["timeout_seconds"], config["timeout_seconds"])
        # Batch download delegates per-symbol history to the wrapped method.
        # Counting the enclosing batch again masks consecutive symbol failures.
        return download(*args, **kwargs)

    def bounded_history(ticker, *args, **kwargs):
        return circuit.call(history, ticker, *args, **kwargs)

    yf.download = bounded_download
    yf.Ticker.history = bounded_history
    return circuit
