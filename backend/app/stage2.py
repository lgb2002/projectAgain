"""Stage 2 API. External agents are separate services and access this marketplace through scoped APIs.

All agent tools call this server with narrow bearer grants. This module contains
NO LLM code, no agent webserver, no execution of seller uploads, and NO payments.
"""
import hashlib
import os
import secrets
import smtplib
from datetime import timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session

from .db import get_db
from .models import (Listing, ListingAsset, AssetShare, DownloadTicket, Notification,
                     InspectionReport, Transaction, FixRequest, PasswordResetToken,
                     InspectionAccess, Offer,
                     SecurityThrottle, User, ServiceGrant, now)
from .private_storage import upload as store_upload, download as store_download, delete as store_delete, StorageUnavailable
from .static_screen import screen, RejectedFile, MAX_FILE
from .malware_scan import scan_bytes
from .security import auth_context, human, allowed, hash_password
from .main import must_listing, must_tx, fail, audit, view, output, admin_only

router = APIRouter(prefix='/api/v1', tags=['Phase 2'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TicketBody(Strict):
    token: str = Field(min_length=20, max_length=128)


class ShareCreate(Strict):
    transaction_id: str
    expires_in_hours: int = Field(default=12, ge=1, le=48)


class Visibility(Strict):
    is_public: bool


class FixCreate(Strict):
    description: str = Field(min_length=10, max_length=2000)


class FixResolve(Strict):
    status: str
    resolution_note: str = Field(min_length=3, max_length=2000)


class InspectionAccessCreate(Strict):
    principal_user_id: str = Field(min_length=36, max_length=36)
    purpose: str = Field(min_length=10, max_length=240)
    expires_in_hours: int = Field(default=3, ge=1, le=12)
    consent: bool


class PasswordResetRequest(Strict):
    email: str = Field(min_length=5, max_length=320)


class PasswordResetConfirm(Strict):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


def _clean(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


from .notifications_v07 import notify


def throttle(db: Session, key: str, purpose: str, seconds: int):
    """Cooldown for account operations; deliberately stores only a digest."""
    token = hashlib.sha256((purpose + ':' + key.strip().lower()).encode()).hexdigest()
    row = db.scalar(select(SecurityThrottle).where(SecurityThrottle.key_hash==token,
                                                     SecurityThrottle.purpose==purpose))
    if row and (_clean(row.last_at) + timedelta(seconds=seconds) > now()):
        fail(429, '너무 자주 요청했습니다. 잠시 후 다시 시도하세요.')
    if row: row.last_at = now()
    else: db.add(SecurityThrottle(key_hash=token,purpose=purpose,last_at=now()))
    db.flush()


def _asset_visible_to(db, asset: ListingAsset, ctx):
    listing = db.get(Listing, asset.listing_id)
    if not listing or listing.status=='REMOVED':return False
    if ctx['kind']!='session':return False
    if ctx['user'].role=='ADMIN' or listing.seller_id==ctx['user'].id:return True
    if asset.upload_status!='APPROVED':return False
    # Seller explicitly shares a vetted asset with one demo transaction buyer.
    shares=db.scalars(select(AssetShare).where(AssetShare.asset_id==asset.id,
                  AssetShare.recipient_user_id==ctx['user'].id,
                  AssetShare.revoked_at.is_(None))).all()
    for share in shares:
        if _clean(share.expires_at)<=now():continue
        tx=db.get(Transaction, share.transaction_id)
        if tx and tx.buyer_id==ctx['user'].id and tx.seller_id==listing.seller_id and tx.is_demo and tx.status not in ('CANCELLED','DISPUTED'):
            return True
    return False


@router.get('/system/storage-status')
def storage_status(ctx=Depends(human)):
    # No bucket name, filesystem paths, or credentials exposed.
    from .private_storage import storage_kind
    try: return {'configured':True,'backend':storage_kind(),'automatic_malware_scan':False,
                 'source_execution':False,'max_file_bytes':MAX_FILE}
    except StorageUnavailable: return {'configured':False,'automatic_malware_scan':False,'source_execution':False}


@router.post('/listings/{listing_id}/assets/upload',status_code=201)
async def upload_asset(listing_id: str, request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db), ctx=Depends(human)):
    listing=must_listing(db,listing_id)
    if listing.seller_id!=ctx['user'].id:fail(404,'매물이 없습니다.')
    if listing.status in ('CLOSED','RESERVED','REMOVED'):fail(409,'이 상태에서는 파일을 추가할 수 없습니다.')
    # Small fixed-size marketplace: prevent unlimited object-storage charges.
    existing=db.scalar(select(func.count()).select_from(ListingAsset).where(ListingAsset.listing_id==listing.id)) or 0
    if existing>=20:fail(429,'매물당 첨부 파일은 최대 20개입니다.')
    used=db.scalar(select(func.coalesce(func.sum(ListingAsset.size_bytes),0))
                   .select_from(ListingAsset).join(Listing,Listing.id==ListingAsset.listing_id)
                   .where(Listing.seller_id==ctx['user'].id)) or 0
    if used>=100*1024*1024:fail(429,'계정당 비공개 파일 용량 제한에 도달했습니다.')
    file_name=(file.filename or '').replace('\\','/').rsplit('/',1)[-1]
    content=await file.read(MAX_FILE+1)
    try: scanned=screen(file_name,content)
    except RejectedFile as exc:fail(422,str(exc))
    malware_status, malware_note = scan_bytes(content)
    if malware_status=='INFECTED':fail(422,'악성코드 탐지로 업로드가 차단됐습니다.')
    if used+len(content)>100*1024*1024:fail(429,'계정당 최대 파일 저장 용량은 100MB입니다.')
    sha=hashlib.sha256(content).hexdigest()
    key=f'private/{listing.id}/{uuid4().hex}'
    try:store_upload(key,content)
    except (StorageUnavailable,OSError):fail(503,'비공개 파일 저장소를 사용할 수 없습니다.')
    row=ListingAsset(listing_id=listing.id,asset_type='SOURCE_ARCHIVE' if file_name.lower().endswith('.zip') else 'DOCUMENT',
                     file_name=file_name,private_object_key=key,content_type='application/octet-stream',
                     size_bytes=len(content),checksum_sha256=sha,visibility='PRIVATE_SELLER',
                     upload_status='QUARANTINED',malware_scan_status=malware_status,uploaded_by=ctx['user'].id)
    db.add(row);db.flush()
    audit(db,ctx,'asset.upload.quarantined','listing_asset',row.id,new={'size_bytes':len(content),'sha256':sha,'static_screen':scanned,'malware_scan_status':malware_status},demo=listing.is_demo)
    try:db.commit()
    except Exception:
        db.rollback()
        try:store_delete(key)
        except Exception:pass
        raise
    return {'id':row.id,'file_name':row.file_name,'size_bytes':len(content),'checksum_sha256':sha,
            'upload_status':'QUARANTINED','static_screen':scanned,'malware_scan_status':malware_status,'malware_scan_note':malware_note,
            'warning':'정적 파일 형식 검사만 수행했습니다. 악성코드 검사는 아직 수행하지 않았으며 실행 안전성이 보장되지 않습니다.'}


@router.post('/assets/{asset_id}/static-inspections',status_code=201)
def static_inspect_asset(asset_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    asset=db.get(ListingAsset,asset_id)
    if not asset:fail(404,'자료를 찾을 수 없습니다.')
    listing=must_listing(db,asset.listing_id)
    if listing.seller_id!=ctx['user'].id and ctx['user'].role!='ADMIN':fail(404,'자료를 찾을 수 없습니다.')
    if not asset.file_name.lower().endswith('.zip'):fail(422,'정적 검사 대상은 ZIP 소스코드입니다.')
    from .static_inspector import inspect_zip
    try:
        content=store_download(asset.private_object_key)
        if hashlib.sha256(content).hexdigest()!=asset.checksum_sha256:fail(409,'저장 파일의 체크섬이 일치하지 않습니다.')
        result=inspect_zip(content)
    except (StorageUnavailable,OSError):fail(503,'파일 저장소에 접근할 수 없습니다.')
    row=InspectionReport(listing_id=listing.id,report_type='STATIC',verdict=result['verdict'],
                         reviewer_kind='RULE_ENGINE',submitted_by_user_id=ctx['user'].id,
                         findings=result['findings'],evidence_refs=[],source_version_sha256=asset.checksum_sha256,
                         is_public=False)
    db.add(row);db.flush()
    audit(db,ctx,'asset.static_inspect','inspection',row.id,new={'asset_id':asset.id,'verdict':row.verdict},demo=listing.is_demo)
    db.commit()
    return {'id':row.id,'listing_id':listing.id,'verdict':row.verdict,'findings':row.findings,
            'level':result['level'],'source_version_sha256':row.source_version_sha256,
            'warning':'정적 구조·의존성만 확인했습니다. 코드 실행·악성코드 검증·양도 가능성 판단을 하지 않았습니다.'}


@router.get('/assets/{asset_id}')
def asset_detail(asset_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    a=db.get(ListingAsset,asset_id)
    if not a or not _asset_visible_to(db,a,ctx):fail(404,'자료를 찾을 수 없습니다.')
    return view(a,['id','listing_id','asset_type','file_name','size_bytes','checksum_sha256','visibility','upload_status','malware_scan_status','created_at'])


@router.post('/assets/{asset_id}/download-intents',status_code=201)
def issue_download_ticket(asset_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    asset=db.get(ListingAsset,asset_id)
    if not asset or not _asset_visible_to(db,asset,ctx):fail(404,'다운로드 권한이 없습니다.')
    if asset.upload_status!='APPROVED':fail(409,'검토가 완료되지 않은 파일은 다운로드할 수 없습니다.')
    token=secrets.token_urlsafe(40)
    row=DownloadTicket(asset_id=asset.id,issued_to_user_id=ctx['user'].id,
                       token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=now()+timedelta(minutes=3))
    db.add(row);db.flush()
    audit(db,ctx,'asset.download.ticket','listing_asset',asset.id,new={'ticket_id':row.id},demo=True)
    db.commit()
    return {'ticket':token,'expires_at':row.expires_at.isoformat(),'single_use':True}


@router.post('/assets/redeem')
def redeem_download(data:TicketBody,db:Session=Depends(get_db),ctx=Depends(human)):
    h=hashlib.sha256(data.token.encode()).hexdigest()
    ticket=db.scalar(select(DownloadTicket).where(DownloadTicket.token_hash==h))
    if not ticket or ticket.issued_to_user_id!=ctx['user'].id:fail(404,'다운로드 요청이 유효하지 않습니다.')
    if ticket.revoked_at or ticket.redeemed_at or _clean(ticket.expires_at)<=now():fail(410,'다운로드 요청이 만료되었거나 이미 사용됐습니다.')
    asset=db.get(ListingAsset,ticket.asset_id)
    if not asset or asset.upload_status!='APPROVED' or not _asset_visible_to(db,asset,ctx):fail(403,'파일 열람 권한이 없습니다.')
    updated=db.execute(update(DownloadTicket).where(DownloadTicket.id==ticket.id,
                   DownloadTicket.redeemed_at.is_(None),DownloadTicket.revoked_at.is_(None))
                   .values(redeemed_at=now()))
    if updated.rowcount!=1:fail(410,'이미 사용된 요청입니다.')
    audit(db,ctx,'asset.download.redeem','listing_asset',asset.id,new={'ticket_id':ticket.id},demo=True)
    db.commit()
    try:data_bytes=store_download(asset.private_object_key)
    except (StorageUnavailable,OSError):fail(503,'파일을 불러올 수 없습니다.')
    if hashlib.sha256(data_bytes).hexdigest()!=asset.checksum_sha256:fail(409,'파일 무결성 검사에 실패했습니다.')
    ascii_name='project-asset'+('.zip' if asset.file_name.lower().endswith('.zip') else '.bin')
    return Response(content=data_bytes, media_type='application/octet-stream',
          headers={'Content-Disposition':f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(asset.file_name)}",
                   'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})


@router.post('/admin/assets/{asset_id}/review')
def review_asset(asset_id:str,data:dict,db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    if data.get('status') not in ('APPROVED','REJECTED'):fail(422,'승인 또는 거부 상태만 허용됩니다.')
    reason=str(data.get('reason','')).strip()
    if len(reason)<5:fail(422,'검토 사유를 5자 이상 기록하세요.')
    asset=db.scalar(select(ListingAsset).where(ListingAsset.id==asset_id).with_for_update())
    if not asset:fail(404,'파일을 찾을 수 없습니다.')
    if asset.upload_status not in ('QUARANTINED','APPROVED'):fail(409,'이 상태는 검토할 수 없습니다.')
    listing=db.get(Listing, asset.listing_id)
    if data['status']=='APPROVED' and asset.malware_scan_status!='CLEAN':
        if os.getenv('APP_ENV','development')=='production' or not listing or not listing.is_demo:
            fail(409,'실거래용 파일은 악성코드 검사 CLEAN 확인 전 배포할 수 없습니다.')
    old=asset.upload_status;asset.upload_status=data['status']
    audit(db,ctx,'asset.review','listing_asset',asset.id,old={'status':old},new={'status':asset.upload_status,'reason':reason})
    notify(db,asset.uploaded_by,'ASSET_REVIEW','등록한 파일의 검토 상태가 변경됐습니다.','listing_asset',asset.id)
    db.commit();return {'asset_id':asset.id,'upload_status':asset.upload_status,
             'disclaimer':'관리자 자료 공개 승인은 악성코드 검사나 코드 안전성 인증이 아닙니다.'}


@router.get('/admin/assets')
def admin_assets(db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    rows=db.scalars(select(ListingAsset).order_by(ListingAsset.created_at.desc()).limit(100)).all()
    return {'items':[view(r,['id','listing_id','file_name','size_bytes','checksum_sha256','upload_status','malware_scan_status','created_at']) for r in rows]}


@router.post('/assets/{asset_id}/shares',status_code=201)
def share_asset(asset_id:str,data:ShareCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    asset=db.get(ListingAsset,asset_id)
    if not asset:fail(404,'파일을 찾을 수 없습니다.')
    listing=must_listing(db,asset.listing_id)
    if listing.seller_id!=ctx['user'].id:fail(404,'파일을 찾을 수 없습니다.')
    if asset.upload_status!='APPROVED':fail(409,'검토되지 않은 자료는 공유할 수 없습니다.')
    tx=db.get(Transaction,data.transaction_id)
    if not tx or tx.listing_id!=listing.id or tx.seller_id!=ctx['user'].id or not tx.is_demo or tx.status in ('CANCELLED','DISPUTED','DEMO_COMPLETED'):
        fail(409,'활성화된 본인 시연 거래에서만 공유할 수 있습니다.')
    from .deal_models import DealAgreement
    agreement=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    if not agreement or agreement.status!='ACKNOWLEDGED':
        fail(409,'양측이 모의 거래 조건을 확인해야 원본 자료를 공유할 수 있습니다.')
    from .deal_models import DealCancellation
    if db.scalar(select(DealCancellation.id).where(DealCancellation.transaction_id==tx.id,DealCancellation.status=='PENDING')):
        fail(409,'거래 취소 요청 처리 중에는 새 자료를 공유할 수 없습니다.')
    row=AssetShare(asset_id=asset.id,transaction_id=tx.id,owner_user_id=ctx['user'].id,
                   recipient_user_id=tx.buyer_id,expires_at=now()+timedelta(hours=data.expires_in_hours))
    db.add(row);db.flush()
    audit(db,ctx,'asset.share','asset_share',row.id,new={'recipient_user_id':tx.buyer_id,'expires_at':row.expires_at.isoformat()})
    notify(db,tx.buyer_id,'ASSET_SHARED','시연용 인수인계 자료가 공유됐습니다.','transaction',tx.id)
    db.commit();return {'id':row.id,'asset_id':asset.id,'transaction_id':tx.id,'expires_at':row.expires_at.isoformat(),
                        'warning':'시연용 파일 접근이며 실제 결제나 저작재산권 이전을 의미하지 않습니다.'}


@router.get('/transactions/{transaction_id}/shared-assets')
def shared_assets(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=must_tx(db,transaction_id,ctx)
    rows=db.scalars(select(AssetShare).where(AssetShare.transaction_id==tx.id,
                            AssetShare.revoked_at.is_(None))).all()
    items=[]
    for r in rows:
        asset=db.get(ListingAsset,r.asset_id)
        if asset and _asset_visible_to(db,asset,ctx):
            items.append({'share_id':r.id,'asset_id':asset.id,'file_name':asset.file_name,
                          'size_bytes':asset.size_bytes,'checksum_sha256':asset.checksum_sha256,
                          'expires_at':r.expires_at.isoformat()})
    return {'items':items}


@router.post('/assets/shares/{share_id}/revoke')
def revoke_share(share_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    share=db.get(AssetShare,share_id)
    if not share or share.owner_user_id!=ctx['user'].id:fail(404,'공유 내역을 찾을 수 없습니다.')
    share.revoked_at=now()
    audit(db,ctx,'asset.share.revoke','asset_share',share.id)
    db.commit();return {'ok':True}


@router.post('/listings/{listing_id}/inspection-reports/{report_id}/visibility')
def publish_report(listing_id:str,report_id:str,data:Visibility,db:Session=Depends(get_db),ctx=Depends(human)):
    listing=must_listing(db,listing_id)
    if listing.seller_id!=ctx['user'].id and ctx['user'].role!='ADMIN':fail(404,'보고서를 찾을 수 없습니다.')
    row=db.get(InspectionReport,report_id)
    if not row or row.listing_id!=listing_id:fail(404,'보고서를 찾을 수 없습니다.')
    # A buyer's private inspection notes must not be published by a seller without the buyer's separate consent.
    if data.is_public and row.submitted_by_user_id not in (listing.seller_id,) and ctx['user'].role!='ADMIN':
        fail(403,'매수자가 제출한 비공개 실사 보고서는 별도 공개 동의 없이 게시할 수 없습니다.')
    # Findings can contain proprietary information; seller must explicitly approve.
    row.is_public=data.is_public
    audit(db,ctx,'inspection.visibility','inspection',row.id,new={'is_public':row.is_public},demo=listing.is_demo)
    db.commit();return {'id':row.id,'is_public':row.is_public,
                         'notice':'에이전트 보고서는 플랫폼 또는 전문가의 인증이 아닙니다.'}


@router.get('/agent/context')
def agent_context(db:Session=Depends(get_db),ctx=Depends(auth_context)):
    if ctx['kind']!='agent':fail(403,'외부 에이전트 Bearer 토큰이 필요합니다.')
    return {'api_version':'v1','principal_user_id':ctx['user'].id,'scopes':ctx['scopes'],
            'no_agent_server_required':True,'human_approval_for_offer':True,
            'automatic_code_execution':False,'live_payment_enabled':False,
            'limits':{'inspections_per_report':100,'offer_draft_requires_approval':True},
            'hint':'Streamlit은 requests 라이브러리로 이 API를 직접 호출합니다.'}


@router.get('/notifications')
def my_notifications(limit:int=Query(default=100,ge=1,le=100),offset:int=Query(default=0,ge=0),db:Session=Depends(get_db),ctx=Depends(human)):
    rows=db.scalars(select(Notification).where(Notification.user_id==ctx['user'].id)
                         .order_by(Notification.created_at.desc(),Notification.id.desc())
                         .offset(offset).limit(limit+1)).all()
    has_more=len(rows)>limit
    rows=rows[:limit]
    unread=db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id==ctx['user'].id,Notification.read_at.is_(None))) or 0
    return {'items':[view(r,['id','kind','title','resource_type','resource_id','read_at','created_at']) for r in rows],
            'unread':unread,'has_more':has_more}


@router.post('/notifications/{notification_id}/read')
def read_notification(notification_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    row=db.get(Notification,notification_id)
    if not row or row.user_id!=ctx['user'].id:fail(404,'알림이 없습니다.')
    row.read_at=now()
    db.commit();return {'ok':True}


@router.get('/transactions/{transaction_id}/fix-requests')
def list_fix_requests(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    allowed(ctx,'handover:read')
    must_tx(db,transaction_id,ctx)
    rows=db.scalars(select(FixRequest).where(FixRequest.transaction_id==transaction_id)
                    .order_by(FixRequest.created_at.desc())).all()
    return {'items':[view(r,['id','transaction_id','description','status','resolution_note','created_at','updated_at']) for r in rows]}


@router.post('/transactions/{transaction_id}/fix-requests',status_code=201)
def create_fix_request(transaction_id:str,data:FixCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=must_tx(db,transaction_id,ctx)
    if tx.buyer_id!=ctx['user'].id:fail(403,'구매자만 보완 요청을 제출할 수 있습니다.')
    if tx.status in ('CANCELLED','DEMO_COMPLETED'):fail(409,'종료된 거래입니다.')
    row=FixRequest(transaction_id=tx.id,raised_by_user_id=ctx['user'].id,seller_id=tx.seller_id,
                   description=data.description)
    db.add(row);db.flush()
    audit(db,ctx,'handover.fix_request','fix_request',row.id)
    notify(db,tx.seller_id,'FIX_REQUEST','구매자가 인수인계 보완을 요청했습니다.','transaction',tx.id)
    db.commit();return view(row,['id','transaction_id','description','status','resolution_note','created_at'])


@router.post('/transactions/{transaction_id}/fix-requests/{request_id}/resolve')
def resolve_fix_request(transaction_id:str,request_id:str,data:FixResolve,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=must_tx(db,transaction_id,ctx)
    if tx.seller_id!=ctx['user'].id:fail(403,'판매자만 처리할 수 있습니다.')
    row=db.get(FixRequest,request_id)
    if not row or row.transaction_id!=tx.id:fail(404,'보완 요청이 없습니다.')
    if row.status!='OPEN':fail(409,'이미 처리된 보완 요청입니다.')
    if data.status not in ('RESOLVED','DECLINED'):fail(422,'처리 상태를 확인하세요.')
    row.status=data.status;row.resolution_note=data.resolution_note
    # RESOLVED is only the seller's claim. The buyer must confirm separately.

    audit(db,ctx,'handover.fix_request.resolve','fix_request',row.id,new={'status':row.status})
    notify(db,tx.buyer_id,'FIX_REQUEST_RESULT','인수인계 보완 요청에 응답이 등록됐습니다.','transaction',tx.id)
    db.commit();return view(row,['id','transaction_id','description','status','resolution_note'])


@router.post('/transactions/{transaction_id}/fix-requests/{request_id}/confirm')
def confirm_fix_request(transaction_id:str,request_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=must_tx(db,transaction_id,ctx)
    if tx.buyer_id != ctx['user'].id:fail(403,'구매자만 보완 완료를 확인할 수 있습니다.')
    if tx.status in ('CANCELLED','DEMO_COMPLETED'):fail(409,'종료된 거래입니다.')
    row=db.scalar(select(FixRequest).where(FixRequest.id==request_id,FixRequest.transaction_id==tx.id).with_for_update())
    if not row:fail(404,'보완 요청이 없습니다.')
    if row.status!='RESOLVED':fail(409,'판매자가 보완 완료한 항목만 구매자가 확인할 수 있습니다.')
    row.status='CONFIRMED'
    audit(db,ctx,'handover.fix_request.confirm','fix_request',row.id,new={'status':'CONFIRMED'})
    notify(db,tx.seller_id,'FIX_CONFIRMED','구매자가 보완 완료를 최종 확인했습니다.','transaction',tx.id)
    db.commit();return {'id':row.id,'status':row.status}


@router.post('/transactions/{transaction_id}/fix-requests/{request_id}/reopen')
def reopen_fix_request(transaction_id:str,request_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=must_tx(db,transaction_id,ctx)
    if tx.buyer_id != ctx['user'].id:fail(403,'구매자만 보완 요청을 다시 열 수 있습니다.')
    if tx.status in ('CANCELLED','DEMO_COMPLETED'):fail(409,'종료된 거래입니다.')
    row=db.scalar(select(FixRequest).where(FixRequest.id==request_id,FixRequest.transaction_id==tx.id).with_for_update())
    if not row:fail(404,'보완 요청이 없습니다.')
    if row.status not in ('RESOLVED','DECLINED'):fail(409,'현재 상태에서는 다시 열 수 없습니다.')
    row.status='OPEN';row.resolution_note=None
    audit(db,ctx,'handover.fix_request.reopen','fix_request',row.id,new={'status':'OPEN'})
    notify(db,tx.seller_id,'FIX_REOPENED','구매자가 인수인계 보완을 다시 요청했습니다.','transaction',tx.id)
    db.commit();return {'id':row.id,'status':row.status}


@router.post('/assets/{asset_id}/inspection-accesses',status_code=201)
def grant_inspection_access(asset_id:str,data:InspectionAccessCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    if not data.consent:fail(422,'명시적 파일 검사 동의가 필요합니다.')
    asset=db.get(ListingAsset,asset_id)
    if not asset:fail(404,'파일을 찾을 수 없습니다.')
    listing=must_listing(db,asset.listing_id)
    if listing.seller_id!=ctx['user'].id:fail(404,'파일을 찾을 수 없습니다.')
    if asset.upload_status!='APPROVED':fail(409,'관리자 검토 전에는 파일 검사 권한을 부여할 수 없습니다.')
    if os.getenv('APP_ENV','development')=='production' and asset.malware_scan_status!='CLEAN':
        fail(409,'운영 환경에서는 악성코드 검사 CLEAN 확인이 필요합니다.')
    principal=db.get(User,data.principal_user_id)
    if not principal or not principal.is_active:fail(404,'대상 사용자를 찾지 못했습니다.')
    if principal.id != ctx['user'].id:
        # Consent to a specific buyer who has interacted with this listing only.
        relationship=db.scalar(select(Offer.id).where(Offer.listing_id==listing.id,Offer.buyer_id==principal.id).limit(1))
        tx_relationship=db.scalar(select(Transaction.id).where(Transaction.listing_id==listing.id,
                Transaction.buyer_id==principal.id).limit(1))
        if not relationship and not tx_relationship:
            fail(403,'이 매물에 제안하거나 거래에 참여한 사용자에게만 권한을 줄 수 있습니다.')
    # Revoke an earlier authorization to prevent accumulating open grants.
    for prior in db.scalars(select(InspectionAccess).where(InspectionAccess.asset_id==asset.id,
                      InspectionAccess.principal_user_id==principal.id,
                      InspectionAccess.revoked_at.is_(None))).all():
        prior.revoked_at=now()
    row=InspectionAccess(asset_id=asset.id,approved_by_user_id=ctx['user'].id,
                         principal_user_id=principal.id,purpose=data.purpose,
                         expires_at=now()+timedelta(hours=data.expires_in_hours))
    db.add(row);db.flush()
    audit(db,ctx,'asset.inspection_access.grant','inspection_access',row.id,
          new={'asset_id':asset.id,'principal_user_id':principal.id,'expires_at':row.expires_at.isoformat()},demo=listing.is_demo)
    db.commit()
    return {'id':row.id,'asset_id':asset.id,'principal_user_id':principal.id,
            'purpose':row.purpose,'expires_at':row.expires_at.isoformat(),
            'warning':'외부 Streamlit 에이전트가 파일 원본을 읽을 수 있습니다. 신뢰하는 대상에게만 동의하세요.'}


@router.get('/assets/{asset_id}/inspection-accesses')
def inspection_accesses(asset_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    asset=db.get(ListingAsset,asset_id)
    if not asset:fail(404,'파일을 찾을 수 없습니다.')
    listing=must_listing(db,asset.listing_id)
    if listing.seller_id!=ctx['user'].id:fail(404,'파일을 찾을 수 없습니다.')
    rows=db.scalars(select(InspectionAccess).where(InspectionAccess.asset_id==asset.id)
            .order_by(InspectionAccess.created_at.desc()).limit(50)).all()
    return {'items':[view(r,['id','asset_id','principal_user_id','purpose','expires_at','revoked_at','created_at']) for r in rows]}


@router.post('/assets/inspection-accesses/{access_id}/revoke')
def revoke_inspection_access(access_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    row=db.scalar(select(InspectionAccess).where(InspectionAccess.id==access_id).with_for_update())
    if not row or row.approved_by_user_id!=ctx['user'].id:fail(404,'검사 접근 권한이 없습니다.')
    row.revoked_at=now()
    audit(db,ctx,'asset.inspection_access.revoke','inspection_access',row.id)
    db.commit();return {'ok':True}


@router.get('/agent/listings/{listing_id}/inspection-assets')
def agent_approved_inspection_assets(listing_id:str,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    """Only the caller's currently approved file metadata. Never enumerate other private assets."""
    if ctx['kind']!='agent':fail(403,'에이전트 위임 토큰이 필요합니다.')
    allowed(ctx,'asset:inspect')
    listing=must_listing(db,listing_id)
    q=(select(ListingAsset,InspectionAccess)
       .join(InspectionAccess,InspectionAccess.asset_id==ListingAsset.id)
       .where(ListingAsset.listing_id==listing.id,
              ListingAsset.upload_status=='APPROVED',
              InspectionAccess.principal_user_id==ctx['user'].id,
              InspectionAccess.revoked_at.is_(None),InspectionAccess.expires_at>now())
       .order_by(InspectionAccess.created_at.desc()).limit(100))
    rows=db.execute(q).all()
    items=[];known=set()
    for asset,approval in rows:
        if asset.id in known:continue
        if os.getenv('APP_ENV','development')=='production' and asset.malware_scan_status!='CLEAN':continue
        known.add(asset.id)
        items.append({'id':asset.id,'listing_id':asset.listing_id,'file_name':asset.file_name,
                      'asset_type':asset.asset_type,'size_bytes':asset.size_bytes,
                      'checksum_sha256':asset.checksum_sha256,
                      'upload_status':asset.upload_status,'malware_scan_status':asset.malware_scan_status,
                      'approval_expires_at':_clean(approval.expires_at).isoformat(),
                      'inspection_content_path':f'/api/v1/agent/assets/{asset.id}/inspection-content'})
    return {'items':items,'next_cursor':None,'access_policy':'per_asset_seller_approval',
            'note':'노출된 파일은 판매자가 명시적으로 승인한 실사 대상입니다. 무단 실행하지 마세요.'}


@router.get('/agent/assets/{asset_id}/inspection-content')
def agent_inspection_content(asset_id:str,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    # Explicit human seller consent PLUS a scope-restricted bearer token.
    if ctx['kind']!='agent':fail(403,'외부 에이전트 토큰으로만 검사할 수 있습니다.')
    allowed(ctx,'asset:inspect')
    asset=db.get(ListingAsset,asset_id)
    if not asset:fail(404,'자료를 찾을 수 없습니다.')
    listing=must_listing(db,asset.listing_id)
    if asset.upload_status!='APPROVED':fail(403,'승인되지 않은 파일입니다.')
    if os.getenv('APP_ENV','development')=='production' and asset.malware_scan_status!='CLEAN':
        fail(403,'안전 검사가 확인되지 않았습니다.')
    approval=db.scalar(select(InspectionAccess.id).where(
        InspectionAccess.asset_id==asset.id, InspectionAccess.principal_user_id==ctx['user'].id,
        InspectionAccess.revoked_at.is_(None), InspectionAccess.expires_at>now()).limit(1))
    if not approval:fail(404,'판매자가 승인한 실사 접근 권한이 없습니다.')
    try:content=store_download(asset.private_object_key)
    except (StorageUnavailable,OSError):fail(503,'저장소에 접근할 수 없습니다.')
    if hashlib.sha256(content).hexdigest()!=asset.checksum_sha256:fail(409,'파일 무결성 검사가 실패했습니다.')
    audit(db,ctx,'asset.inspection_access.read','listing_asset',asset.id,
          new={'approval_id':approval},demo=listing.is_demo)
    db.commit()
    return Response(content=content,media_type='application/octet-stream',headers={
        'Content-Disposition':'attachment; filename="inspection-asset.bin"',
        'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'})


@router.post('/auth/request-password-reset')
def request_password_reset(data:PasswordResetRequest,request:Request,db:Session=Depends(get_db)):
    email=data.email.strip().lower()
    # Public route must not reveal whether a user email is registered.
    throttle(db,request.client.host if request.client else 'unknown','reset:ip',60)
    throttle(db,email,'reset:email',120)
    user=db.scalar(select(User).where(User.email==email))
    dev_token=None
    if user and user.is_active:
        token=secrets.token_urlsafe(40)
        reset=PasswordResetToken(user_id=user.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                 expires_at=now()+timedelta(minutes=20))
        db.add(reset)
        if os.getenv('SMTP_HOST'):
            base=os.getenv('PUBLIC_BASE_URL','').rstrip('/')
            link=base+'/reset-password?token='+token
            msg=EmailMessage();msg['Subject']='비밀번호 재설정';msg['From']=os.getenv('SMTP_FROM','no-reply@example.invalid')
            msg['To']=user.email;msg.set_content('본인이 요청한 경우에만 20분 안에 아래 주소를 이용하세요.\n'+link)
            try:
                with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=10) as smtp:
                    smtp.starttls();smtp.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD']);smtp.send_message(msg)
            except Exception:fail(503,'메일 발송 환경이 준비되지 않았습니다.')
        elif os.getenv('APP_ENV') == 'test':
            dev_token=token
        else:
            # Never send reset tokens to unauthenticated callers on a public dev preview.
            # No SMTP configured: silently no-op; response stays non-enumerating.
            db.delete(reset)
    db.commit()
    result={'message':'계정이 존재하면 비밀번호 재설정 안내를 전송했습니다.'}
    if dev_token and os.getenv('APP_ENV')=='test':
        result['development_reset_token']=dev_token
    return result


@router.post('/auth/confirm-password-reset')
def confirm_password_reset(data:PasswordResetConfirm,db:Session=Depends(get_db)):
    token_hash=hashlib.sha256(data.token.encode()).hexdigest()
    row=db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash==token_hash).with_for_update())
    if not row or row.used_at or _clean(row.expires_at)<=now():fail(400,'재설정 링크가 만료되었거나 유효하지 않습니다.')
    user=db.get(User,row.user_id)
    if not user or not user.is_active:fail(400,'계정을 찾을 수 없습니다.')
    user.password_hash=hash_password(data.new_password)
    user.auth_version+=1
    row.used_at=now()
    grants=db.scalars(select(ServiceGrant).where(ServiceGrant.principal_user_id==user.id,ServiceGrant.revoked_at.is_(None))).all()
    for grant in grants:grant.revoked_at=now()
    db.commit()
    return {'ok':True,'message':'비밀번호가 변경되었습니다. 다시 로그인해 주세요.'}
