"""Human-only DEMO deal room.

Immutable offer/listing snapshots, two-party acknowledgement, bilateral cancellation,
case review and audit timeline. No payment methods, funds, electronic-signature
provider, settlement, refund transfers or IP assignment are performed here.
"""
import hashlib
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from .db import get_db
from .models import Listing, Offer, Transaction, User, AssetShare, now
from .deal_models import DealAgreement, DealCancellation, DealDispute, DealEvent
from .security import human
from .notifications_v07 import notify

router = APIRouter(prefix='/api/v1')

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Acknowledge(Strict):
    snapshot_sha256: str = Field(min_length=64,max_length=64,pattern=r'^[0-9a-f]{64}$')
    understood_demo_only: Literal[True]
    confirmed_terms: Literal[True]

class CancellationCreate(Strict):
    reason: str = Field(min_length=10,max_length=2000)

class CancellationRespond(Strict):
    accept: bool
    response_note: str = Field(min_length=5,max_length=2000)

class DisputeCreate(Strict):
    reason_code: Literal['MISSING_ASSET','MISREPRESENTATION','RIGHTS_CONCERN','HANDOVER_DELAY','OTHER']
    description: str = Field(min_length=15,max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list,max_length=12)

class DisputeRespond(Strict):
    response: str = Field(min_length=10,max_length=3000)

class DisputeDecision(Strict):
    decision: Literal['RESUME_HANDOVER','CANCEL_DEMO']
    reason: str = Field(min_length=15,max_length=3000)


def error(status,message):
    raise HTTPException(status_code=status,detail=message)


def transaction(db,transaction_id,ctx,lock=False,admin=False):
    stmt=select(Transaction).where(Transaction.id==transaction_id)
    if lock:stmt=stmt.with_for_update()
    tx=db.scalar(stmt)
    user=ctx['user']
    if not tx or (user.id not in (tx.buyer_id,tx.seller_id) and not (admin and user.role=='ADMIN')):
        error(404,'거래를 찾을 수 없습니다.')
    if not tx.is_demo:error(403,'이 기능은 모의 거래에만 사용할 수 있습니다.')
    return tx


def only_admin(ctx):
    if ctx['user'].role!='ADMIN':error(403,'관리자 권한이 필요합니다.')


def evt(db,tx,ctx,event_type,details=None):
    db.add(DealEvent(transaction_id=tx.id,actor_id=ctx['user'].id,event_type=event_type,details=details or {}))
    from .main import audit
    audit(db,ctx,'deal.'+event_type.lower(),'transaction',tx.id,new=details or {},demo=True)


def other(tx,user_id):
    return tx.seller_id if tx.buyer_id==user_id else tx.buyer_id


def send(db,tx,user_id,title,kind):
    notify(db,user_id,kind,title,'transaction',tx.id)


def canonical_snapshot(listing:Listing,offer:Offer):
    """Terms are fixed when the offer is accepted; never use mutable live listing for signature."""
    from .offer_terms_v2 import OfferTermsV2
    v2=offer.terms if isinstance(offer.terms,dict) and offer.terms.get('schema_version')==2 else None
    # V2 is already validated on creation. Legacy freeform terms stay as-is.
    return {
        'schema_version':2 if v2 else 1,
        'notice':'거래 조건 확인용 시연 기록입니다. 실제 결제·대금보호·소유권 이전·법률상 전자서명을 실행하지 않습니다.',
        'listing_id':listing.id,
        'listing_version_at_acceptance':listing.version,
        'listing_title':listing.title,
        'accepted_offer_id':offer.id,
        'price_krw':offer.offered_price_krw,
        'rights_type':v2['rights_type'] if v2 else listing.sale_rights_type,
        'inventory_mode':listing.inventory_mode,
        'included_assets':list(v2['included_assets']) if v2 else list(listing.included_assets or []),
        'excluded_assets':list(v2['excluded_assets']) if v2 else list(listing.excluded_assets or []),
        'known_defects':list(listing.known_defects or []),
        'required_services':list(listing.required_services or []),
        'handover_days_estimate':listing.handover_days_estimate,
        'seller_support_days':v2['support']['days'] if v2 else listing.seller_support_days,
        'support_terms':v2['support'] if v2 else None,
        'structured_terms_verified':bool(v2),
        'offer_terms':offer.terms or {},
        'payment_state':'NOT_AVAILABLE',
        'settlement_state':'NOT_AVAILABLE',
        'ownership_transfer_state':'NOT_PERFORMED',
    }


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()


