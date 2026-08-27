import uuid
from datetime import UTC, datetime

import pytest
import redis
from sqlalchemy.orm import Session

from ace.config import settings
from ace.db.models.alerts import Alert
from ace.ingestion.models import NormalisedAlert
from ace.pipeline.dedup import check_dedup


@pytest.fixture
def redis_client() -> redis.Redis:
    r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
    r.flushdb()
    return r


def create_mock_alert(status: str = "firing", severity: str = "warning") -> NormalisedAlert:
    return NormalisedAlert(
        id=uuid.uuid4(),
        source_tool="prometheus",
        external_id="ext-123",
        severity=severity,
        component_unresolved=False,
        raw_payload={},
        starts_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        status=status,
    )


def test_dedup_first_passes_second_deduped(redis_client: redis.Redis, db_session: Session) -> None:
    fp = "test-fp-1"

    # Store first alert in DB
    alert1 = create_mock_alert()
    db_alert1 = Alert(
        **alert1.model_dump(exclude_none=True), fingerprint=fp, received_at=datetime.now(UTC)
    )
    db_session.add(db_alert1)
    db_session.commit()

    # First check -> miss (forwards)
    assert not check_dedup(redis_client, fp, alert1, db_session)

    # Second incoming identical alert
    alert2 = create_mock_alert()
    db_alert2 = Alert(
        **alert2.model_dump(exclude_none=True), fingerprint=fp, received_at=datetime.now(UTC)
    )
    db_session.add(db_alert2)
    db_session.commit()

    # Second check -> hit (drops)
    assert check_dedup(redis_client, fp, alert2, db_session)

    # Check original was updated
    db_session.refresh(db_alert1)
    assert db_alert1.occurrence_count == 2
    assert db_alert1.last_seen_at == db_alert2.received_at

    # Check duplicate row still exists (not deleted)
    assert db_session.get(Alert, db_alert2.id) is not None


def test_dedup_highest_severity_wins(redis_client: redis.Redis, db_session: Session) -> None:
    fp = "test-fp-2"

    alert1 = create_mock_alert(severity="warning")
    db_alert1 = Alert(
        **alert1.model_dump(exclude_none=True), fingerprint=fp, received_at=datetime.now(UTC)
    )
    db_session.add(db_alert1)
    db_session.commit()

    check_dedup(redis_client, fp, alert1, db_session)

    # New alert escalated to critical
    alert2 = create_mock_alert(severity="critical")
    db_alert2 = Alert(
        **alert2.model_dump(exclude_none=True), fingerprint=fp, received_at=datetime.now(UTC)
    )
    db_session.add(db_alert2)
    db_session.commit()

    assert check_dedup(redis_client, fp, alert2, db_session)

    db_session.refresh(db_alert1)
    assert db_alert1.occurrence_count == 2
    assert db_alert1.severity == "warning"  # Not mutated
    assert db_alert1.last_seen_at == db_alert2.received_at


def test_dedup_resolved_closes_and_clears_key(
    redis_client: redis.Redis, db_session: Session
) -> None:
    fp = "test-fp-3"

    # Firing
    firing_alert = create_mock_alert(status="firing")
    db_firing = Alert(
        **firing_alert.model_dump(exclude_none=True), fingerprint=fp, received_at=datetime.now(UTC)
    )
    db_session.add(db_firing)
    db_session.commit()

    assert not check_dedup(redis_client, fp, firing_alert, db_session)

    # Resolved
    resolved_alert = create_mock_alert(status="resolved")
    db_resolved = Alert(
        **resolved_alert.model_dump(exclude_none=True),
        fingerprint=fp,
        received_at=datetime.now(UTC),
    )
    db_session.add(db_resolved)
    db_session.commit()

    # Resolved hits dedup key, updates original, deletes key, returns False to forward
    assert not check_dedup(redis_client, fp, resolved_alert, db_session)

    db_session.refresh(db_firing)
    assert db_firing.status == "firing"
    assert db_firing.ends_at is None

    db_session.refresh(db_resolved)
    assert db_resolved.resolves_alert_id == db_firing.id

    # Firing again -> new alert (re-fire bug fixed)
    firing2 = create_mock_alert(status="firing")
    db_firing2 = Alert(
        **firing2.model_dump(exclude_none=True), fingerprint=fp, received_at=datetime.now(UTC)
    )
    db_session.add(db_firing2)
    db_session.commit()

    assert not check_dedup(redis_client, fp, firing2, db_session)
    assert redis_client.exists(f"dedup:{fp}")
