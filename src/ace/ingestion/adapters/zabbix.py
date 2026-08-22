import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ace.ingestion.adapters.base import BaseAdapter
from ace.ingestion.models import Candidate, NormalisedAlert
from ace.ingestion.resolver import Resolver

logger = logging.getLogger(__name__)


class ZabbixAdapter(BaseAdapter):
    """
    Adapter for Zabbix webhooks.
    """

    SEVERITY_MAP = {
        "not classified": "info",
        "information": "info",
        "warning": "low",
        "average": "medium",
        "high": "high",
        "disaster": "critical",
    }

    def extract_identifiers(self, alert_data: dict[str, Any]) -> list[Candidate]:
        candidates = []
        item_key = alert_data.get("item_key", "")
        host = alert_data.get("host", "")

        # 1. Parse item_key for brackets, e.g. vfs.fs.size[/mnt/valkey-data,pused]
        if "[" in item_key and "]" in item_key:
            try:
                bracket_content = item_key.split("[")[1].split("]")[0]
                # bracket_content might be /mnt/valkey-data,pused -> we want the first part usually,
                # but to be safe and match Prometheus, the filesystem path is the first argument
                args = bracket_content.split(",")
                if args and args[0]:
                    candidates.append(Candidate(value=args[0].strip(), field_name="item_key_arg"))
            except Exception as e:
                logger.debug(f"Failed to parse Zabbix item_key {item_key}: {e}")

        # 2. Host
        if host:
            candidates.append(Candidate(value=host, field_name="host"))

        # 3. Item key (the full key)
        if item_key:
            candidates.append(Candidate(value=item_key, field_name="item_key"))

        return candidates

    def normalize(self, payload: Any, session: Session) -> list[NormalisedAlert]:
        if not isinstance(payload, dict) or "value" not in payload:
            raise ValueError("Expected Zabbix payload to contain 'value' key")

        try:
            alert_data = json.loads(payload["value"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Zabbix value is not valid JSON: {e}") from e

        resolver = Resolver(session)

        # Zabbix doesn't send a unique fingerprint per event typically,
        # so we'll generate one based on trigger_name and host and time if we don't have event_id.
        # But wait, it doesn't send an event_id in the mock payload. Let's just generate a UUID.
        # Ideally, we hash something. Let's use uuid4 for now as external_id.
        external_id = str(uuid.uuid4())[:16]

        raw_severity = alert_data.get("severity", "unknown").lower()
        if raw_severity not in self.SEVERITY_MAP:
            logger.warning(
                f"Unknown severity '{raw_severity}' mapped to medium. "
                f"Alert external_id: {external_id}"
            )
        severity = self.SEVERITY_MAP.get(raw_severity, "medium")

        # Parse timestamps (e.g., 2026.08.21T06:09:04Z)
        event_time = alert_data.get("event_time", "")
        if event_time:
            # Replace dots in date part with hyphens
            try:
                # 2026.08.21T06:09:04Z -> 2026-08-21T06:09:04Z
                if "T" in event_time:
                    date_part, time_part = event_time.split("T")
                    date_part = date_part.replace(".", "-")
                    event_time = f"{date_part}T{time_part}"
                starts_at = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            except Exception:
                starts_at = datetime.now()
        else:
            starts_at = datetime.now()

        # Is it resolved? (If Zabbix sends recovery, but mock doesn't show status. Assume firing).
        # We don't have a status in the mock payload, so default to firing.
        status = "firing"

        candidates = self.extract_identifiers(alert_data)
        component_id, component_unresolved = resolver.resolve(candidates, "zabbix")

        if component_unresolved:
            alias_to_lookup = candidates[0].value if candidates else "none"
            logger.warning(
                f"Component unresolved for alert {external_id} (alias attempted: {alias_to_lookup})"
            )

        alert = NormalisedAlert(
            source_tool="zabbix",
            external_id=external_id,
            severity=severity,
            component_id=component_id,
            component_unresolved=component_unresolved,
            labels={
                "host": alert_data.get("host", ""),
                "item_key": alert_data.get("item_key", ""),
                "severity": alert_data.get("severity", ""),
            },
            annotations={
                "summary": alert_data.get("trigger_name", ""),
                "value": alert_data.get("item_value", ""),
            },
            raw_payload=alert_data,
            starts_at=starts_at,
            ends_at=None,
            status=status,
            environment="production",
            tenant="default",
        )

        return [alert]
