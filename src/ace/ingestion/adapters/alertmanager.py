from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ace.ingestion.adapters.base import BaseAdapter
from ace.ingestion.models import Candidate, NormalisedAlert


class AlertmanagerAdapter(BaseAdapter):
    """
    Adapter for Prometheus Alertmanager v4 webhooks.
    """

    SEVERITY_MAP = {
        "critical": "critical",
        "page": "critical",  # Sometimes used in prometheus
        "high": "high",
        "warning": "medium",
        "low": "low",
        "info": "info",
    }

    def extract_identifiers(self, alert_data: dict[str, Any]) -> list[Candidate]:
        candidates = []
        labels = alert_data.get("labels", {})

        # Priority order for Prometheus / Blackbox
        # 1. Mountpoint (most specific for filesystems)
        if "mountpoint" in labels:
            candidates.append(Candidate(value=labels["mountpoint"], field_name="mountpoint"))

        # 2. Target instance for blackbox probes
        if labels.get("job") == "blackbox" or "Probe" in labels.get("alertname", ""):
            if "instance" in labels:
                candidates.append(Candidate(value=labels["instance"], field_name="instance"))

        # 3. Component label (if explicitly provided)
        if "component" in labels:
            candidates.append(Candidate(value=labels["component"], field_name="component"))

        # 4. Instance, pod, service, job (decreasing specificity)
        if "instance" in labels and labels.get("job") != "blackbox":
            candidates.append(Candidate(value=labels["instance"], field_name="instance"))
        if "pod" in labels:
            candidates.append(Candidate(value=labels["pod"], field_name="pod"))
        if "service" in labels:
            candidates.append(Candidate(value=labels["service"], field_name="service"))
        if "job" in labels:
            candidates.append(Candidate(value=labels["job"], field_name="job"))
        if "alertname" in labels:
            candidates.append(Candidate(value=labels["alertname"], field_name="alertname"))

        return candidates

    def normalize(self, payload: Any, session: Session) -> list[NormalisedAlert]:
        alerts_list = payload.get("alerts", [])
        normalised_alerts = []
        from ace.ingestion.resolver import Resolver

        resolver = Resolver(session)

        for alert_data in alerts_list:
            labels = alert_data.get("labels", {})
            annotations = alert_data.get("annotations", {})

            # Extract basic fields
            external_id = alert_data.get("fingerprint", "")
            raw_severity = labels.get("severity", "unknown").lower()
            if raw_severity not in self.SEVERITY_MAP:
                import logging

                logging.getLogger(__name__).warning(
                    f"Unknown severity '{raw_severity}' mapped to medium. "
                    f"Alert external_id: {external_id}"
                )
            severity = self.SEVERITY_MAP.get(raw_severity, "medium")

            status_raw = alert_data.get("status", "firing")
            status = "resolved" if status_raw == "resolved" else "firing"

            # Parse timestamps
            try:
                starts_at = datetime.fromisoformat(
                    alert_data.get("startsAt").replace("Z", "+00:00")
                )
            except Exception:
                starts_at = datetime.now()

            ends_at_raw = alert_data.get("endsAt")
            ends_at = None
            if ends_at_raw and not ends_at_raw.startswith("0001-01-01"):
                try:
                    ends_at = datetime.fromisoformat(ends_at_raw.replace("Z", "+00:00"))
                except Exception:
                    pass

            source_tool = "prometheus"
            if labels.get("job") == "blackbox" or "Probe" in labels.get("alertname", ""):
                source_tool = "blackbox"

            candidates = self.extract_identifiers(alert_data)
            component_id, component_unresolved = resolver.resolve(candidates, source_tool)

            if component_unresolved:
                import logging

                alias_to_lookup = candidates[0].value if candidates else "none"

                logging.getLogger(__name__).warning(
                    f"Component unresolved for alert {external_id} "
                    f"(alias attempted: {alias_to_lookup})"
                )

            normalised_alerts.append(
                NormalisedAlert(
                    source_tool=source_tool,
                    external_id=external_id,
                    severity=severity,
                    component_id=component_id,
                    component_unresolved=component_unresolved,
                    labels=labels,
                    annotations=annotations,
                    raw_payload=alert_data,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    status=status,
                    environment="production",  # Could be derived from labels if present
                    tenant="default",
                )
            )

        return normalised_alerts