def prepare_agreement(db,tx,ctx=None):
    existing=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    if existing:return existing
    offer=db.get(Offer,tx.accepted_offer_id)
    listing=db.get(Listing,tx.listing_id)
    if not offer or not listing:error(409,'거래의 원본 제안 또는 매물 정보를 확인할 수 없습니다.')
    snap=canonical_snapshot(listing,offer)
    agreement=DealAgreement(transaction_id=tx.id,offer_id=offer.id,snapshot=snap,snapshot_sha256=digest(snap))
    db.add(agreement)
    db.flush()
    from .v012_support import policy_for
    policy_for(db,tx,create=True)
    if ctx:evt(db,tx,ctx,'AGREEMENT_PREPARED',{'digest':agreement.snapshot_sha256})
    return agreement


def agreement_view(a):
    if a is None:return None
    return {'id':a.id,'transaction_id':a.transaction_id,'snapshot':a.snapshot,'snapshot_sha256':a.snapshot_sha256,
            'status':a.status,'buyer_ack_at':a.buyer_ack_at,'seller_ack_at':a.seller_ack_at,'created_at':a.created_at}


def closed(tx):
    if tx.status in ('CANCELLED','DEMO_COMPLETED'):error(409,'이미 종료된 모의 거래입니다.')


def cancellation_view(c):
    return {'id':c.id,'transaction_id':c.transaction_id,'requested_by':c.requested_by,'reason':c.reason,
            'status':c.status,'responded_by':c.responded_by,'response_note':c.response_note,
            'created_at':c.created_at,'resolved_at':c.resolved_at}


def dispute_view(d):
    return {'id':d.id,'transaction_id':d.transaction_id,'opened_by':d.opened_by,'reason_code':d.reason_code,
            'description':d.description,'evidence_refs':d.evidence_refs,'status':d.status,
            'counterparty_response':d.counterparty_response,'counterparty_responded_at':d.counterparty_responded_at,
            'admin_decision':d.admin_decision,'admin_reason':d.admin_reason,
            'resolved_at':d.resolved_at,'created_at':d.created_at}


def cancel_demo(db,tx):
    """Releases a one-time listing; never refunds or reverses downloaded copies."""
    closed(tx)
    tx.status='CANCELLED';tx.version+=1
    # No listing state changes: cancelling a DEMO must never reactivate a genuine reservation.
    tx.exclusive_guard_listing_id=None
    for share in db.scalars(select(AssetShare).where(AssetShare.transaction_id==tx.id,AssetShare.revoked_at.is_(None))).all():
        share.revoked_at=now()


@router.get('/transactions/{transaction_id}/agreement')
def get_agreement(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx)
    a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    return {'agreement':agreement_view(a),'legacy_requires_preparation':a is None,'payments_enabled':False}


