"""Account withdrawal and privacy erasure, with durable private-file deletion queue.

DEMO records retain non-identifying technical IDs for referential integrity only.
Deleting an account never relies on client-provided user IDs or access tokens.
"""
import hashlib
import secrets
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean, select, delete, or_
from sqlalchemy.orm import Mapped, mapped_column, Session
from fastapi import APIRouter, Depends, HTTPException, Response
from .db import Base, get_db
from .models import (now, uid, User, Listing, Favorite, BuyerPreferences, Offer, Transaction, HandoverCheck,
    InspectionReport, AgentAction, ServiceGrant, ListingAsset, ModerationReport, AuditEvent,
    IdempotencyRecord, DownloadTicket, AssetShare, Notification, PasswordResetToken,
    InspectionAccess, ListingAiDraft, GithubConnection, ProjectImport, ListingSourceSummary, FixRequest)
from .marketplace_models import (ListingShowcase, ListingMedia, ListingInquiry,
    NotificationPreference, NotificationEmail)
from .deal_models import DealAgreement, DealCancellation, DealDispute, DealEvent
from .roadmap_models import DevelopmentRoadmap, DevelopmentRoadmapTask
from .v012_models import (OfferThread, SupportCase, SupportMessage, RoadmapBuyerContext, SupportPolicySnapshot)
from .security import human, verify_password, hash_password, COOKIE_NAME

router = APIRouter(prefix='/api/v1', tags=['Privacy'])


class PrivacyErasure(Base):
    __tablename__ = 'privacy_erasures'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    objects_queued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(25), default='OBJECTS_PENDING', nullable=False)


class PrivacyErasureObject(Base):
    __tablename__ = 'privacy_erasure_objects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeleteMyAccount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=1, max_length=200)
    confirmation: str = Field(pattern='^계정 탈퇴$')


def _erasure_counts(db, user_id):
    ids=select(Listing.id).where(Listing.seller_id==user_id)
    return {'listings':len(db.scalars(select(Listing.id).where(Listing.seller_id==user_id)).all()),
            'negotiations':len(db.scalars(select(Offer.id).where(or_(Offer.buyer_id==user_id,Offer.seller_id==user_id))).all()),
            'demo_transactions':len(db.scalars(select(Transaction.id).where(or_(Transaction.buyer_id==user_id,Transaction.seller_id==user_id))).all()),
            'source_archives':len(db.scalars(select(ProjectImport.id).where(ProjectImport.user_id==user_id)).all())}


@router.get('/auth/privacy/summary')
def privacy_summary(db:Session=Depends(get_db),ctx=Depends(human)):
    return {'impact':_erasure_counts(db,ctx['user'].id),
            'terms':'비활성화된 계정으로 전환하고 개인정보·비공개 자료·연결 정보를 삭제합니다. 시연 거래는 취소 또는 종료되며 식별 정보가 제거된 최소 관계 ID는 기록 일관성을 위해 유지됩니다.',
            'storage_deletion':'비공개 객체는 삭제 큐에 기록한 뒤 별도 작업에서 영구 삭제합니다. 백업 및 외부 GitHub App 설치 권한은 별도 관리가 필요합니다.'}


