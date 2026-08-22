from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ace.api.dependencies import get_db
from ace.db.models.components import Component, ComponentAlias

router = APIRouter()


@router.get("/{component_id}")
def get_component(component_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:  # noqa: B008
    """
    Get a component and its aliases by ID.
    """
    component = db.query(Component).filter(Component.id == component_id).first()
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")

    aliases = db.query(ComponentAlias).filter(ComponentAlias.component_id == component_id).all()

    return {
        "id": component.id,
        "canonical_name": component.canonical_name,
        "type": component.type,
        "environment": component.environment,
        "tenant": component.tenant,
        "service_tier": component.service_tier,
        "aliases": [
            {
                "id": a.id,
                "alias": a.alias,
                "source_tool": a.source_tool,
                "match_method": a.match_method,
            }
            for a in aliases
        ],
    }
