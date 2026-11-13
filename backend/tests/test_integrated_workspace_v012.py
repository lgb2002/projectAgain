"""v0.12: active listings remain public during DEMO; fixed support contract; access control."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Listing, Transaction
from app.deal_models import DealAgreement
from app.v012_models import SupportCase, SupportPolicySnapshot
from test_workflows import people, setup_market, post
from test_development_roadmap_v09 import complete


def v2(listing,days=7):
    return {'schema_version':2,'price_krw':70000,'rights_type':listing['sale_rights_type'],
            'included_assets':listing['included_assets'],'excluded_assets':listing['excluded_assets'],
            'handover_days':7,'support':{'days':days,'included_case_limit':{0:0,7:3,14:5,30:10}[days],
            'scope_codes':['SETUP_GUIDANCE','EXISTING_FUNCTION_GUIDANCE'] if days else [],
            'reply_goal_hours':72,'is_reply_goal_guaranteed':False,'exceptions_note':'새 기능 추가 제외'},
            'buyer_conditions_note':'설치 가이드 확인'}


def create(seller,buyer,listing,days=7):
    terms=v2(listing,days)
    payload={'listing_id':listing['id'],'offered_price_krw':70000,
             'terms':terms,'expires_at':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),'is_demo':True}
    r=post(buyer,'/offers',payload)
    assert r.status_code==201,r.text
    o=r.json()
    accepted=post(seller,f'/offers/{o["id"]}/accept',{'expected_version':o['version']})
    assert accepted.status_code==201,accepted.text
    return o,accepted.json()


def case_payload(category='SETUP_GUIDANCE',task=None):
    return {'category':category,'title':'설치 과정에서 발생한 문제',
            'description':'파이썬 실행 시 필요한 설정 파일을 찾지 못했습니다.',
            'roadmap_task_id':task,'attachment_refs':[]}


def test_demo_accept_completion_keeps_listing_active_and_starts_fixed_support():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    offer,tx=create(seller,buyer,listing)
    txid=tx['id']
    with SessionLocal() as db:
        row=db.get(Listing,listing['id']);t=db.get(Transaction,txid)
        assert row.status=='ACTIVE' and t.exclusive_guard_listing_id is None
        a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==txid))
        assert a.snapshot['support_terms']['days']==7
        assert a.snapshot['support_terms']['included_case_limit']==3
        assert a.snapshot['structured_terms_verified'] is True
        assert a.snapshot['price_krw']==70000
    assert stranger['client'].get(f'/api/v1/listings/{listing["id"]}?include_demo=true').status_code==200
    before=buyer['client'].get(f'/api/v1/transactions/{txid}/support-policy').json()
    assert before['days']==7 and before['starts_at'] is None
    complete(seller,buyer,tx)
    after=buyer['client'].get(f'/api/v1/transactions/{txid}/support-policy').json()
    assert after['starts_at'] is not None and after['ends_at'] is not None
    assert after['remaining_cases']==3
    assert stranger['client'].get(f'/api/v1/transactions/{txid}/support-policy').status_code==404
    with SessionLocal() as db:
        assert db.get(Listing,listing['id']).status=='ACTIVE'
        assert db.get(Transaction,txid).completed_at is not None
        policy=db.scalar(select(SupportPolicySnapshot).where(SupportPolicySnapshot.transaction_id==txid))
        assert policy.agreement_snapshot_sha256==db.scalar(select(DealAgreement.snapshot_sha256).where(DealAgreement.transaction_id==txid))


def test_quota_reply_after_expiry_buyer_only_resolve_and_remedy_not_counted():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    _,tx=create(seller,buyer,listing);txid=tx['id'];complete(seller,buyer,tx)
    endpoint=f'/transactions/{txid}/support-cases'
    first=post(buyer,endpoint,case_payload());assert first.status_code==201,first.text
    case=first.json();cid=case['id']
    assert post(stranger,endpoint,case_payload()).status_code==404
    assert stranger['client'].get('/api/v1'+endpoint+'/'+cid).status_code==404
    assert post(seller,endpoint,case_payload()).status_code==403
    assert post(seller,endpoint+'/'+cid+'/resolve',{'expected_version':case['version']}).status_code==403
    response=post(seller,endpoint+'/'+cid+'/messages',{'body':'설치 설정 위치를 문서에 안내했습니다.','expected_version':case['version'],'attachment_refs':[]})
    assert response.status_code==201,response.text
    assert buyer['client'].get('/api/v1'+endpoint+'/'+cid).json()['messages'][1]['body'].startswith('설치 설정')
    assert post(buyer,endpoint+'/'+cid+'/messages',{'body':'설정 파일이 정상 동작합니다.','expected_version':case['version'],'attachment_refs':[]}).status_code==409
    for _ in range(2):assert post(buyer,endpoint,case_payload()).status_code==201
    assert post(buyer,endpoint,case_payload()).status_code==409
    remedy=post(buyer,endpoint,case_payload('MISSING_ASSET'));assert remedy.status_code==201,remedy.text
    assert remedy.json()['coverage_type']=='HANDOVER_REMEDY'
    assert buyer['client'].get(f'/api/v1/transactions/{txid}/support-policy').json()['used_cases']==3
    with SessionLocal() as db:
        p=db.scalar(select(SupportPolicySnapshot).where(SupportPolicySnapshot.transaction_id==txid))
        p.ends_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert post(buyer,endpoint,case_payload()).status_code==409
    current=buyer['client'].get('/api/v1'+endpoint+'/'+cid).json()['case']
    assert post(seller,endpoint+'/'+cid+'/messages',{'body':'지원 기한이 지나도 답변은 가능합니다.','expected_version':current['version'],'attachment_refs':[]}).status_code==201
    current=buyer['client'].get('/api/v1'+endpoint+'/'+cid).json()['case']
    assert post(buyer,endpoint+'/'+cid+'/resolve',{'expected_version':current['version']}).status_code==200
    assert post(seller,endpoint+'/'+cid+'/messages',{'body':'종료된 요청 답변','expected_version':current['version']+1,'attachment_refs':[]}).status_code==409


def test_zero_support_still_allows_handover_remedy_and_roadmap_link():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    _,tx=create(seller,buyer,listing,days=0);txid=tx['id'];complete(seller,buyer,tx)
    base=f'/transactions/{txid}/support-cases'
    assert post(buyer,base,case_payload('SETUP_GUIDANCE')).status_code==409
    assert post(buyer,base,case_payload('MISSING_ASSET')).status_code==201
    plan=post(buyer,f'/transactions/{txid}/development-roadmap').json()
    task=plan['tasks'][0]
    linked=post(buyer,f'/transactions/{txid}/roadmap/tasks/{task["id"]}/support-cases',case_payload('MISSING_ASSET',task['id']))
    assert linked.status_code==201,linked.text
    new=buyer['client'].get(f'/api/v1/transactions/{txid}/development-roadmap').json()
    assert linked.json()['id'] in new['tasks'][0]['support_case_ids']
    assert post(stranger,f'/transactions/{txid}/roadmap/tasks/{task["id"]}/support-cases',case_payload('MISSING_ASSET',task['id'])).status_code==404
    patch=post(buyer,f'/transactions/{txid}/roadmap/buyer-context',{'skill_level':'NONE','objective':'초보자 실습',
        'preferred_guidance_level':'DETAILED','expected_version':1},'patch')
    assert patch.status_code==200,patch.text
    assert buyer['client'].get(f'/api/v1/transactions/{txid}/development-roadmap').json()['buyer_context']['skill_level']=='NONE'


def test_offer_thread_stale_version_and_rights_exclusion_guard():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    terms=v2(listing);terms['support']['included_case_limit']=0
    payload={'listing_id':listing['id'],'offered_price_krw':70000,'terms':terms,
             'expires_at':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()}
    assert post(buyer,'/offers',payload).status_code==422
    terms=v2(listing);terms['price_krw']=80000
    assert post(buyer,'/offers',{**payload,'terms':terms}).status_code==422
    offer,tx=create(seller,buyer,listing)
    thread=buyer['client'].get('/api/v1/offer-threads/'+offer['thread_id']).json()
    assert len(thread['offers'])==1 and thread['offers'][0]['terms']['schema_version']==2
    assert stranger['client'].get('/api/v1/offer-threads/'+offer['thread_id']).status_code==404
    assert post(seller,'/offer-threads/'+offer['thread_id']+'/accept',{'expected_version':1}).status_code==409


def test_admin_support_dispute_review_is_versioned_and_private():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    _,tx=create(seller,buyer,listing);txid=tx['id'];complete(seller,buyer,tx)
    endpoint=f'/transactions/{txid}/support-cases'
    case=post(buyer,endpoint,case_payload()).json()
    elevated=post(buyer,endpoint+'/'+case['id']+'/escalate',
                  {'body':'판매자 지원 범위에 대해 관리자 확인을 요청합니다.',
                   'expected_version':case['version'],'attachment_refs':[]})
    assert elevated.status_code==200,elevated.text
    assert seller['client'].get('/api/v1/admin/support-cases').status_code==403
    items=admin['client'].get('/api/v1/admin/support-cases')
    assert items.status_code==200 and len(items.json()['items'])==1
    detail=admin['client'].get('/api/v1/admin/support-cases/'+case['id'])
    assert detail.status_code==200 and len(detail.json()['messages'])==2
    assert stranger['client'].get('/api/v1/admin/support-cases/'+case['id']).status_code==403
    decision={'action':'REQUEST_INFO','note':'지원 가능 범위와 인계 자료를 먼저 대조해 주세요.',
              'expected_version':elevated.json()['version']}
    assert post(buyer,'/admin/support-cases/'+case['id']+'/decision',decision).status_code==403
    approved=post(admin,'/admin/support-cases/'+case['id']+'/decision',decision)
    assert approved.status_code==200 and approved.json()['status']=='NEEDS_INFO',approved.text
    assert post(admin,'/admin/support-cases/'+case['id']+'/decision',decision).status_code==409
    assert admin['client'].get('/api/v1/admin/support-cases').json()['items']==[]
