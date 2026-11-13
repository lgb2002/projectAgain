"""v0.8: DEMO-only transaction agreements, case management and append-only timelines.
No legal e-signatures, payments, escrow, settlement or ownership transfer are implemented.
"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, BigInteger, JSON, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now

class DealAgreement(Base):
    __tablename__ = 'deal_agreements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), unique=True, nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey('offers.id'), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False)
    buyer_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seller_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    buyer_ack_digest: Mapped[str | None] = mapped_column(String(64))
    seller_ack_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class DealCancellation(Base):
    __tablename__ = 'deal_cancellations'
    __table_args__ = (Index('ix_deal_cancellations_tx_status', 'transaction_id', 'status'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False)
    responded_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    response_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class DealDispute(Base):
    __tablename__ = 'deal_disputes'
    __table_args__ = (Index('ix_deal_disputes_tx_status', 'transaction_id', 'status'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), nullable=False, index=True)
    opened_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default='OPEN', nullable=False)
    counterparty_response: Mapped[str | None] = mapped_column(Text)
    counterparty_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_decision: Mapped[str | None] = mapped_column(String(40))
    admin_reason: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_status: Mapped[str] = mapped_column(String(32), default='HANDOVER_IN_PROGRESS', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class DealEvent(Base):
    __tablename__ = 'deal_events'
    __table_args__ = (Index('ix_deal_events_tx_created', 'transaction_id', 'created_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