def erase_account(db:Session, user:User):
    """One atomic DB transaction. A separate idempotent cleaner removes storage objects."""
    u=db.scalar(select(User).where(User.id==user.id).with_for_update())
    if not u or not u.is_active or db.get(PrivacyErasure,u.id):
        raise HTTPException(409,'이미 탈퇴했거나 처리 중인 계정입니다.')
    if u.role=='ADMIN':
        raise HTTPException(403,'관리자 계정은 이 화면에서 탈퇴할 수 없습니다. 다른 관리자로 권한을 이관한 후 처리하세요.')
    user_id=u.id; timestamp=now()
    listings=db.scalars(select(Listing).where(Listing.seller_id==user_id)).all()
    listing_ids={x.id for x in listings}
    txs=db.scalars(select(Transaction).where(or_(Transaction.seller_id==user_id,Transaction.buyer_id==user_id))).all()
    tx_ids={x.id for x in txs}
    other_offers=db.scalars(select(Offer).where(or_(Offer.buyer_id==user_id,Offer.seller_id==user_id,
                                                        Offer.proposed_by==user_id))).all()
    offer_ids={x.id for x in other_offers}
    # Deactivate first, removing sessions and bearer grants on the very same commit.
    u.is_active=False;u.auth_version+=1;u.email=f'deleted-{u.id}@invalid.local'
    u.password_hash=hash_password(secrets.token_urlsafe(40));u.email_verified_at=None
    u.deleted_at=timestamp
    db.execute(delete(GithubConnection).where(GithubConnection.user_id==user_id))
    db.execute(delete(BuyerPreferences).where(BuyerPreferences.user_id==user_id))
    db.execute(delete(Favorite).where(Favorite.user_id==user_id))
    db.execute(delete(NotificationPreference).where(NotificationPreference.user_id==user_id))
    for grant in db.scalars(select(ServiceGrant).where(ServiceGrant.principal_user_id==user_id)):
        grant.revoked_at=timestamp;grant.token_hash=secrets.token_hex(32)
        grant.client_id='revoked';grant.scopes=[]
    for item in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id==user_id)):
        item.used_at=timestamp;item.token_hash=secrets.token_hex(32)
    for act in db.scalars(select(AgentAction).where(AgentAction.user_id==user_id)):
        act.status='REJECTED';act.proposed_payload={}
    for idem in db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.actor_id==user_id)):
        idem.response_json={}

    object_keys=set()
    for imp in db.scalars(select(ProjectImport).where(ProjectImport.user_id==user_id)):
        object_keys.add(imp.object_key)
        imp.source_label='삭제된 연결';imp.filename='removed.zip';imp.analysis={};imp.status='ERASED'
        imp.revision_sha=None;imp.checksum_sha256='';imp.size_bytes=0;imp.expires_at=timestamp
    for asset in db.scalars(select(ListingAsset).where(or_(ListingAsset.listing_id.in_(listing_ids),
                                                             ListingAsset.uploaded_by==user_id))):
        object_keys.add(asset.private_object_key)
        asset.file_name='removed';asset.upload_status='DELETED';asset.visibility='PRIVATE_SELLER'
        asset.checksum_sha256='';asset.size_bytes=0
        for ticket in db.scalars(select(DownloadTicket).where(DownloadTicket.asset_id==asset.id)):
            ticket.revoked_at=timestamp
        for share in db.scalars(select(AssetShare).where(AssetShare.asset_id==asset.id)):
            share.revoked_at=timestamp
        for access in db.scalars(select(InspectionAccess).where(InspectionAccess.asset_id==asset.id)):
            access.revoked_at=timestamp;access.purpose='삭제됨'
    # Revoke access to OTHER people's assets, too; deletion applies to all identity-bound grants.
    for ticket in db.scalars(select(DownloadTicket).where(DownloadTicket.issued_to_user_id==user_id)):
        ticket.revoked_at=timestamp;ticket.token_hash=secrets.token_hex(32)
    for share in db.scalars(select(AssetShare).where(or_(AssetShare.owner_user_id==user_id,
                                                       AssetShare.recipient_user_id==user_id))):
        share.revoked_at=timestamp
    for access in db.scalars(select(InspectionAccess).where(or_(InspectionAccess.approved_by_user_id==user_id,
                                                                 InspectionAccess.principal_user_id==user_id))):
        access.revoked_at=timestamp;access.purpose='삭제됨'
    for media in db.scalars(select(ListingMedia).where(ListingMedia.listing_id.in_(listing_ids))):
        object_keys.add(media.object_key);media.caption=''
    for show in db.scalars(select(ListingShowcase).where(ListingShowcase.listing_id.in_(listing_ids))):
        show.demo_url=None;show.video_url=None;show.highlights=[]
    for summary in db.scalars(select(ListingSourceSummary).where(ListingSourceSummary.listing_id.in_(listing_ids))):
        summary.analysis={}
    from .readiness_report import ListingReadinessReport
    for report in db.scalars(select(ListingReadinessReport).where(ListingReadinessReport.listing_id.in_(listing_ids))):
        report.report={'status':'REMOVED','message':'계정 탈퇴로 인수 보고서가 비공개 처리되었습니다.'}
    for li in listings:
        li.title='삭제된 프로젝트';li.description='계정 탈퇴로 게시가 종료되었습니다.'
        li.status='REMOVED';li.verification_status='UNVERIFIED';li.rights_attested=False
        li.tech_stack=[];li.included_assets=[];li.excluded_assets=[];li.known_defects=[];li.required_services=[]
        li.revenue_krw_claimed=None;li.has_revenue=False;li.monthly_cost_estimate_krw=None
        li.handover_days_estimate=None;li.seller_support_days=None;li.version+=1
    for draft in db.scalars(select(ListingAiDraft).where(or_(ListingAiDraft.user_id==user_id,
                                                               ListingAiDraft.listing_id.in_(listing_ids)))):
        draft.result_json=None
    for report in db.scalars(select(InspectionReport).where(or_(InspectionReport.submitted_by_user_id==user_id,
                                                                InspectionReport.listing_id.in_(listing_ids)))):
        report.findings=[];report.evidence_refs=[];report.is_public=False
    for report in db.scalars(select(ModerationReport).where(or_(ModerationReport.reported_by==user_id,
                                                                ModerationReport.listing_id.in_(listing_ids)))):
        report.description=None;report.status='CLOSED'
    for inquiry in db.scalars(select(ListingInquiry).where(or_(ListingInquiry.buyer_id==user_id,
                                                               ListingInquiry.seller_id==user_id,
                                                               ListingInquiry.listing_id.in_(listing_ids)))):
        inquiry.question='삭제된 문의';inquiry.answer=None;inquiry.visibility='PRIVATE';inquiry.hidden_at=timestamp
    for offer in other_offers:
        offer.terms={}
        if offer.status=='PENDING':offer.status='WITHDRAWN';offer.version+=1
    for thread in db.scalars(select(OfferThread).where(or_(OfferThread.buyer_id==user_id,OfferThread.seller_id==user_id))):
        thread.status='CANCELLED';thread.version+=1
    for tx in txs:
        if tx.is_demo and tx.status not in ('CANCELLED','DEMO_COMPLETED'):
            tx.status='CANCELLED';tx.version+=1
        # Completed DEMO history is retained only as non-identifying referential IDs.
        tx.exclusive_guard_listing_id=None
    for policy in db.scalars(select(SupportPolicySnapshot).where(SupportPolicySnapshot.transaction_id.in_(tx_ids))):
        policy.days=0;policy.case_limit=0;policy.scope_codes=[];policy.ends_at=timestamp
        policy.agreement_snapshot_sha256=hashlib.sha256(b'{}').hexdigest()
    for agreement in db.scalars(select(DealAgreement).where(DealAgreement.transaction_id.in_(tx_ids))):
        agreement.snapshot={};agreement.snapshot_sha256=hashlib.sha256(b'{}').hexdigest()
        agreement.status='REDACTED_ACCOUNT_DELETED'
        agreement.buyer_ack_digest=None;agreement.seller_ack_digest=None
    for row in db.scalars(select(HandoverCheck).where(HandoverCheck.transaction_id.in_(tx_ids))):
        row.remarks=None;row.evidence_refs=[];row.description='개인정보 삭제로 인수 자료 비공개'
    for row in db.scalars(select(FixRequest).where(FixRequest.transaction_id.in_(tx_ids))):
        row.description='삭제된 내용';row.resolution_note=None;row.status='CLOSED'
    for row in db.scalars(select(DealCancellation).where(DealCancellation.transaction_id.in_(tx_ids))):
        row.reason='삭제된 내용';row.response_note=None;row.status='RESOLVED'
    for row in db.scalars(select(DealDispute).where(DealDispute.transaction_id.in_(tx_ids))):
        row.description='삭제된 내용';row.evidence_refs=[];row.counterparty_response=None;row.admin_reason=None;row.status='CLOSED'
    for row in db.scalars(select(DealEvent).where(DealEvent.transaction_id.in_(tx_ids))):
        row.details={}
    support_cases=db.scalars(select(SupportCase).where(or_(SupportCase.buyer_id==user_id,SupportCase.seller_id==user_id))).all()
    support_ids={r.id for r in support_cases}
    for row in support_cases:
        row.title='종료된 지원 요청';row.description='삭제된 내용';row.status='CLOSED_UNRESOLVED';row.closed_at=timestamp
    for row in db.scalars(select(SupportMessage).where(or_(SupportMessage.sender_id==user_id,
                                                              SupportMessage.case_id.in_(support_ids)))):
        row.body='탈퇴한 사용자의 메시지가 삭제되었습니다.';row.attachment_refs=[]
    for roadmap in db.scalars(select(DevelopmentRoadmap).where(DevelopmentRoadmap.buyer_id==user_id)):
        for task in db.scalars(select(DevelopmentRoadmapTask).where(DevelopmentRoadmapTask.roadmap_id==roadmap.id)):
            task.buyer_note=''
        context=db.get(RoadmapBuyerContext,roadmap.id)
        if context:context.objective=''
    # Do not leak messages to a remaining counterparty via obsolete listing notifications.
    notification_ids=set(db.scalars(select(Notification.id).where(or_(Notification.user_id==user_id,
        (Notification.resource_type=='listing') & Notification.resource_id.in_(listing_ids),
        (Notification.resource_type=='offer') & Notification.resource_id.in_(offer_ids),
        (Notification.resource_type=='transaction') & Notification.resource_id.in_(tx_ids),
        (Notification.resource_type=='support_case') & Notification.resource_id.in_(support_ids)))).all())
    for mail in db.scalars(select(NotificationEmail).where(or_(NotificationEmail.user_id==user_id,
                                                               NotificationEmail.notification_id.in_(notification_ids)))):
        mail.status='CANCELLED';mail.last_error_code=None
    for msg in db.scalars(select(Notification).where(Notification.id.in_(notification_ids))):
        msg.title='삭제된 알림';msg.read_at=timestamp
    asset_ids={a.id for a in db.scalars(select(ListingAsset).where(ListingAsset.listing_id.in_(listing_ids)))}
    for event in db.scalars(select(AuditEvent).where(or_(AuditEvent.actor_user_id==user_id,
                                                        (AuditEvent.resource_type=='listing') & AuditEvent.resource_id.in_(listing_ids),
                                                        (AuditEvent.resource_type=='listing_asset') & AuditEvent.resource_id.in_(asset_ids),
                                                        (AuditEvent.resource_type=='offer') & AuditEvent.resource_id.in_(offer_ids),
                                                        (AuditEvent.resource_type=='transaction') & AuditEvent.resource_id.in_(tx_ids),
                                                        (AuditEvent.resource_type=='support_case') & AuditEvent.resource_id.in_(support_ids)))):
        event.old_state=None;event.new_state=None
    db.add(PrivacyErasure(user_id=user_id,objects_queued=len(object_keys),
                          status='OBJECTS_PENDING' if object_keys else 'COMPLETED'))
    for key in object_keys:
        # Keys are internal random storage identifiers; never submitted by the browser.
        if key.startswith('private/') and len(key)<=256:
            db.add(PrivacyErasureObject(user_id=user_id,object_key=key))
    db.commit()
    return len(object_keys)


