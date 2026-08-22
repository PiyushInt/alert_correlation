import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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


class Component(Base):
    __tablename__ = "components"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant: Mapped[str] = mapped_column(String(100), nullable=False)
    service_tier: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentAlias(Base):
    __tablename__ = "component_aliases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    source_tool: Mapped[str] = mapped_column(String(100), nullable=False)
    match_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'exact'|'alias'|'fuzzy'|'manual'
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("alias", "source_tool", name="uq_component_aliases_alias_source_tool"),
        Index("ix_component_aliases_alias", "alias"),
    )


class Dependency(Base):
    """
    from_component_id DEPENDS ON to_component_id.
    The arrow points from dependent to dependency.
    """

    __tablename__ = "dependencies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    to_component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # 'trace'|'inventory'|'manual'

    __table_args__ = (
        UniqueConstraint("from_component_id", "to_component_id", name="uq_dependencies_from_to"),
        Index("ix_dependencies_from_component_id", "from_component_id"),
        Index("ix_dependencies_to_component_id", "to_component_id"),
    )


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_change_events_component_id_occurred_at", "component_id", "occurred_at"),
    )
