"""Integrated DEMO buyer workspace, negotiation timeline and post-handover support.

Sensitive records are private to the two participants. No legal transfer/payment.
"""
from datetime import datetime, timedelta, timezone
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .db import get_db
from .models import BuyerPreferences, Listing, Offer, Transaction, AuditEvent, User, now
from .deal_models import DealAgreement
from .roadmap_models import DevelopmentRoadmap, DevelopmentRoadmapTask
from .v012_models import (OfferThread, SupportPolicySnapshot, SupportCase,
                          SupportMessage, RoadmapBuyerContext, RoadmapTaskHelpLink)
from .offer_terms_v2 import default_terms
from .schemas import Counter
from .security import human
from .notifications_v07 import notify

router=APIRouter(prefix='/api/v1', tags=['Integrated demo workspace'])
CATEGORIES={'SETUP_GUIDANCE','EXISTING_FUNCTION_GUIDANCE','CODE_STRUCTURE_GUIDANCE',
            'MISSING_ASSET','RIGHTS_CONCERN','OUT_OF_SCOPE'}
CLOSED={'RESOLVED','CLOSED_UNRESOLVED'}
SECRET_PATTERNS=(re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',re.I),
                 re.compile(r'(?i)(?:api[_-]?key|secret[_-]?key|password|access[_-]?token)\s*[:=]\s*[\'\"]?[A-Za-z0-9+/=_-]{16,}'))

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class SupportCreate(Strict):
    category: Literal['SETUP_GUIDANCE','EXISTING_FUNCTION_GUIDANCE','CODE_STRUCTURE_GUIDANCE',
                      'MISSING_ASSET','RIGHTS_CONCERN','OUT_OF_SCOPE']
    title: str = Field(min_length=5,max_length=150)
    description: str = Field(min_length=10,max_length=4000)
    roadmap_task_id: str | None = None
    attachment_refs: list[str] = Field(default_factory=list,max_length=0)

class MessageCreate(Strict):
    body: str = Field(min_length=2,max_length=4000)
    attachment_refs: list[str] = Field(default_factory=list,max_length=0)
    expected_version: int = Field(ge=1)

class VersionIn(Strict):
    expected_version: int = Field(ge=1)

class CoverageChange(VersionIn):
    coverage_type: Literal['IN_SCOPE','OUT_OF_SCOPE','UNDER_REVIEW']
    reason: str = Field(min_length=10,max_length=1000)

class AdminSupportDecision(VersionIn):
    action: Literal['REQUEST_INFO','CLOSE_UNRESOLVED']
    note: str = Field(min_length=10,max_length=1000)

class RoadmapContextPatch(VersionIn):
    skill_level: Literal['NONE','BASIC','INTERMEDIATE','ADVANCED']
    objective: str = Field(default='',max_length=500)
    preferred_guidance_level: Literal['BRIEF','STANDARD','DETAILED']='DETAILED'


def reject(code,text):raise HTTPException(code,text)


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def check_body(body):
    if any(pattern.search(body) for pattern in SECRET_PATTERNS):
        reject(422,'비밀키, 토큰 또는 비밀번호가 포함된 것 같습니다. 비밀값을 제거하고 다시 작성해 주세요.')
    return body.strip()


def tx_access(db,txid,ctx,lock=False):
    q=select(Transaction).where(Transaction.id==txid)
    if lock:q=q.with_for_update()
    tx=db.scalar(q)
    if not tx or ctx['user'].id not in (tx.buyer_id,tx.seller_id):reject(404,'해당 작업실이 없습니다.')
    if not tx.is_demo:reject(403,'시연 거래 전용 기능입니다.')
    return tx


def case_access(db,txid,caseid,ctx,lock=False):
    tx=tx_access(db,txid,ctx,lock=lock)
    q=select(SupportCase).where(SupportCase.id==caseid,SupportCase.transaction_id==tx.id)
    if lock:q=q.with_for_update()
    case=db.scalar(q)
    if not case:reject(404,'지원 요청을 찾을 수 없습니다.')
    return tx,case


