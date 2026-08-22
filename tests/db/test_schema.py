from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ace.db.models.alerts import Alert
from ace.db.models.components import Component, ComponentAlias, Dependency
from ace.db.models.incidents import Incident, IncidentFeedback, IncidentLink, IncidentSplit
from ace.db.repositories.dependencies import DependencyRepository


def test_component_creation(db_session: Session) -> None:
    now = datetime.now(UTC)
    comp = Component(
        canonical_name="cart",
        type="service",
        environment="prod",
        tenant="default",
        service_tier="tier-1",
        first_seen=now,
        last_seen=now,
    )
    db_session.add(comp)
    db_session.commit()
    assert comp.id is not None


def test_composite_unique_key_permits_same_alias_string_different_tools(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    comp = Component(
        canonical_name="cart",
        type="service",
        environment="prod",
        tenant="default",
        service_tier="tier-1",
        first_seen=now,
        last_seen=now,
    )
    db_session.add(comp)
    db_session.commit()

    alias1 = ComponentAlias(
        component_id=comp.id,
        alias="cart-service",
        source_tool="prometheus",
        match_method="exact",
        confidence=1.0,
    )
    alias2 = ComponentAlias(
        component_id=comp.id,
        alias="cart-service",
        source_tool="zabbix",
        match_method="exact",
        confidence=1.0,
    )
    db_session.add_all([alias1, alias2])
    db_session.commit()
    assert alias1.id is not None
    assert alias2.id is not None


def test_create_two_alerts(db_session: Session) -> None:
    now = datetime.now(UTC)
    alert1 = Alert(
        source_tool="prometheus",
        external_id="ext-1",
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
    assert alert1.id is not None
    assert alert2.id is not None


def test_create_incident_with_source_tool_count_2(db_session: Session) -> None:
    now = datetime.now(UTC)
    inc = Incident(
        title="Cart is down",
        status="active",
        severity="critical",
        opened_at=now,
        alert_count=2,
        source_tool_count=2,
    )
    db_session.add(inc)
    db_session.commit()
    assert inc.source_tool_count == 2


def test_incident_link_feedback_split(db_session: Session) -> None:
    now = datetime.now(UTC)
    inc1 = Incident(
        title="Cart is down",
        status="active",
        severity="critical",
        opened_at=now,
    )
    inc2 = Incident(
        title="Valkey is slow",
        status="active",
        severity="high",
        opened_at=now,
    )
    db_session.add_all([inc1, inc2])
    db_session.commit()

    a_id, b_id = (inc1.id, inc2.id) if inc1.id < inc2.id else (inc2.id, inc1.id)

    link = IncidentLink(
        incident_a=a_id,
        incident_b=b_id,
        link_type="possibly_related",
        reason="time proximity",
        created_at=now,
    )
    feedback = IncidentFeedback(
        incident_id=inc1.id,
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
    assert link.id is not None
    assert feedback.id is not None
    assert split.id is not None


def test_dependency_direction(db_session: Session) -> None:
    now = datetime.now(UTC)
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

    # "cart depends on valkey" -> from=cart, to=valkey
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
    # dependents_of(valkey) returns cart
    deps = repo.dependents_of(valkey_comp.id)
    assert len(deps) == 1
    assert deps[0].canonical_name == "cart"
    assert deps[0].id == cart_comp.id


def test_incident_links_rejects_reversed_duplicate(db_session: Session) -> None:
    now = datetime.now(UTC)
    inc1 = Incident(title="A", status="active", severity="low", opened_at=now)
    inc2 = Incident(title="B", status="active", severity="low", opened_at=now)
    db_session.add_all([inc1, inc2])
    db_session.commit()

    a_id, b_id = (inc1.id, inc2.id) if inc1.id < inc2.id else (inc2.id, inc1.id)

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


def test_incident_links_rejects_exact_duplicate(db_session: Session) -> None:
    now = datetime.now(UTC)
    inc1 = Incident(title="A", status="active", severity="low", opened_at=now)
    inc2 = Incident(title="B", status="active", severity="low", opened_at=now)
    db_session.add_all([inc1, inc2])
    db_session.commit()

    a_id, b_id = (inc1.id, inc2.id) if inc1.id < inc2.id else (inc2.id, inc1.id)

    # Insert correct ordering
    link_correct = IncidentLink(
        incident_a=a_id, incident_b=b_id, link_type="related", reason="test", created_at=now
    )
    db_session.add(link_correct)
    db_session.commit()

    # Try inserting the EXACT SAME pair again (should fail due to UNIQUE constraint)
    link_duplicate = IncidentLink(
        incident_a=a_id, incident_b=b_id, link_type="related", reason="duplicate", created_at=now
    )
    db_session.add(link_duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
