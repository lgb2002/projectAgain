from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, BigInteger, Boolean, DateTime, ForeignKey, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(12), default='USER', nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Listing(Base):
    __tablename__ = 'listings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(40), nullable=False)
    sale_rights_type: Mapped[str] = mapped_column(String(60), nullable=False)
    inventory_mode: Mapped[str] = mapped_column(String(20), default='ONE_TIME', nullable=False)
    price_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    included_assets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    excluded_assets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    known_defects: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_services: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    monthly_cost_estimate_krw: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    handover_days_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_support_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_revenue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revenue_krw_claimed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revenue_claim_verification: Mapped[str] = mapped_column(String(40), default='NOT_PROVIDED', nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default='UNVERIFIED', nullable=False)
    status: Mapped[str] = mapped_column(String(24), default='DRAFT', index=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rights_attested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class BuyerPreferences(Base):
    __tablename__ = 'buyer_preferences'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    min_budget_krw: Mapped[int] = mapped_column(BigInteger, default=0)
    max_budget_krw: Mapped[int] = mapped_column(BigInteger, default=1000000)
    skill_level: Mapped[str] = mapped_column(String(20), default='BASIC')
    objectives: Mapped[list] = mapped_column(JSON, default=list)
    preferred_tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    max_monthly_cost_krw: Mapped[int | None] = mapped_column(BigInteger)
    risk_tolerance: Mapped[str] = mapped_column(String(12), default='MEDIUM')


class Favorite(Base):
    __tablename__ = 'favorites'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Offer(Base):
    __tablename__ = 'offers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), index=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    parent_offer_id: Mapped[str | None] = mapped_column(ForeignKey('offers.id'))
    thread_id: Mapped[str | None] = mapped_column(ForeignKey('offer_threads.id'), nullable=True, index=True)
    listing_version_at_proposal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proposed_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    offered_price_krw: Mapped[int] = mapped_column(BigInteger)
    terms: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Transaction(Base):
    __tablename__ = 'transactions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), index=True)
    accepted_offer_id: Mapped[str] = mapped_column(ForeignKey('offers.id'), unique=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    exclusive_guard_listing_id: Mapped[str | None] = mapped_column(ForeignKey('listings.id'), unique=True, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default='AWAITING_HANDOVER', nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HandoverCheck(Base):
    __tablename__ = 'handover_checks'
    __table_args__ = (UniqueConstraint('transaction_id', 'check_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), index=True)
    check_key: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    seller_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    buyer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str] = mapped_column(String(24), default='NOT_TESTED')
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    remarks: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class InspectionReport(Base):
    __tablename__ = 'inspection_reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), index=True)
    report_type: Mapped[str] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(24))
    reviewer_kind: Mapped[str] = mapped_column(String(24), default='AI_AGENT')
    submitted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    agent_job_id: Mapped[str | None] = mapped_column(String(36))
    findings: Mapped[list] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    source_version_sha256: Mapped[str | None] = mapped_column(String(64))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentAction(Base):
    __tablename__ = 'agent_action_requests'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    requesting_agent_id: Mapped[str] = mapped_column(String(128))
    action_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(36))
    proposed_payload: Mapped[dict] = mapped_column(JSON)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default='PENDING_APPROVAL')
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_resource_id: Mapped[str | None] = mapped_column(String(36))


class ServiceGrant(Base):
    __tablename__ = 'service_grants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    principal_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    client_id: Mapped[str] = mapped_column(String(128), default='external_agent')
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ListingAsset(Base):
    __tablename__ = 'listing_assets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'))
    asset_type: Mapped[str] = mapped_column(String(30))
    file_name: Mapped[str] = mapped_column(String(255))
    private_object_key: Mapped[str] = mapped_column(String(64), unique=True)
    content_type: Mapped[str] = mapped_column(String(160))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    visibility: Mapped[str] = mapped_column(String(40), default='PRIVATE_SELLER')
    upload_status: Mapped[str] = mapped_column(String(24), default='QUARANTINED')
    malware_scan_status: Mapped[str] = mapped_column(String(24), default='NOT_PERFORMED', nullable=False)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModerationReport(Base):
    __tablename__ = 'moderation_reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'))
    reported_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    reason_code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    actor_type: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(48))
    resource_id: Mapped[str] = mapped_column(String(36))
    old_state: Mapped[dict | None] = mapped_column(JSON)
    new_state: Mapped[dict | None] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdempotencyRecord(Base):
    __tablename__ = 'idempotency_records'
    __table_args__ = (UniqueConstraint('actor_id', 'route', 'request_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    route: Mapped[str] = mapped_column(String(120), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class DownloadTicket(Base):
    __tablename__ = 'download_tickets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    asset_id: Mapped[str] = mapped_column(ForeignKey('listing_assets.id'), index=True, nullable=False)
    issued_to_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssetShare(Base):
    __tablename__ = 'asset_shares'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    asset_id: Mapped[str] = mapped_column(ForeignKey('listing_assets.id'), index=True, nullable=False)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), index=True, nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PasswordResetToken(Base):
    __tablename__ = 'password_reset_tokens'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SecurityThrottle(Base):
    __tablename__ = 'security_throttles'
    __table_args__ = (UniqueConstraint('key_hash', 'purpose'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class FixRequest(Base):
    __tablename__ = 'handover_fix_requests'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), index=True, nullable=False)
    raised_by_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default='OPEN', nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class InspectionAccess(Base):
    """Seller-approved, time-limited access for a specific agent principal and asset."""
    __tablename__ = 'inspection_accesses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    asset_id: Mapped[str] = mapped_column(ForeignKey('listing_assets.id'), index=True, nullable=False)
    approved_by_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    principal_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(240), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class ListingAiDraft(Base):
    """Legacy v0.3 draft records kept exclusively for data-preserving migrations. No API uses this."""
    __tablename__ = 'listing_ai_drafts'
    __table_args__ = (UniqueConstraint('listing_id', 'input_fingerprint'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='RUNNING', nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GithubConnection(Base):
    """Only the owner can use their encrypted GitHub App user credentials."""
    __tablename__ = 'github_connections'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_login: Mapped[str] = mapped_column(String(120), nullable=False)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class ProjectImport(Base):
    """Private source snapshot staged for a single seller's eventual listing."""
    __tablename__ = 'project_imports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    listing_id: Mapped[str | None] = mapped_column(ForeignKey('listings.id'), index=True)
    source_type: Mapped[str] = mapped_column(String(12), nullable=False)
    source_label: Mapped[str] = mapped_column(String(220), nullable=False)
    source_private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revision_sha: Mapped[str | None] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    object_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    malware_status: Mapped[str] = mapped_column(String(24), nullable=False)
    analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='STAGED', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ListingSourceSummary(Base):
    """Public-safe technical summary; no private repository name or source paths."""
    __tablename__ = 'listing_source_summaries'
    listing_id: Mapped[str] = mapped_column(ForeignKey('listings.id'), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey('project_imports.id'), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(12), nullable=False)
    analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