def audit(db,ctx,name,kind,id,detail):
    db.add(AuditEvent(actor_user_id=ctx['user'].id,actor_type='USER',action=name,
        resource_type=kind,resource_id=id,old_state=None,new_state=detail,is_demo=True))


def policy_for(db,tx,create=False):
    policy=db.scalar(select(SupportPolicySnapshot).where(SupportPolicySnapshot.transaction_id==tx.id))
    if policy or not create:return policy
    a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    if not a:return None
    support=a.snapshot.get('support_terms') if a.snapshot.get('structured_terms_verified') else None
    policy=SupportPolicySnapshot(transaction_id=tx.id,agreement_snapshot_sha256=a.snapshot_sha256,
        days=support['days'] if support else 0,
        case_limit=support['included_case_limit'] if support else 0,
        scope_codes=support['scope_codes'] if support else [],
        reply_goal_hours=support['reply_goal_hours'] if support else 72,
        reply_goal_guaranteed=False,simulation_only=True)
    db.add(policy);db.flush()
    return policy


def start_support_policy(db,tx,ctx):
    """Called from the buyer's final handover confirmation in the same DB transaction."""
    p=policy_for(db,tx,create=True)
    if p and p.starts_at is None:
        p.starts_at=tx.completed_at or now()
        p.ends_at=p.starts_at + timedelta(days=p.days)
        audit(db,ctx,'support.started','transaction',tx.id,
              {'days':p.days,'case_limit':p.case_limit,'starts_at':p.starts_at.isoformat(),
               'ends_at':p.ends_at.isoformat()})


def policy_view(db,tx,p):
    if not p:
        return {'available':False,'reason':'조건 기록을 확인할 수 없습니다.','simulation_only':True,
                'days':0,'case_limit':0,'used_cases':0,'remaining_cases':0}
    used=db.scalar(select(func.count(SupportCase.id)).where(SupportCase.transaction_id==tx.id,
                     SupportCase.coverage_type=='IN_SCOPE')) or 0
    agreement=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==tx.id))
    legacy=not bool(agreement and agreement.snapshot.get('structured_terms_verified'))
    return {'available':True,'transaction_id':tx.id,'days':p.days,'case_limit':p.case_limit,
            'used_cases':used,'remaining_cases':max(0,p.case_limit-used),
            'scope_codes':p.scope_codes,'reply_goal_hours':p.reply_goal_hours,
            'reply_goal_guaranteed':p.reply_goal_guaranteed,
            'starts_at':p.starts_at,'ends_at':p.ends_at,
            'agreement_snapshot_sha256':p.agreement_snapshot_sha256,
            'simulation_only':True,'legacy_terms_unverified':legacy}


def case_view(item):
    return {'id':item.id,'transaction_id':item.transaction_id,'roadmap_task_id':item.roadmap_task_id,
            'buyer_id':item.buyer_id,'seller_id':item.seller_id,'category':item.category,
            'title':item.title,'description':item.description,'coverage_type':item.coverage_type,
            'status':item.status,'opened_at':item.opened_at,'first_reply_at':item.first_reply_at,
            'resolved_at':item.resolved_at,'closed_at':item.closed_at,'version':item.version}


def message_view(m):
    return {'id':m.id,'case_id':m.case_id,'sender_id':m.sender_id,'body':m.body,
            'attachment_refs':m.attachment_refs,'message_type':m.message_type,'created_at':m.created_at}


