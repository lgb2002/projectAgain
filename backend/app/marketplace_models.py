"""V0.7 marketplace content, conversations and reliable notification outbox.
Import these model classes before metadata.create_all or migrations.
"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, now


class ListingShowcase(Base):
    __tablename__ = 'listing_showcases'
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), primary_key=True)
    demo_url: Mapped[str | None] = mapped_column(String(700))
    video_url: Mapped[str | None] = mapped_column(String(700))
    highlights: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ListingMedia(Base):
    __tablename__ = 'listing_media'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), index=True, nullable=False)
    object_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    caption: Mapped[str] = mapped_column(String(140), default='', nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class ListingInquiry(Base):
    __tablename__ = 'listing_inquiries'
    __table_args__ = (Index('ix_inquiry_listing_visibility_created', 'listing_id','visibility','created_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), index=True, nullable=False)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(12), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class NotificationEmail(Base):
    """Outbox row in SAME DB transaction as the notification; worker delivers later."""
    __tablename__ = 'notification_emails'
    __table_args__ = (UniqueConstraint('notification_id'), Index('ix_email_status_due', 'status', 'next_attempt_at'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    notification_id: Mapped[str] = mapped_column(ForeignKey('notifications.id'), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