@router.post('/auth/privacy/delete', status_code=202)
def delete_account(data:DeleteMyAccount, response:Response,
                   db:Session=Depends(get_db),ctx=Depends(human)):
    if not verify_password(data.password,ctx['user'].password_hash):
        raise HTTPException(403,'현재 비밀번호가 일치하지 않습니다.')
    count=erase_account(db,ctx['user'])
    response.delete_cookie(COOKIE_NAME,path='/')
    return {'account_disabled':True,'personal_data_redacted':True,'private_objects_queued':count,
            'message':'계정 접속이 종료됐습니다. 비공개 파일은 별도 삭제 워커가 처리합니다.'}


def cleanup_objects(db:Session,limit=100):
    """Idempotent retry. Failure keeps rows pending, no object key logging."""
    from .private_storage import delete as delete_object, StorageUnavailable
    rows=db.scalars(select(PrivacyErasureObject).where(PrivacyErasureObject.status=='PENDING')
                    .order_by(PrivacyErasureObject.created_at).limit(limit)).all()
    completed=0;failed=0
    for row in rows:
        try:
            delete_object(row.object_key)
            row.status='DELETED';row.deleted_at=now();completed+=1
        except (StorageUnavailable,OSError):
            failed+=1
        row.attempts+=1
        db.commit()
    for owner in {r.user_id for r in rows}:
        pending=db.scalar(select(PrivacyErasureObject.id).where(PrivacyErasureObject.user_id==owner,
                                             PrivacyErasureObject.status=='PENDING').limit(1))
        if pending is None:
            request=db.get(PrivacyErasure,owner)
            if request:request.status='COMPLETED';db.commit()
    return {'processed':completed,'failed':failed,'pending':len(rows)-completed}
