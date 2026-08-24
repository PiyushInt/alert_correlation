import asyncio
import logging
from datetime import UTC, datetime

import redis
from sqlalchemy.orm import Session

from ace.api.deps import SessionLocal
from ace.config import settings
from ace.db.models.components import Dependency
from ace.dependency.graph import graph_instance
from ace.dependency.health import update_map_health_metrics
from ace.dependency.inventory import load_inventory_topology

logger = logging.getLogger(__name__)


def refresh_once(db: Session) -> None:
    """
    Does one pass of the graph refresh logic.
    """
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    now = datetime.now(UTC)
    last_refresh_str = redis_client.get("graph_last_refresh")

    if isinstance(last_refresh_str, str):
        last_refresh = datetime.fromisoformat(last_refresh_str)

        # Apply decay
        trace_edges = db.query(Dependency).filter_by(source="trace").all()
        edges_to_delete = []

        for edge in trace_edges:
            if edge.last_seen and edge.last_seen < last_refresh:
                edge.confidence -= settings.EDGE_CONFIDENCE_DECAY
                if edge.confidence < settings.EDGE_CONFIDENCE_MIN:
                    edges_to_delete.append(edge)

        for edge in edges_to_delete:
            db.delete(edge)

        db.commit()

    # Update the refresh timestamp in Redis
    redis_client.set("graph_last_refresh", now.isoformat())

    # Reload the memory graph
    graph_instance.refresh(db)

    # Update health metrics
    update_map_health_metrics(db)


async def graph_refresh_loop() -> None:
    """
    Periodic job that:
    1. Applies confidence decay to trace edges not seen since last refresh.
    2. Refreshes the NetworkX graph from DB.
    3. Computes map health metrics.
    """
    # Run the initial inventory seed
    try:
        load_inventory_topology()
    except Exception as e:
        logger.error(f"Failed to load inventory topology: {e}")

    while True:
        try:
            with SessionLocal() as db:
                refresh_once(db)
        except Exception as e:
            logger.error(f"Error in graph refresh job: {e}", exc_info=True)

        await asyncio.sleep(settings.GRAPH_REFRESH_INTERVAL)
