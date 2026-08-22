from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ace.db.repositories.components import ComponentRepository
from ace.ingestion.adapters.base import BaseAdapter
from ace.ingestion.models import NormalisedAlert


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

    def normalize(self, payload: Any, session: Session) -> list[NormalisedAlert]:
        alerts_list = payload.get("alerts", [])
        normalised_alerts = []
        component_repo = ComponentRepository(session)

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

            # Component resolution v1: EXACT and ALIAS lookup ONLY
            # Usually the instance or job is a good proxy for component alias
            alias_to_lookup = labels.get("instance") or labels.get("job") or labels.get("alertname")
            component_id = None
            component_unresolved = True

            if alias_to_lookup:
                # 1. Exact canonical name match
                component = component_repo.get_by_name(alias_to_lookup)
                if component:
                    component_id = component.id
                    component_unresolved = False
                else:
                    # 2. Alias match
                    component = component_repo.get_by_alias(alias_to_lookup, "prometheus")
                    if component:
                        component_id = component.id
                        component_unresolved = False

            if component_unresolved:
                import logging

                logging.getLogger(__name__).warning(
                    f"Component unresolved for alert {external_id} "
                    f"(alias attempted: {alias_to_lookup})"
                )

            normalised_alerts.append(
                NormalisedAlert(
                    source_tool="prometheus",
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
