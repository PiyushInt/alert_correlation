import logging
import threading

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()
        self._current_state = "OK"

        self.counters: dict[str, Counter] = {
            "ace_alerts_received_total": Counter(
                "ace_alerts_received_total", "Total alerts received"
            ),
            "worker_received": Counter(
                "ace_worker_alerts_received_total", "Alerts pulled by worker"
            ),
            "worker_forwarded": Counter(
                "ace_worker_alerts_forwarded_total", "Alerts published to clean stream"
            ),
            "worker_dead_lettered": Counter("ace_worker_dead_letter_total", "Failed messages"),
            "ace_incidents_created_total": Counter(
                "ace_incidents_created_total", "Total incidents opened"
            ),
            "ace_incident_alerts_merged_total": Counter(
                "ace_incident_alerts_merged_total", "Total alerts merged into incidents"
            ),
            "ace_containment_refused_total": Counter(
                "ace_containment_refused_total",
                "Total times containment refused a merge",
                labelnames=["reason"],
            ),
            "ace_incidents_split_total": Counter(
                "ace_incidents_split_total",
                "Total number of incidents partitioned via split operation",
            ),
            "ace_incident_feedback_total": Counter(
                "ace_incident_feedback_total",
                "Total operator feedback submissions",
                labelnames=["verdict"],
            ),
            "ace_signal_disagreement_total": Counter(
                "ace_signal_disagreement_total",
                "Feedback instances marking 'wrong_group', tracked by the signal "
                "that formed the grouping",
                labelnames=["signal_name"],
            ),
        }

        self.histograms: dict[str, Histogram] = {
            "ace_incident_notification_latency_seconds": Histogram(
                "ace_incident_notification_latency_seconds",
                "Latency from alert receipt to first incident notification",
                buckets=(5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, float("inf")),
            )
        }

    def inc_counter(self, name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
        if name in self.counters:
            if labels:
                self.counters[name].labels(**labels).inc(value)
            else:
                self.counters[name].inc(value)
        else:
            with self._lock:
                if name not in self._counters:
                    self._counters[name] = 0
                self._counters[name] += value

    def observe_histogram(self, name: str, value: float) -> None:
        if name in self.histograms:
            self.histograms[name].observe(value)
        else:
            logger.warning(f"Histogram {name} not registered")

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