@router.get('/transactions/{transaction_id}/agreement/document')
def export_demo_terms(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    """Download a fixed, UTF-8 record of demo terms; NOT a legal agreement."""
    tx=transaction(db,transaction_id,ctx)
    a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    if not a:error(404,'거래 조건 기록이 아직 없습니다.')
    snap=a.snapshot
    lines=[
        'ProjectAgain - 모의 거래 조건 확인서',
        '================================',
        '본 문서는 시연용 조건 기록이며 법적 효력이 보장되는 전자계약서가 아닙니다.',
        '대금 지급·환불·정산·저작재산권 양도 또는 소유권 이전이 실행되지 않습니다.',
        '',
        f'거래 ID: {tx.id}',
        f'확정 제안 ID: {a.offer_id}',
        f'매물명: {snap["listing_title"]}',
        f'가상 거래금액: {snap["price_krw"]:,}원 (청구되지 않음)',
        f'판매자 진술 권리유형: {snap["rights_type"]}',
        f'예상 인계기간: {snap["handover_days_estimate"] if snap["handover_days_estimate"] is not None else "미기재"}일',
        f'예상 지원기간: {snap["seller_support_days"] if snap["seller_support_days"] is not None else "미기재"}일',
        '', '포함 자산:',
        *[f' - {v}' for v in snap.get('included_assets',[])],
        '', '제외 자산:',
        *[f' - {v}' for v in snap.get('excluded_assets',[])],
        '', '알려진 결함:',
        *[f' - {v}' for v in snap.get('known_defects',[])],
        '', '외부 서비스:',
        *[f' - {v}' for v in snap.get('required_services',[])],
        '', '수락된 제안의 추가 조건:',
        json.dumps(snap.get('offer_terms',{}),ensure_ascii=False,sort_keys=True,indent=2),
        '',f'조건 고정 해시 (SHA-256): {a.snapshot_sha256}',
        f'구매자 시연 확인: {a.buyer_ack_at.isoformat() if a.buyer_ack_at else "미확인"}',
        f'판매자 시연 확인: {a.seller_ack_at.isoformat() if a.seller_ack_at else "미확인"}',
        f'확인 상태: {a.status}',
        '', '이 확인 이력은 법적 전자서명 인증이나 거래대금 지급 사실의 증명이 아닙니다.',
    ]
    content='\ufeff'+'\n'.join(lines)+'\n'
    return Response(content=content.encode('utf-8'),media_type='text/plain; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="projectagain-demo-terms-{tx.id[:8]}.txt"',
        'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.post('/transactions/{transaction_id}/agreement/prepare')
def prepare(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx,lock=True)
    closed(tx)
    if tx.status=='DISPUTED':error(409,'분쟁 중에는 거래 조건을 준비할 수 없습니다.')
    a=prepare_agreement(db,tx,ctx)
    db.commit()
    return {'agreement':agreement_view(a),'payments_enabled':False}


@router.post('/transactions/{transaction_id}/agreement/acknowledge')
def acknowledge(transaction_id:str,data:Acknowledge,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx,lock=True)
    closed(tx)
    if tx.status=='DISPUTED':error(409,'분쟁 처리 후 확인할 수 있습니다.')
    a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id).with_for_update())
    if not a:error(409,'먼저 거래 조건 기록을 생성해 주세요.')
    if a.status=='VOID':error(409,'무효 처리된 거래 조건입니다.')
    if data.snapshot_sha256!=a.snapshot_sha256:error(409,'거래 조건이 일치하지 않습니다. 문서를 다시 열어 확인하세요.')
    buyer=ctx['user'].id==tx.buyer_id
    if (a.buyer_ack_at if buyer else a.seller_ack_at):error(409,'이미 확인한 계약 기록입니다.')
    if buyer:
        a.buyer_ack_at=now();a.buyer_ack_digest=data.snapshot_sha256
    else:
        a.seller_ack_at=now();a.seller_ack_digest=data.snapshot_sha256
    if a.buyer_ack_at and a.seller_ack_at:a.status='ACKNOWLEDGED'
    evt(db,tx,ctx,'AGREEMENT_ACKNOWLEDGED',{'party':'BUYER' if buyer else 'SELLER','digest':a.snapshot_sha256})
    send(db,tx,other(tx,ctx['user'].id),'상대방이 모의 거래 조건을 확인했습니다.','DEAL_AGREEMENT')
    db.commit()
    return {'agreement':agreement_view(a),'payments_enabled':False}


@router.get('/transactions/{transaction_id}/deal-events')
def deal_events(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx)
    rows=db.scalars(select(DealEvent).where(DealEvent.transaction_id==tx.id).order_by(DealEvent.created_at,DealEvent.id).limit(200)).all()
    return {'items':[{'id':r.id,'actor_id':r.actor_id,'event_type':r.event_type,'details':r.details,'created_at':r.created_at} for r in rows]}


@router.get('/transactions/{transaction_id}/cancellations')
def get_cancellations(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx)
    rows=db.scalars(select(DealCancellation).where(DealCancellation.transaction_id==tx.id).order_by(DealCancellation.created_at.desc())).all()
    return {'items':[cancellation_view(r) for r in rows]}


