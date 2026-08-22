import threading


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()
        self._current_state = "OK"

    def inc_counter(self, name: str, value: int = 1) -> None:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = 0
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def get_metrics(self) -> dict[str, float]:
        with self._lock:
            metrics = {**self._counters, **self._gauges}
            return metrics

    def record_state_transition(self, new_state: str, reason: str) -> None:
        import logging

        logger = logging.getLogger(__name__)
        with self._lock:
            if self._current_state != new_state:
                logger.warning(
                    f"State transition: {self._current_state} -> {new_state} (Reason: {reason})"
                )
                self._current_state = new_state
                # Update a gauge for state if we want to monitor it
                state_val = {"OK": 0, "DEGRADED": 1, "BYPASS": 2}.get(new_state, 0)
                self._gauges["system_state"] = state_val


# Singleton registry
registry = MetricsRegistry()
