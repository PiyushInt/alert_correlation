import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ace.db.models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_tool: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    annotations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant: Mapped[str] = mapped_column(String(100), nullable=False)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    bypassed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_alerts_component_id_starts_at", "component_id", "starts_at"),
        Index("ix_alerts_fingerprint", "fingerprint"),
        Index("ix_alerts_incident_id", "incident_id"),
    )


class AlertTypeStat(Base):
    __tablename__ = "alert_type_stats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_type_a: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type_b: Mapped[str] = mapped_column(String(255), nullable=False)
    co_occurrence_count: Mapped[int] = mapped_column(nullable=False, default=0)
    confirmed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    window_days: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_alert_type_stats_types", "alert_type_a", "alert_type_b"),)