@router.post('/transactions/{transaction_id}/cancellations',status_code=201)
def request_cancellation(transaction_id:str,data:CancellationCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx,lock=True)
    closed(tx)
    if tx.status=='DISPUTED':error(409,'분쟁 중에는 취소 요청 대신 분쟁 절차를 이용하세요.')
    if db.scalar(select(DealCancellation.id).where(DealCancellation.transaction_id==tx.id,DealCancellation.status=='PENDING')):
        error(409,'처리 중인 취소 요청이 있습니다.')
    item=DealCancellation(transaction_id=tx.id,requested_by=ctx['user'].id,reason=data.reason)
    db.add(item);db.flush()
    evt(db,tx,ctx,'CANCELLATION_REQUESTED',{'request_id':item.id})
    send(db,tx,other(tx,ctx['user'].id),'모의 거래 취소 요청이 도착했습니다.','DEAL_CANCELLATION')
    db.commit()
    return cancellation_view(item)


@router.post('/transactions/{transaction_id}/cancellations/{request_id}/respond')
def respond_cancellation(transaction_id:str,request_id:str,data:CancellationRespond,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx,lock=True)
    closed(tx)
    if tx.status=='DISPUTED':error(409,'분쟁 중에는 취소 요청에 응답할 수 없습니다.')
    item=db.scalar(select(DealCancellation).where(DealCancellation.id==request_id,DealCancellation.transaction_id==tx.id).with_for_update())
    if not item:error(404,'취소 요청을 찾을 수 없습니다.')
    if item.status!='PENDING':error(409,'이미 처리된 요청입니다.')
    if item.requested_by==ctx['user'].id:error(403,'취소를 요청한 당사자는 스스로 승인할 수 없습니다.')
    item.status='ACCEPTED' if data.accept else 'REJECTED'
    item.responded_by=ctx['user'].id
    item.response_note=data.response_note
    item.resolved_at=now()
    if data.accept:cancel_demo(db,tx)
    evt(db,tx,ctx,'CANCELLATION_'+item.status,{'request_id':item.id})
    send(db,tx,item.requested_by,'모의 거래 취소 요청에 답변이 도착했습니다.','DEAL_CANCELLATION')
    db.commit()
    return cancellation_view(item)


@router.get('/transactions/{transaction_id}/disputes')
def get_disputes(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx)
    rows=db.scalars(select(DealDispute).where(DealDispute.transaction_id==tx.id).order_by(DealDispute.created_at.desc())).all()
    return {'items':[dispute_view(r) for r in rows]}


@router.post('/transactions/{transaction_id}/disputes',status_code=201)
def open_dispute(transaction_id:str,data:DisputeCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx,lock=True)
    closed(tx)
    if tx.status=='DISPUTED':error(409,'이미 진행 중인 분쟁이 있습니다.')
    # Evidence is a list of reference labels, NOT validated file proof. No URLs or private contents.
    if any(len(s)>80 or not s.strip() for s in data.evidence_refs):error(422,'증빙 참조는 각각 1~80자로 입력하세요.')
    previous=tx.status
    item=DealDispute(transaction_id=tx.id,opened_by=ctx['user'].id,reason_code=data.reason_code,
                     description=data.description,evidence_refs=data.evidence_refs,resume_status=previous)
    db.add(item);db.flush()
    tx.status='DISPUTED';tx.version+=1
    for c in db.scalars(select(DealCancellation).where(DealCancellation.transaction_id==tx.id,DealCancellation.status=='PENDING')).all():
        c.status='REJECTED';c.response_note='분쟁 절차로 전환됨';c.resolved_at=now()
    evt(db,tx,ctx,'DISPUTE_OPENED',{'dispute_id':item.id,'reason_code':item.reason_code})
    send(db,tx,other(tx,ctx['user'].id),'모의 거래의 분쟁이 접수되었습니다.','DEAL_DISPUTE')
    for admin in db.scalars(select(User).where(User.role=='ADMIN',User.is_active.is_(True))).all():
        if admin.id not in (tx.buyer_id,tx.seller_id):send(db,tx,admin.id,'모의 거래 분쟁에 관리자 검토가 필요합니다.','DEAL_DISPUTE')
    db.commit()
    return dispute_view(item)


