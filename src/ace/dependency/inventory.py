import logging
from datetime import UTC
from pathlib import Path

import yaml

from ace.api.deps import SessionLocal
from ace.config import settings
from ace.db.models.components import Dependency
from ace.ingestion.models import Candidate
from ace.ingestion.resolver import Resolver

logger = logging.getLogger(__name__)


def load_inventory_topology() -> None:
    """
    Seeds the dependencies table with edges defined in the inventory topology.yaml.
    These edges represent relationships invisible to tracing (e.g. Host -> Volume).
    """
    path = Path(settings.INVENTORY_TOPOLOGY_PATH)
    if not path.exists():
        logger.warning(f"Inventory topology file not found at {path}")
        return

    with open(path) as f:
        topology = yaml.safe_load(f)

    edges = topology.get("edges", [])
    if not edges:
        return

    with SessionLocal() as db:
        resolver = Resolver(db)

        for edge in edges:
            from_name = edge.get("from")
            to_name = edge.get("to")
            if not from_name or not to_name:
                continue

            from_id, _ = resolver.resolve(
                [Candidate(value=from_name, field_name="inventory_edge")], source_tool="inventory"
            )
            to_id, _ = resolver.resolve(
                [Candidate(value=to_name, field_name="inventory_edge")], source_tool="inventory"
            )

            if not from_id or not to_id:
                logger.warning(
                    f"Could not resolve components for inventory edge: {from_name} -> {to_name}"
                )
                continue

            # Inventory edges are considered truth with max confidence
            existing = (
                db.query(Dependency)
                .filter_by(from_component_id=from_id, to_component_id=to_id)
                .first()
            )

            if existing:
                existing.confidence = 1.0
                existing.source = "inventory"
            else:
                from datetime import datetime

                now = datetime.now(UTC)
                new_edge = Dependency(
                    from_component_id=from_id,
                    to_component_id=to_id,
                    confidence=1.0,
                    source="inventory",
                    observation_count=1,
                    first_seen=now,
                    last_seen=now,
                )
                db.add(new_edge)

        db.commit()
