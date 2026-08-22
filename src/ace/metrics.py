import threading


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()

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


# Singleton registry
registry = MetricsRegistry()
