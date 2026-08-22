from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ace.db.models.alerts import Alert
from ace.db.models.components import Component, ComponentAlias, Dependency
from ace.db.models.incidents import Incident, IncidentFeedback, IncidentLink, IncidentSplit
from ace.db.repositories.dependencies import DependencyRepository


def test_schema_acceptance(db_session: Session) -> None:
    now = datetime.now(UTC)

    # 1. Create a component
    cart_comp = Component(
        canonical_name="cart",
        type="service",
        environment="prod",
        tenant="default",
        service_tier="tier-1",
        first_seen=now,
        last_seen=now,
    )
    valkey_comp = Component(
        canonical_name="valkey",
        type="cache",
        environment="prod",
        tenant="default",
        service_tier="tier-1",
        first_seen=now,
        last_seen=now,
    )
    db_session.add_all([cart_comp, valkey_comp])
    db_session.commit()

    # 2. Create aliases from TWO different tools with the same alias string
    alias1 = ComponentAlias(
        component_id=cart_comp.id,
        alias="cart-service",
        source_tool="prometheus",
        match_method="exact",
        confidence=1.0,
    )
    alias2 = ComponentAlias(
        component_id=cart_comp.id,
        alias="cart-service",
        source_tool="zabbix",
        match_method="exact",
        confidence=1.0,
    )
    db_session.add_all([alias1, alias2])
    db_session.commit()

    # 3. Create two alerts
    alert1 = Alert(
        source_tool="prometheus",
        external_id="ext-1",
        component_id=cart_comp.id,
        severity="critical",
        fingerprint="fp-1",
        status="firing",
        environment="prod",
        tenant="default",
        starts_at=now,
        received_at=now,
    )
    alert2 = Alert(
        source_tool="zabbix",
        external_id="ext-2",
        component_id=valkey_comp.id,
        severity="high",
        fingerprint="fp-2",
        status="firing",
        environment="prod",
        tenant="default",
        starts_at=now,
        received_at=now,
    )
    db_session.add_all([alert1, alert2])
    db_session.commit()

    # 4. Create an incident with source_tool_count=2
    inc1 = Incident(
        title="Cart is down",
        status="active",
        severity="critical",
        opened_at=now,
        alert_count=2,
        source_tool_count=2,
    )
    inc2 = Incident(
        title="Valkey is slow",
        status="active",
        severity="high",
        opened_at=now,
        alert_count=1,
        source_tool_count=1,
    )
    db_session.add_all([inc1, inc2])
    db_session.commit()

    # 5. Create an incident link, feedback row, and split row
    # Determine the order to satisfy "incident_a < incident_b"
    a_id, b_id = (inc1.id, inc2.id) if str(inc1.id) < str(inc2.id) else (inc2.id, inc1.id)

    link = IncidentLink(
        incident_a=a_id,
        incident_b=b_id,
        link_type="possibly_related",
        reason="time proximity",
        created_at=now,
    )
    feedback = IncidentFeedback(
        incident_id=inc1.id,
        alert_id=alert1.id,
        verdict="correct",
        operator="admin",
        note="Good catch",
        created_at=now,
    )
    split = IncidentSplit(
        original_incident_id=inc1.id,
        resulting_incident_ids=[str(inc2.id)],
        reason="Unrelated root cause",
        operator="admin",
        created_at=now,
    )
    db_session.add_all([link, feedback, split])
    db_session.commit()

    # 6. Prove dependency direction: cart depends on valkey
    dep = Dependency(
        from_component_id=cart_comp.id,
        to_component_id=valkey_comp.id,
        confidence=1.0,
        observation_count=1,
        first_seen=now,
        last_seen=now,
        source="manual",
    )
    db_session.add(dep)
    db_session.commit()

    repo = DependencyRepository(db_session)
    deps = repo.dependents_of(valkey_comp.id)
    assert len(deps) == 1
    assert deps[0].id == cart_comp.id


def test_incident_links_rejects_reversed_duplicate(db_session: Session) -> None:
    now = datetime.now(UTC)
    inc1 = Incident(title="A", status="active", severity="low", opened_at=now)
    inc2 = Incident(title="B", status="active", severity="low", opened_at=now)
    db_session.add_all([inc1, inc2])
    db_session.commit()

    a_id, b_id = (inc1.id, inc2.id) if str(inc1.id) < str(inc2.id) else (inc2.id, inc1.id)

    # Insert correct ordering
    link_correct = IncidentLink(
        incident_a=a_id, incident_b=b_id, link_type="related", reason="test", created_at=now
    )
    db_session.add(link_correct)
    db_session.commit()

    # Try inserting reversed (should fail due to CHECK constraint incident_a < incident_b)
    link_reversed = IncidentLink(
        incident_a=b_id, incident_b=a_id, link_type="related", reason="test", created_at=now
    )
    db_session.add(link_reversed)
    with pytest.raises(IntegrityError):
        db_session.commit()
