import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ace.db.models.base import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_tool_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    root_cause_component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), nullable=True
    )
    diameter_hops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    split_from_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (Index("ix_incidents_status_opened_at", "status", "opened_at"),)


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    join_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    join_score: Mapped[float] = mapped_column(Float, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("incident_id", "alert_id", name="uq_incident_alerts_incident_alert"),
    )


class IncidentLink(Base):
    __tablename__ = "incident_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_a: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    incident_b: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'possibly_related'
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("incident_a < incident_b", name="ck_incident_links_ordering"),
        UniqueConstraint("incident_a", "incident_b", name="uq_incident_links_a_b"),
    )


class IncidentFeedback(Base):
    __tablename__ = "incident_feedback"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'correct'|'wrong_group'|'missed_member'|'wrong_cause'
    operator: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_incident_feedback_incident_id", "incident_id"),)


class IncidentSplit(Base):
    __tablename__ = "incident_splits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    resulting_incident_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    operator: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RootCauseCandidate(Base):
    __tablename__ = "root_cause_candidates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
