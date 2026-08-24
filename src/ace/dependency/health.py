import logging
from datetime import UTC, datetime

from prometheus_client import Gauge
from sqlalchemy.orm import Session

from ace.db.models.alerts import Alert
from ace.db.models.components import Component, Dependency
from ace.dependency.graph import graph_instance

logger = logging.getLogger(__name__)

map_edge_count_trace = Gauge(
    "ace_map_edge_count_trace", "Total trace-derived edges in the dependency graph"
)
map_edge_count_inventory = Gauge(
    "ace_map_edge_count_inventory", "Total inventory-derived edges in the dependency graph"
)
map_component_coverage = Gauge(
    "ace_map_component_coverage", "Share of components with at least one edge"
)
map_orphan_alert_share = Gauge(
    "ace_map_orphan_alert_share", "Share of last-24h alerts whose component has no edges"
)
map_mean_edge_age_seconds = Gauge(
    "ace_map_mean_edge_age_seconds", "Mean age of edges (now - last_seen)"
)


def update_map_health_metrics(session: Session) -> None:
    """
    Computes and updates Prometheus metrics for dependency map health.
    """
    now = datetime.now(UTC)

    # 1. Edge counts by source
    trace_edges = session.query(Dependency).filter_by(source="trace").count()
    inv_edges = session.query(Dependency).filter_by(source="inventory").count()
    map_edge_count_trace.set(trace_edges)
    map_edge_count_inventory.set(inv_edges)

    # 2. Component Coverage
    total_components = session.query(Component).count()
    if total_components > 0:
        # Components with at least one edge (either as dependent or dependency)
        components_with_edges = set()
        for from_id, to_id in session.query(
            Dependency.from_component_id, Dependency.to_component_id
        ):
            components_with_edges.add(from_id)
            components_with_edges.add(to_id)

        coverage = len(components_with_edges) / total_components
        map_component_coverage.set(coverage)
    else:
        map_component_coverage.set(0.0)

    # 3. Orphan Alert Share
    # Count alerts in last 24h
    import datetime as dt

    twenty_four_hours_ago = now - dt.timedelta(days=1)

    recent_alerts = session.query(Alert).filter(Alert.received_at >= twenty_four_hours_ago).all()
    if recent_alerts:
        orphan_count = 0
        for alert in recent_alerts:
            if alert.component_id:
                # Does this component have any edges? Check memory graph
                if graph_instance.get_node_count() > 0:
                    if alert.component_id not in graph_instance._graph:
                        orphan_count += 1
                else:
                    orphan_count += 1
            else:
                # Null component ID is an orphan
                orphan_count += 1

        orphan_share = orphan_count / len(recent_alerts)
        map_orphan_alert_share.set(orphan_share)
    else:
        map_orphan_alert_share.set(0.0)

    # 4. Mean Edge Age
    edges = session.query(Dependency).all()
    if edges:
        total_age = sum(
            ((now - edge.last_seen).total_seconds() for edge in edges if edge.last_seen), 0.0
        )
        # Inventory edges might not have last_seen depending on seeding mechanism
        # But we set observation_count=1, so we should set last_seen=now during seeding.
        # If any edge lacks last_seen, default to 0 for it
        mean_age = total_age / len(edges)
        map_mean_edge_age_seconds.set(mean_age)
    else:
        map_mean_edge_age_seconds.set(0.0)
