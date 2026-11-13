"""Private buyer-managed post-handover roadmap snapshots."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now, uid


class DevelopmentRoadmap(Base):
    __tablename__ = 'development_roadmaps'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), unique=True, index=True, nullable=False)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class DevelopmentRoadmapTask(Base):
    __tablename__ = 'development_roadmap_tasks'
    __table_args__ = (UniqueConstraint('roadmap_id', 'task_key', name='uq_roadmap_task_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    roadmap_id: Mapped[str] = mapped_column(ForeignKey('development_roadmaps.id'), index=True, nullable=False)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(12), nullable=False)
    assistance: Mapped[str] = mapped_column(String(12), nullable=False)
    priority: Mapped[str] = mapped_column(String(12), nullable=False)
    prerequisites: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    success_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[str] = mapped_column(String(40), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='NOT_STARTED')
    buyer_note: Mapped[str] = mapped_column(Text, nullable=False, default='')
    blocked_reason: Mapped[str | None] = mapped_column(String(28))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)
