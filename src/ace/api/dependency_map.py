from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ace.api.deps import get_db
from ace.dependency.graph import graph_instance

router = APIRouter()


@router.get("/{component_id}")
def get_dependency_map(
    component_id: UUID,
    hops: int = Query(1, ge=1, le=10),
    direction: str = Query("both", pattern="^(inbound|outbound|both)$"),
    db: Session = Depends(get_db),  # noqa: B008
) -> Any:
    """
    Returns the local dependency subgraph for a component.
    """
    from ace.db.models.components import Component

    center_component = db.query(Component).filter_by(id=component_id).first()
    if not center_component:
        raise HTTPException(status_code=404, detail="Component not found")

    nodes_in_subgraph = graph_instance.neighbours_within(
        component_id, hops=hops, direction=direction
    )
    # Include the center component itself
    nodes_in_subgraph.add(component_id)

    components = db.query(Component).filter(Component.id.in_(list(nodes_in_subgraph))).all()
    nodes_data = [
        {"id": str(c.id), "canonical_name": c.canonical_name, "type": c.type} for c in components
    ]

    edges_data = []
    # Build edges between the nodes in the subgraph
    for u in nodes_in_subgraph:
        for v in nodes_in_subgraph:
            if u != v:
                edge_data = graph_instance.get_edge_data(u, v)
                if edge_data:
                    edges_data.append(
                        {
                            "from": str(u),
                            "to": str(v),
                            "confidence": edge_data.get("confidence", 1.0),
                            "source": edge_data.get("source", "unknown"),
                        }
                    )

    return {
        "center": str(component_id),
        "hops": hops,
        "direction": direction,
        "nodes": nodes_data,
        "edges": edges_data,
    }
