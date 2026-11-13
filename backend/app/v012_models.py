"""v0.12 demo negotiation, support and buyer-guidance records.

Never treats a simulated handover as legal asset transfer or payment.
"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now


class OfferThread(Base):
    __tablename__ = 'offer_threads'
    __table_args__ = (Index('ix_offer_threads_pair', 'listing_id', 'buyer_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), nullable=False)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default='UNRESOLVED', nullable=False)
    last_offer_id: Mapped[str | None] = mapped_column(String(36))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SupportPolicySnapshot(Base):
    __tablename__ = 'support_policy_snapshots'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), nullable=False, unique=True)
    agreement_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    case_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reply_goal_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)
    reply_goal_guaranteed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    simulation_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class SupportCase(Base):
    __tablename__ = 'support_cases'
    __table_args__ = (Index('ix_support_cases_tx_category', 'transaction_id', 'coverage_type'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), nullable=False, index=True)
    roadmap_task_id: Mapped[str | None] = mapped_column(ForeignKey('development_roadmap_tasks.id'))
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    category: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_type: Mapped[str] = mapped_column(String(25), nullable=False)
    status: Mapped[str] = mapped_column(String(25), default='OPEN', nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    first_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SupportMessage(Base):
    __tablename__ = 'support_messages'
    __table_args__ = (Index('ix_support_messages_case_date', 'case_id', 'created_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('support_cases.id'), nullable=False)
    sender_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    message_type: Mapped[str] = mapped_column(String(25), default='COMMENT', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class RoadmapBuyerContext(Base):
    __tablename__ = 'roadmap_buyer_contexts'
    roadmap_id: Mapped[str] = mapped_column(ForeignKey('development_roadmaps.id'), primary_key=True)
    skill_level: Mapped[str] = mapped_column(String(20), nullable=False, default='BASIC')
    objective: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    preferred_guidance_level: Mapped[str] = mapped_column(String(20), nullable=False, default='DETAILED')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class RoadmapTaskHelpLink(Base):
    __tablename__ = 'roadmap_task_help_links'
    __table_args__ = (UniqueConstraint('roadmap_task_id', 'support_case_id', name='uq_roadmap_help_link'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    roadmap_task_id: Mapped[str] = mapped_column(ForeignKey('development_roadmap_tasks.id'), nullable=False)
    support_case_id: Mapped[str] = mapped_column(ForeignKey('support_cases.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