def make_case(db,tx,ctx,data):
    if ctx['user'].id!=tx.buyer_id:reject(403,'구매자만 지원을 요청할 수 있습니다.')
    if tx.status!='DEMO_COMPLETED':reject(409,'시연 인수가 완료된 후에 이용할 수 있습니다.')
    # A completed demo remains historical after account erasure, but cannot open new support.
    buyer=db.get(User,tx.buyer_id); seller=db.get(User,tx.seller_id)
    if not buyer or not seller or not buyer.is_active or not seller.is_active:
        reject(409,'거래 참여자가 탈퇴하여 새로운 지원 요청을 접수할 수 없습니다.')
    p=policy_for(db,tx,create=True)
    if not p:reject(409,'시연 거래의 고정 조건 기록이 없습니다.')
    if data.attachment_refs:reject(422,'첨부파일 업로드는 현재 비활성화되어 있습니다. 비밀 정보를 제외한 텍스트로 설명해 주세요.')
    coverage=('HANDOVER_REMEDY' if data.category in {'MISSING_ASSET','RIGHTS_CONCERN'} else
              'OUT_OF_SCOPE' if data.category=='OUT_OF_SCOPE' else 'IN_SCOPE')
    if coverage=='IN_SCOPE':
        if data.category not in p.scope_codes:reject(409,'이 유형은 합의한 일반 기술 지원 범위에 포함되지 않습니다. 별도 협의를 요청해 주세요.')
        if p.days==0 or not p.ends_at or now()>aware(p.ends_at):reject(409,'신규 기술 지원 접수 기간이 지났거나 약정이 없습니다.')
        count=db.scalar(select(func.count(SupportCase.id)).where(SupportCase.transaction_id==tx.id,
                  SupportCase.coverage_type=='IN_SCOPE')) or 0
        if count>=p.case_limit:reject(409,'약정된 기술 지원 문의 건수를 모두 사용했습니다.')
    if data.roadmap_task_id:
        plan=db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id==tx.id))
        task=db.get(DevelopmentRoadmapTask,data.roadmap_task_id)
        if not plan or not task or task.roadmap_id!=plan.id:reject(404,'이 거래의 로드맵 작업이 아닙니다.')
    count_all=db.scalar(select(func.count(SupportCase.id)).where(SupportCase.transaction_id==tx.id)) or 0
    if count_all>=100:reject(429,'시연 지원 요청은 거래당 최대 100개입니다.')
    title=check_body(data.title);description=check_body(data.description)
    if len(title)<5 or len(description)<10:reject(422,'제목과 내용을 구체적으로 입력해 주세요.')
    case=SupportCase(transaction_id=tx.id,roadmap_task_id=data.roadmap_task_id,
        buyer_id=tx.buyer_id,seller_id=tx.seller_id,category=data.category,title=title,
        description=description,coverage_type=coverage,status='OPEN')
    db.add(case);db.flush()
    db.add(SupportMessage(case_id=case.id,sender_id=tx.buyer_id,body=description,message_type='OPENED'))
    if data.roadmap_task_id:
        db.add(RoadmapTaskHelpLink(roadmap_task_id=data.roadmap_task_id,support_case_id=case.id))
    audit(db,ctx,'support.case.opened','support_case',case.id,{'category':data.category,'coverage':coverage})
    notify(db,tx.seller_id,'SUPPORT_REQUEST','새로운 시연 인수 후 지원 요청이 도착했습니다.','transaction',tx.id)
    return case


