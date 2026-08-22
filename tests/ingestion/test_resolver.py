import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy.orm import Session

from ace.db.models.components import Component, ComponentAlias
from ace.ingestion.models import Candidate
from ace.ingestion.resolver import Resolver


def test_resolver_precedence(db_session: Session) -> None:
    # Set up some test components and aliases
    comp_a = Component(
        id=uuid.uuid4(),
        canonical_name="comp_a",
        type="service",
        environment="production",
        tenant="default",
        service_tier="tier-1",
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )
    comp_b = Component(
        id=uuid.uuid4(),
        canonical_name="comp_b",
        type="service",
        environment="production",
        tenant="default",
        service_tier="tier-1",
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )
    db_session.add_all([comp_a, comp_b])
    db_session.commit()

    # comp_a has an alias "alias_a"
    alias_a = ComponentAlias(
        component_id=comp_a.id,
        alias="alias_a",
        source_tool="prom",
        match_method="exact",
        confidence=1.0,
    )
    db_session.add(alias_a)
    db_session.commit()

    resolver = Resolver(db_session)

    # 1. First candidate exact match
    candidates = [
        Candidate(value="comp_a", field_name="exact_match"),
        Candidate(value="something_else", field_name="fallback"),
    ]
    comp_id, unresolved = resolver.resolve(candidates, "prom")
    assert comp_id == comp_a.id
    assert not unresolved

    # 2. Second candidate exact match
    candidates = [
        Candidate(value="unknown", field_name="unknown"),
        Candidate(value="comp_b", field_name="exact_match"),
    ]
    comp_id, unresolved = resolver.resolve(candidates, "prom")
    assert comp_id == comp_b.id
    assert not unresolved

    # 3. Fuzzy match NEVER beats exact/alias match from a lower-precedence candidate
    candidates = [
        Candidate(value="comp_a_fuzzy", field_name="first_candidate"),  # Would match comp_a fuzzy
        Candidate(value="comp_b", field_name="second_candidate"),  # Exact matches comp_b
    ]

    with patch(
        "ace.db.repositories.components.ComponentRepository.fuzzy_search",
        return_value=(comp_a, 90.0),
    ):
        comp_id, unresolved = resolver.resolve(candidates, "prom")
        # Should be comp_b because pass 1 (exact/alias) runs on all candidates before pass 2 (fuzzy)
        assert comp_id == comp_b.id
        assert not unresolved

    # 4. Fuzzy fallback if no exact/alias match
    candidates = [
        Candidate(value="comp_a_fuzzy", field_name="first_candidate"),
        Candidate(value="unknown_b", field_name="second_candidate"),
    ]
    with patch(
        "ace.db.repositories.components.ComponentRepository.fuzzy_search",
        return_value=(comp_a, 90.0),
    ):
        comp_id, unresolved = resolver.resolve(candidates, "prom")
        assert comp_id == comp_a.id
        assert not unresolved
