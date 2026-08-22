import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ace.api.dependencies import get_db
from ace.db.models.alerts import Alert
from ace.db.models.components import Component, ComponentAlias
from ace.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "alertmanager"


def test_alertmanager_webhook_success_unresolved(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    with open(FIXTURES_DIR / "mock-prom-high-disk.json") as f:
        payload = json.load(f)

    with (
        patch("ace.bypass.router.publish_to_stream", return_value=True),
        patch("ace.api.webhooks.alertmanager.evaluate_state", return_value=("OK", 0)),
    ):
        response = client.post("/webhooks/alertmanager", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "accepted"}

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 2
    for alert in alerts:
        assert alert.source_tool == "prometheus"
        # Since we didn't add any components, they should be unresolved
        assert alert.component_id is None
        assert alert.component_unresolved is True


def test_alertmanager_webhook_success_resolved(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    comp = Component(
        canonical_name="otel-collector",
        type="service",
        environment="production",
        tenant="default",
        service_tier="tier-1",
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )
    db_session.add(comp)
    db_session.commit()

    alias = ComponentAlias(
        component_id=comp.id,
        alias="otel-collector:8889",
        source_tool="prometheus",
        match_method="exact",
        confidence=100,
    )
    db_session.add(alias)
    db_session.commit()

    with open(FIXTURES_DIR / "mock-prom-high-disk.json") as f:
        payload = json.load(f)

    with (
        patch("ace.bypass.router.publish_to_stream", return_value=True),
        patch("ace.api.webhooks.alertmanager.evaluate_state", return_value=("OK", 0)),
    ):
        response = client.post("/webhooks/alertmanager", json=payload)
        assert response.status_code == 200

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 2
    for alert in alerts:
        assert alert.component_id == comp.id
        assert alert.component_unresolved is False


def test_alertmanager_webhook_malformed() -> None:
    # No dependency override needed, it should fail fast on Pydantic validation
    payload = {"bad": "payload"}
    response = client.post("/webhooks/alertmanager", json=payload)

    assert response.status_code == 422


def test_publish_failure_persists_and_notifies(db_session: Session, tmp_path: Path) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    with open(FIXTURES_DIR / "mock-prom-cart-down.json") as f:
        payload = json.load(f)

    with (
        patch("ace.bypass.router.publish_to_stream", return_value=False),
        patch("ace.api.webhooks.alertmanager.evaluate_state", return_value=("OK", 0)),
        patch("ace.bypass.router.NOTIFICATIONS_DIR", tmp_path),
    ):
        response = client.post("/webhooks/alertmanager", json=payload)
        assert response.status_code == 200

    alerts = db_session.query(Alert).all()
    assert len(alerts) > 0

    # Check that a notification file was written
    files = list(tmp_path.glob("*.json"))
    assert len(files) == len(alerts)

    # Verify degraded banner is present
    with open(files[0]) as f:
        notification = json.load(f)
        assert "_banner" in notification
        assert (
            notification["_banner"]
            == "[DEGRADED] Alert routed via bypass path. Correlation unavailable."
        )


def test_critical_alert_ok_state(db_session: Session, tmp_path: Path) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    with open(FIXTURES_DIR / "mock-prom-high-disk.json") as f:
        payload = json.load(f)

    # HighDiskUsage severity is 'page', which maps to 'critical' in our adapter
    with (
        patch("ace.bypass.router.publish_to_stream", return_value=True) as mock_publish,
        patch("ace.api.webhooks.alertmanager.evaluate_state", return_value=("OK", 0)),
        patch("ace.bypass.router.NOTIFICATIONS_DIR", tmp_path),
    ):
        response = client.post("/webhooks/alertmanager", json=payload)
        assert response.status_code == 200

    alerts = db_session.query(Alert).all()
    assert len(alerts) == 2

    # Should publish AND notify
    assert mock_publish.call_count == 2

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 2

    with open(files[0]) as f:
        notification = json.load(f)
        assert "_banner" not in notification


def test_lag_unknown_does_not_latch_bypass(db_session: Session) -> None:
    """
    Proves that if a consumer group doesn't exist, lag is unknown (None),
    so the system remains OK even if older messages exist in the stream.
    """
    app.dependency_overrides[get_db] = lambda: db_session

    import redis

    from ace.config import settings

    r = redis.from_url(settings.REDIS_URL)
    r.delete("alerts.raw")

    with open(FIXTURES_DIR / "mock-prom-high-disk.json") as f:
        payload = json.load(f)

    # Post an alert. We DON'T mock publish_to_stream, so it really goes to Redis.
    # We DON'T mock evaluate_state, so it really checks Redis.
    response = client.post("/webhooks/alertmanager", json=payload)
    assert response.status_code == 200

    # Ensure it's in the stream
    stream_len = r.xlen("alerts.raw")
    assert stream_len > 0

    # Advance time past MAX_PIPELINE_LAG and check state
    from ace.bypass.health import evaluate_state

    # We mock get_pipeline_lag's concept of 'now' or evaluate_state's canary check?
    # Actually, we don't even need to mock time if we mock the stream entry age!
    # Wait, the best way to advance time is to mock datetime.now in ace.bypass.health
    with patch("ace.bypass.health.datetime") as mock_dt:
        from datetime import UTC, timedelta

        # Set time to way in the future
        future_time = datetime.now(UTC) + timedelta(seconds=settings.MAX_PIPELINE_LAG + 100)
        mock_dt.now.return_value = future_time
        # Canary also uses datetime.now, so canary might fail! We disable canary check.
        with patch("ace.bypass.health.settings.CANARY_ENABLED", False):
            state, lag = evaluate_state()

    # State must be OK because lag is unknown (None)
    assert lag is None
    assert state == "OK"


def test_alertmanager_webhook_unknown_severity(db_session: Session, caplog) -> None:
    """
    Proves that an unknown severity maps to medium and logs a warning.
    """
    app.dependency_overrides[get_db] = lambda: db_session

    with open(FIXTURES_DIR / "mock-prom-high-disk.json") as f:
        payload = json.load(f)

    # Inject unknown severity
    for alert in payload["alerts"]:
        alert["labels"]["severity"] = "flibbertigibbet"

    with (
        patch("ace.bypass.router.publish_to_stream", return_value=True),
        patch("ace.api.webhooks.alertmanager.evaluate_state", return_value=("OK", 0)),
    ):
        response = client.post("/webhooks/alertmanager", json=payload)
        assert response.status_code == 200

    alerts = db_session.query(Alert).all()
    assert len(alerts) > 0
    for alert in alerts:
        assert alert.severity == "medium"
        assert "Unknown severity 'flibbertigibbet' mapped to medium" in caplog.text
