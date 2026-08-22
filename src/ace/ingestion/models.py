from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NormalisedAlert(BaseModel):
    id: UUID | None = Field(default=None, description="Database ID (populated after persist)")
    source_tool: str = Field(..., description="Tool that generated the alert (e.g., prometheus)")
    external_id: str = Field(..., description="Unique ID from the source tool (e.g., fingerprint)")
    severity: str = Field(..., description="Mapped severity (info, low, medium, high, critical)")
    component_id: UUID | None = Field(default=None, description="Resolved component ID, if any")
    component_unresolved: bool = Field(
        default=False, description="True if component resolution failed"
    )
    labels: dict[str, Any] = Field(default_factory=dict, description="Alert labels")
    annotations: dict[str, Any] = Field(default_factory=dict, description="Alert annotations")
    raw_payload: dict[str, Any] = Field(..., description="Original raw payload for audit")
    starts_at: datetime = Field(..., description="When the alert started firing")
    ends_at: datetime | None = Field(default=None, description="When the alert resolved")
    status: str = Field(..., description="Current status (e.g., firing, resolved)")
    environment: str = Field(default="production", description="Deployment environment")
    tenant: str = Field(default="default", description="Tenant ID")