@router.get('/listings/{listing_id}/offer-terms-template')
def offer_terms_template(listing_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    listing=db.get(Listing,listing_id)
    if not listing or listing.status!='ACTIVE':reject(404,'공개 중인 매물이 아닙니다.')
    if listing.seller_id==ctx['user'].id:reject(403,'본인의 매물입니다.')
    return {'terms':default_terms(listing),'listing_version':listing.version,'expires_in_days':[1,3,7,14],
            'support_recommendations':{'0':0,'7':3,'14':5,'30':10},'simulation_only':True}


def thread_access(db,thread_id,ctx,lock=False):
    q=select(OfferThread).where(OfferThread.id==thread_id)
    if lock:q=q.with_for_update()
    thread=db.scalar(q)
    if not thread or ctx['user'].id not in (thread.buyer_id,thread.seller_id):reject(404,'협상을 찾을 수 없습니다.')
    return thread


@router.get('/offer-threads/{thread_id}')
def get_thread(thread_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    thread=thread_access(db,thread_id,ctx)
    offers=db.scalars(select(Offer).where(Offer.thread_id==thread.id).order_by(Offer.created_at,Offer.id)).all()
    changes=[]
    for i,o in enumerate(offers):
        previous=offers[i-1] if i else None
        fields=['price_krw','rights_type','included_assets','excluded_assets','handover_days','support','buyer_conditions_note']
        old=previous.terms if previous and previous.terms.get('schema_version')==2 else {}
        new=o.terms if o.terms.get('schema_version')==2 else {}
        diff={name:{'before':old.get(name),'after':new.get(name)} for name in fields if old.get(name)!=new.get(name)} if previous else {}
        changes.append({'id':o.id,'parent_offer_id':o.parent_offer_id,'proposed_by':o.proposed_by,
                        'offered_price_krw':o.offered_price_krw,'terms':o.terms,'status':o.status,
                        'version':o.version,'expires_at':o.expires_at,'created_at':o.created_at,
                        'diff_from_previous':diff,'legacy_terms':o.terms.get('schema_version')!=2})
    return {'id':thread.id,'listing_id':thread.listing_id,'buyer_id':thread.buyer_id,'seller_id':thread.seller_id,
            'status':thread.status,'version':thread.version,'last_offer_id':thread.last_offer_id,
            'offers':changes,'terms_template':default_terms(db.get(Listing,thread.listing_id)),
            'simulation_only':True}


@router.post('/offer-threads/{thread_id}/counter',status_code=201)
def counter_thread(thread_id:str,data:Counter,request:Request,
                   db:Session=Depends(get_db),ctx=Depends(human)):
    from .main import do_counter,idem_replay,idem_record,OFFER_FIELDS,view
    thread=thread_access(db,thread_id,ctx,lock=True)
    if thread.status!='UNRESOLVED':reject(409,'종료된 협상입니다.')
    offer=db.scalar(select(Offer).where(Offer.id==thread.last_offer_id).with_for_update())
    if not offer:reject(404,'제안을 찾을 수 없습니다.')
    route='offer.thread.counter:'+thread.id
    old=idem_replay(db,ctx,request,route,data.model_dump(mode='json'))
    if old is not None:return old
    child=do_counter(db,ctx,offer,data)
    result=view(child,OFFER_FIELDS)
    idem_record(db,ctx,request,route,data.model_dump(mode='json'),result)
    db.commit()
    return result


@router.post('/offer-threads/{thread_id}/accept',status_code=201)
def accept_thread(thread_id:str,data:VersionIn,request:Request,db:Session=Depends(get_db),ctx=Depends(human)):
    from .main import do_accept,idem_replay,idem_record,TX_FIELDS,view
    thread=thread_access(db,thread_id,ctx,lock=True)
    if thread.status!='UNRESOLVED':reject(409,'종료된 협상입니다.')
    route='offer.thread.accept:'+thread.id
    old=idem_replay(db,ctx,request,route,data.model_dump())
    if old is not None:return old
    offer=db.scalar(select(Offer).where(Offer.id==thread.last_offer_id).with_for_update())
    if not offer:reject(404,'제안을 찾을 수 없습니다.')
    tx=do_accept(db,ctx,offer,data.expected_version)
    result=view(tx,TX_FIELDS)
    idem_record(db,ctx,request,route,data.model_dump(),result)
    db.commit()
    return result


@router.get('/transactions/{transaction_id}/support-policy')
def support_policy(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=tx_access(db,transaction_id,ctx)
    p=policy_for(db,tx)
    if not p and tx.status=='DEMO_COMPLETED':
        p=policy_for(db,tx,create=True)
        if p and tx.completed_at:
            p.starts_at=tx.completed_at;p.ends_at=tx.completed_at+timedelta(days=p.days)
        db.commit()
    return policy_view(db,tx,p)


@router.get('/transactions/{transaction_id}/workspace')
def project_workspace(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=tx_access(db,transaction_id,ctx)
    listing=db.get(Listing,tx.listing_id)
    p=policy_for(db,tx)
    plan=db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id==tx.id))
    next_task=None
    if plan:
        next_task=db.scalar(select(DevelopmentRoadmapTask).where(
            DevelopmentRoadmapTask.roadmap_id==plan.id,
            DevelopmentRoadmapTask.status!='COMPLETED').order_by(DevelopmentRoadmapTask.position).limit(1))
    return {'transaction_id':tx.id,'listing_title':listing.title if listing else '프로젝트',
        'status':tx.status,'buyer_id':tx.buyer_id,'seller_id':tx.seller_id,
        'role':'BUYER' if ctx['user'].id==tx.buyer_id else 'SELLER',
        'next_action':('인계 조건 확인' if tx.status=='AWAITING_HANDOVER' else
                       '인수 절차 진행' if tx.status not in {'DEMO_COMPLETED','CANCELLED'} else
                       (next_task.title if next_task else '개발 로드맵 생성 또는 확인')),
        'next_roadmap_task_id':next_task.id if next_task else None,
        'roadmap_created':bool(plan),'support':policy_view(db,tx,p),
        'agreement_url':f'/api/v1/transactions/{tx.id}/agreement',
        'simulation_only':True}


@router.get('/transactions/{transaction_id}/support-cases')
def list_support_cases(transaction_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=tx_access(db,transaction_id,ctx)
    cases=db.scalars(select(SupportCase).where(SupportCase.transaction_id==tx.id)
                 .order_by(SupportCase.opened_at.desc()).limit(100)).all()
    return {'items':[case_view(c) for c in cases]}


@router.post('/transactions/{transaction_id}/support-cases',status_code=201)
def create_support_case(transaction_id:str,data:SupportCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=tx_access(db,transaction_id,ctx,lock=True)
    case=make_case(db,tx,ctx,data)
    db.commit();return case_view(case)


@router.post('/transactions/{transaction_id}/roadmap/tasks/{task_id}/support-cases',status_code=201)
def roadmap_support_case(transaction_id:str,task_id:str,data:SupportCreate,
                         db:Session=Depends(get_db),ctx=Depends(human)):
    if data.roadmap_task_id is not None and data.roadmap_task_id!=task_id:reject(422,'작업 ID가 다릅니다.')
    tx=tx_access(db,transaction_id,ctx,lock=True)
    case=make_case(db,tx,ctx,data.model_copy(update={'roadmap_task_id':task_id}))
    db.commit();return case_view(case)


@router.get('/transactions/{transaction_id}/support-cases/{case_id}')
def support_case_detail(transaction_id:str,case_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    _,case=case_access(db,transaction_id,case_id,ctx)
    messages=db.scalars(select(SupportMessage).where(SupportMessage.case_id==case.id)
                .order_by(SupportMessage.created_at,SupportMessage.id)).all()
    return {'case':case_view(case),'messages':[message_view(m) for m in messages]}


@router.post('/transactions/{transaction_id}/support-cases/{case_id}/messages',status_code=201)
def add_support_message(transaction_id:str,case_id:str,data:MessageCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    tx,case=case_access(db,transaction_id,case_id,ctx,lock=True)
    if case.version!=data.expected_version:reject(409,'사례가 변경됐습니다. 다시 확인해 주세요.')
    if case.status in CLOSED or tx.status=='CANCELLED':reject(409,'종료된 요청에는 답변할 수 없습니다.')
    if data.attachment_refs:reject(422,'현재 메시지 첨부파일은 지원하지 않습니다.')
    count=db.scalar(select(func.count(SupportMessage.id)).where(SupportMessage.case_id==case.id)) or 0
    if count>=150:reject(429,'사례당 메시지 최대 수에 도달했습니다.')
    body=check_body(data.body)
    msg=SupportMessage(case_id=case.id,sender_id=ctx['user'].id,body=body)
    db.add(msg)
    if ctx['user'].id==tx.seller_id:
        case.status='SELLER_REPLIED'
        if not case.first_reply_at:case.first_reply_at=now()
    else:case.status='NEEDS_INFO'
    case.version+=1
    audit(db,ctx,'support.message.sent','support_case',case.id,{'message_id':msg.id})
    notify(db,tx.buyer_id if ctx['user'].id==tx.seller_id else tx.seller_id,
           'SUPPORT_REPLY','시연 인수 후 지원 요청에 새 답변이 등록됐습니다.','transaction',tx.id)
    db.commit();return {'case':case_view(case),'message':message_view(msg)}


@router.post('/transactions/{transaction_id}/support-cases/{case_id}/resolve')
def resolve_support_case(transaction_id:str,case_id:str,data:VersionIn,
                         db:Session=Depends(get_db),ctx=Depends(human)):
    tx,case=case_access(db,transaction_id,case_id,ctx,lock=True)
    if ctx['user'].id!=tx.buyer_id:reject(403,'구매자만 해결 완료를 확정할 수 있습니다.')
    if case.version!=data.expected_version or case.status in CLOSED:reject(409,'현재 해결 확정할 수 없는 요청입니다.')
    case.status='RESOLVED';case.resolved_at=now();case.version+=1
    audit(db,ctx,'support.case.resolved','support_case',case.id,{})
    notify(db,tx.seller_id,'SUPPORT_RESOLVED','구매자가 지원 요청 해결을 확인했습니다.','transaction',tx.id)
    db.commit();return case_view(case)


@router.post('/transactions/{transaction_id}/support-cases/{case_id}/escalate')
def escalate_support_case(transaction_id:str,case_id:str,data:MessageCreate,
                          db:Session=Depends(get_db),ctx=Depends(human)):
    tx,case=case_access(db,transaction_id,case_id,ctx,lock=True)
    if case.version!=data.expected_version or case.status in CLOSED:reject(409,'요청이 변경됐거나 종료되었습니다.')
    case.status='ESCALATED';case.version+=1
    msg=SupportMessage(case_id=case.id,sender_id=ctx['user'].id,
                       body=check_body(data.body),message_type='ESCALATION')
    db.add(msg)
    audit(db,ctx,'support.case.escalated','support_case',case.id,{'reason':msg.body[:400]})
    db.commit();return case_view(case)


@router.post('/transactions/{transaction_id}/support-cases/{case_id}/coverage')
def support_coverage(transaction_id:str,case_id:str,data:CoverageChange,
                     db:Session=Depends(get_db),ctx=Depends(human)):
    tx,case=case_access(db,transaction_id,case_id,ctx,lock=True)
    if ctx['user'].id!=tx.seller_id:reject(403,'판매자만 지원 범위를 재검토할 수 있습니다.')
    if case.version!=data.expected_version or case.status in CLOSED:reject(409,'요청이 변경되거나 종료되었습니다.')
    if case.coverage_type=='HANDOVER_REMEDY':reject(409,'약정 누락 또는 권리 문제를 일반 지원으로 재분류할 수 없습니다.')
    p=policy_for(db,tx)
    if data.coverage_type=='IN_SCOPE':
        if not p or case.category not in p.scope_codes:reject(409,'합의한 지원 범위 밖입니다.')
        used=db.scalar(select(func.count(SupportCase.id)).where(SupportCase.transaction_id==tx.id,
              SupportCase.coverage_type=='IN_SCOPE',SupportCase.id!=case.id)) or 0
        if used>=p.case_limit:reject(409,'지원 건수를 초과합니다.')
    before=case.coverage_type;case.coverage_type=data.coverage_type;case.version+=1
    db.add(SupportMessage(case_id=case.id,sender_id=tx.seller_id,
                          body=check_body(data.reason),message_type='COVERAGE_DECISION'))
    audit(db,ctx,'support.coverage.changed','support_case',case.id,{'before':before,'after':data.coverage_type})
    notify(db,tx.buyer_id,'SUPPORT_COVERAGE','판매자가 지원 범위에 대한 검토 의견을 등록했습니다.','transaction',tx.id)
    db.commit();return case_view(case)


@router.get('/admin/support-cases')
def admin_support_cases(db:Session=Depends(get_db),ctx=Depends(human)):
    if ctx['user'].role!='ADMIN':reject(403,'관리자 권한이 필요합니다.')
    cases=db.scalars(select(SupportCase).where(SupportCase.status=='ESCALATED')
          .order_by(SupportCase.opened_at).limit(100)).all()
    return {'items':[{'id':c.id,'transaction_id':c.transaction_id,'status':c.status,
                       'coverage_type':c.coverage_type,'category':c.category,
                       'opened_at':c.opened_at} for c in cases]}


@router.get('/admin/support-cases/{case_id}')
def admin_support_case_detail(case_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    if ctx['user'].role!='ADMIN':reject(403,'관리자 권한이 필요합니다.')
    case=db.get(SupportCase,case_id)
    if not case:reject(404,'지원 요청을 찾을 수 없습니다.')
    messages=db.scalars(select(SupportMessage).where(SupportMessage.case_id==case.id)
                        .order_by(SupportMessage.created_at,SupportMessage.id)).all()
    return {'case':case_view(case),'messages':[message_view(m) for m in messages]}


@router.post('/admin/support-cases/{case_id}/decision')
def admin_support_decision(case_id:str,data:AdminSupportDecision,
                           db:Session=Depends(get_db),ctx=Depends(human)):
    if ctx['user'].role!='ADMIN':reject(403,'관리자 권한이 필요합니다.')
    case=db.scalar(select(SupportCase).where(SupportCase.id==case_id).with_for_update())
    if not case:reject(404,'지원 요청을 찾을 수 없습니다.')
    if case.status!='ESCALATED' or case.version!=data.expected_version:
        reject(409,'검토 대기 중인 최신 요청만 처리할 수 있습니다.')
    note=check_body(data.note)
    case.version+=1
    if data.action=='CLOSE_UNRESOLVED':
        case.status='CLOSED_UNRESOLVED';case.closed_at=now()
    else:case.status='NEEDS_INFO'
    db.add(SupportMessage(case_id=case.id,sender_id=ctx['user'].id,
                          body=note,message_type='ADMIN_DECISION'))
    audit(db,ctx,'support.admin.decision','support_case',case.id,
          {'action':data.action,'status':case.status})
    for receiver in (case.buyer_id,case.seller_id):
        notify(db,receiver,'SUPPORT_REVIEW','시연 인수 지원 요청에 관리자 검토 결과가 등록됐습니다.',
               'transaction',case.transaction_id)
    db.commit();return case_view(case)


@router.patch('/transactions/{transaction_id}/roadmap/buyer-context')
def roadmap_context(transaction_id:str,data:RoadmapContextPatch,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=tx_access(db,transaction_id,ctx,lock=True)
    if tx.buyer_id!=ctx['user'].id or tx.status!='DEMO_COMPLETED':reject(403,'구매자 인수 후에만 변경할 수 있습니다.')
    plan=db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id==tx.id))
    if not plan:reject(404,'먼저 개발 로드맵을 생성해 주세요.')
    item=db.get(RoadmapBuyerContext,plan.id)
    if not item:
        if data.expected_version!=0 and data.expected_version!=1:reject(409,'도움 수준을 새로고침해 주세요.')
        item=RoadmapBuyerContext(roadmap_id=plan.id,version=0)
        db.add(item)
    elif item.version!=data.expected_version:reject(409,'다른 변경 사항이 있습니다.')
    item.skill_level=data.skill_level;item.objective=check_body(data.objective)
    item.preferred_guidance_level=data.preferred_guidance_level;item.version+=1
    audit(db,ctx,'roadmap.context.updated','development_roadmap',plan.id,{'skill_level':data.skill_level})
    db.commit()
    return {'skill_level':item.skill_level,'objective':item.objective,
            'preferred_guidance_level':item.preferred_guidance_level,'version':item.version}
