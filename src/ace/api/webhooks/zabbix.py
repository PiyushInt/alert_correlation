import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ace.api.deps import get_db
from ace.ingestion.adapters.zabbix import ZabbixAdapter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("")
async def receive_zabbix_webhook(
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
) -> Any:
    """
    Receive alerts from Zabbix.
    The payload is expected to be a JSON object like {"value": "<escaped_json>"}.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Zabbix webhook JSON: {e}")
        return Response(status_code=400, content="Invalid JSON")

    try:
        adapter = ZabbixAdapter()
        normalised_alerts = adapter.normalize(payload, db)
    except ValueError as e:
        logger.error(f"Failed to normalize Zabbix webhook: {e}")
        return Response(status_code=422, content="Invalid payload format")

    from datetime import UTC, datetime

    from ace.bypass.health import evaluate_state
    from ace.bypass.router import route_alert
    from ace.db.models.alerts import Alert

    for n_alert in normalised_alerts:
        try:
            # 1. Persist to Postgres
            db_alert = Alert(
                source_tool=n_alert.source_tool,
                external_id=n_alert.external_id,
                severity=n_alert.severity,
                component_id=n_alert.component_id,
                component_unresolved=n_alert.component_unresolved,
                labels=n_alert.labels,
                annotations=n_alert.annotations,
                raw_payload=n_alert.raw_payload,
                fingerprint=n_alert.external_id,
                status=n_alert.status,
                environment=n_alert.environment,
                tenant=n_alert.tenant,
                starts_at=n_alert.starts_at,
                ends_at=n_alert.ends_at,
                received_at=datetime.now(UTC),
            )
            db.add(db_alert)
            db.commit()
            db.refresh(db_alert)

            n_alert.id = db_alert.id

            # 2. Evaluate state
            state, _ = evaluate_state()

            # 3. Route
            route_alert(n_alert, state)
        except Exception as e:
            logger.error(f"Failed to process Zabbix alert {n_alert.external_id}: {e}")

    return {"status": "accepted"}