@router.post('/transactions/{transaction_id}/disputes/{dispute_id}/respond')
def respond_dispute(transaction_id:str,dispute_id:str,data:DisputeRespond,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=transaction(db,transaction_id,ctx,lock=True)
    if tx.status!='DISPUTED':error(409,'분쟁 처리 중인 거래가 아닙니다.')
    item=db.scalar(select(DealDispute).where(DealDispute.id==dispute_id,DealDispute.transaction_id==tx.id).with_for_update())
    if not item:error(404,'분쟁을 찾을 수 없습니다.')
    if item.status!='OPEN':error(409,'이미 종료된 분쟁입니다.')
    if item.opened_by==ctx['user'].id:error(403,'분쟁 신청자는 상대방 답변을 작성할 수 없습니다.')
    if item.counterparty_responded_at:error(409,'이미 답변했습니다.')
    item.counterparty_response=data.response;item.counterparty_responded_at=now()
    evt(db,tx,ctx,'DISPUTE_RESPONDED',{'dispute_id':item.id})
    send(db,tx,item.opened_by,'모의 거래 분쟁에 상대방 답변이 등록됐습니다.','DEAL_DISPUTE')
    db.commit()
    return dispute_view(item)


@router.get('/admin/deal-disputes')
def admin_disputes(db:Session=Depends(get_db),ctx=Depends(human)):
    only_admin(ctx)
    rows=db.scalars(select(DealDispute).order_by(DealDispute.created_at.desc()).limit(100)).all()
    return {'items':[dispute_view(d) for d in rows]}


@router.post('/admin/deal-disputes/{dispute_id}/decide')
def decide_dispute(dispute_id:str,data:DisputeDecision,db:Session=Depends(get_db),ctx=Depends(human)):
    only_admin(ctx)
    item=db.scalar(select(DealDispute).where(DealDispute.id==dispute_id).with_for_update())
    if not item:error(404,'분쟁을 찾을 수 없습니다.')
    tx=transaction(db,item.transaction_id,ctx,lock=True,admin=True)
    if ctx['user'].id in (tx.buyer_id,tx.seller_id):error(403,'거래 당사자는 관리자라도 자신의 분쟁을 결정할 수 없습니다.')
    if item.status!='OPEN' or tx.status!='DISPUTED':error(409,'이미 처리된 분쟁입니다.')
    if data.decision=='CANCEL_DEMO':cancel_demo(db,tx)
    else:
        tx.status=item.resume_status if item.resume_status in ('AWAITING_HANDOVER','HANDOVER_IN_PROGRESS','HANDOVER_REVIEW') else 'HANDOVER_IN_PROGRESS'
        tx.version+=1
    item.status='RESOLVED';item.admin_decision=data.decision;item.admin_reason=data.reason
    item.resolved_by=ctx['user'].id;item.resolved_at=now()
    evt(db,tx,ctx,'DISPUTE_RESOLVED',{'dispute_id':item.id,'decision':data.decision})
    for uid in (tx.buyer_id,tx.seller_id):send(db,tx,uid,'모의 거래 분쟁 검토 결과가 등록됐습니다.','DEAL_DISPUTE')
    db.commit()
    return dispute_view(item)


@router.get('/admin/deal-transactions')
def admin_transactions(db:Session=Depends(get_db),ctx=Depends(human)):
    only_admin(ctx)
    rows=db.scalars(select(Transaction).order_by(Transaction.created_at.desc()).limit(100)).all()
    return {'items':[{'id':t.id,'listing_id':t.listing_id,'buyer_id':t.buyer_id,'seller_id':t.seller_id,
                      'status':t.status,'is_demo':t.is_demo,'created_at':t.created_at} for t in rows]}


@router.get('/admin/deal-transactions/{transaction_id}')
def admin_deal_detail(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    only_admin(ctx)
    tx=transaction(db,transaction_id,ctx,admin=True)
    a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    cancellations=db.scalars(select(DealCancellation).where(DealCancellation.transaction_id==tx.id).order_by(DealCancellation.created_at)).all()
    disputes=db.scalars(select(DealDispute).where(DealDispute.transaction_id==tx.id).order_by(DealDispute.created_at)).all()
    events=db.scalars(select(DealEvent).where(DealEvent.transaction_id==tx.id).order_by(DealEvent.created_at,DealEvent.id)).all()
    return {'transaction':{'id':tx.id,'listing_id':tx.listing_id,'status':tx.status,'buyer_id':tx.buyer_id,
                           'seller_id':tx.seller_id,'is_demo':tx.is_demo},
            'agreement':agreement_view(a),
            'cancellations':[cancellation_view(c) for c in cancellations],
            'disputes':[dispute_view(d) for d in disputes],
            'events':[{'event_type':e.event_type,'actor_id':e.actor_id,'details':e.details,'created_at':e.created_at} for e in events]}
