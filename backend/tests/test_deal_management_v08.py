"""Demo transaction agreements, bilateral cancellation and administrator dispute review."""
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import Listing, AssetShare, User
from app.deal_models import DealAgreement, DealDispute, DealEvent
from test_workflows import people, setup_market, offer_payload, post


def new_deal():
    seller,buyer,stranger,admin=people()
    listing=setup_market(seller,buyer,admin)
    offer=post(buyer,'/offers',offer_payload(listing['id'])).json()
    r=post(seller,f'/offers/{offer["id"]}/accept',{'expected_version':offer['version']})
    assert r.status_code==201,r.text
    return seller,buyer,stranger,admin,listing,r.json()


def agree(user,txid):
    p=user['client'].get(f'/api/v1/transactions/{txid}/agreement')
    assert p.status_code==200,p.text
    digest=p.json()['agreement']['snapshot_sha256']
    return post(user,f'/transactions/{txid}/agreement/acknowledge',{'snapshot_sha256':digest,'understood_demo_only':True,'confirmed_terms':True})


def test_immutable_terms_two_party_ack_and_handover_gate():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    assert buyer['client'].get(f'/api/v1/transactions/{txid}/agreement').json()['agreement']['snapshot']['price_krw']==70000
    assert stranger['client'].get(f'/api/v1/transactions/{txid}/agreement').status_code==404
    assert post(stranger,f'/transactions/{txid}/agreement/prepare').status_code==404
    assert post(seller,f'/transactions/{txid}/transition',{'status':'HANDOVER_IN_PROGRESS','expected_version':1}).status_code==409
    assert post(buyer,f'/transactions/{txid}/agreement/acknowledge',{'snapshot_sha256':'0'*64,'understood_demo_only':True,'confirmed_terms':True}).status_code==409
    first=agree(seller,txid)
    assert first.status_code==200,first.text
    assert first.json()['agreement']['status']=='PENDING'
    assert agree(seller,txid).status_code==409
    second=agree(buyer,txid)
    assert second.status_code==200 and second.json()['agreement']['status']=='ACKNOWLEDGED'
    assert post(seller,f'/transactions/{txid}/transition',{'status':'HANDOVER_IN_PROGRESS','expected_version':1}).status_code==200
    assert post(seller,f'/transactions/{txid}/transition',{'status':'DISPUTED','expected_version':2}).status_code==409
    assert post(seller,f'/transactions/{txid}/transition',{'status':'CANCELLED','expected_version':2}).status_code==409
    assert post(stranger,f'/transactions/{txid}/cancellations',{'reason':'외부 무단 취소 시도입니다.'}).status_code==404
    events=buyer['client'].get(f'/api/v1/transactions/{txid}/deal-events').json()['items']
    assert any(e['event_type']=='AGREEMENT_ACKNOWLEDGED' for e in events)
    with SessionLocal() as db:
        a=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==txid))
        assert a.snapshot_sha256 and a.buyer_ack_digest==a.seller_ack_digest==a.snapshot_sha256
        assert a.snapshot['payment_state']=='NOT_AVAILABLE'


def test_bilateral_cancellation_and_return_listing():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    req=post(seller,f'/transactions/{txid}/cancellations',{'reason':'판매자가 등록한 파일이 준비되지 않았습니다.'})
    assert req.status_code==201,req.text
    cancel_id=req.json()['id']
    assert post(seller,f'/transactions/{txid}/cancellations/{cancel_id}/respond',{'accept':True,'response_note':'본인 승인 거부'}).status_code==403
    assert post(buyer,f'/transactions/{txid}/cancellations',{'reason':'중복 취소 요청입니다. 다시 확인합니다.'}).status_code==409
    assert post(stranger,f'/transactions/{txid}/cancellations/{cancel_id}/respond',{'accept':True,'response_note':'외부 사용자'}).status_code==404
    assert post(buyer,f'/transactions/{txid}/cancellations/{cancel_id}/respond',{'accept':True,'response_note':'자료 준비 부족 확인 및 취소 동의'}).status_code==200
    with SessionLocal() as db:
        row=db.get(Listing,listing['id'])
        assert row.status=='ACTIVE'
    assert seller['client'].get(f'/api/v1/transactions/{txid}').json()['status']=='CANCELLED'
    assert post(seller,f'/transactions/{txid}/cancellations',{'reason':'종료 후 취소 요청 불가입니다.'}).status_code==409
    assert post(buyer,'/offers',offer_payload(listing['id'])).status_code==201


def test_cancellation_rejection_and_re_request():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    req=post(seller,f'/transactions/{txid}/cancellations',{'reason':'일정이 맞지 않아서 취소를 요청합니다.'}).json()
    response=post(buyer,f'/transactions/{txid}/cancellations/{req["id"]}/respond',{'accept':False,'response_note':'기존 조건대로 진행을 원합니다.'})
    assert response.status_code==200 and response.json()['status']=='REJECTED'
    assert post(seller,f'/transactions/{txid}/cancellations',{'reason':'조건 재협의가 필요하여 다시 요청합니다.'}).status_code==201
    assert buyer['client'].get(f'/api/v1/transactions/{txid}').json()['status']=='AWAITING_HANDOVER'


def test_dispute_pause_counterparty_response_and_admin_resume():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    assert post(buyer,f'/transactions/{txid}/disputes',{'reason_code':'MISSING_ASSET','description':'소스코드 전달 목록에 핵심 파일이 빠져 있습니다.', 'evidence_refs':[]}).status_code==201
    case=buyer['client'].get(f'/api/v1/transactions/{txid}/disputes').json()['items'][0]
    assert post(buyer,f'/transactions/{txid}/disputes/{case["id"]}/respond',{'response':'본인 혼자 답변할 수 없는 내용입니다.'}).status_code==403
    assert post(seller,f'/transactions/{txid}/transition',{'status':'HANDOVER_IN_PROGRESS','expected_version':2}).status_code==409
    res=post(seller,f'/transactions/{txid}/disputes/{case["id"]}/respond',{'response':'누락 파일은 업로드하기로 하였으며 인계 자료를 보완하겠습니다.'})
    assert res.status_code==200,res.text
    assert post(seller,f'/transactions/{txid}/disputes/{case["id"]}/respond',{'response':'다시 답변할 수 없습니다.'}).status_code==409
    assert post(buyer,f'/admin/deal-disputes/{case["id"]}/decide',{'decision':'RESUME_HANDOVER','reason':'양측이 증빙을 비교했고 인계를 재개하기로 결정했습니다.'}).status_code==403
    admin_cases=admin['client'].get('/api/v1/admin/deal-disputes')
    assert admin_cases.status_code==200 and len(admin_cases.json()['items'])==1
    assert stranger['client'].get('/api/v1/admin/deal-disputes').status_code==403
    ok=post(admin,f'/admin/deal-disputes/{case["id"]}/decide',{'decision':'RESUME_HANDOVER','reason':'양측에서 파일 보완을 진행하도록 인계를 재개합니다.'})
    assert ok.status_code==200,ok.text
    assert ok.json()['status']=='RESOLVED'
    assert buyer['client'].get(f'/api/v1/transactions/{txid}').json()['status']=='AWAITING_HANDOVER'
    assert post(admin,f'/admin/deal-disputes/{case["id"]}/decide',{'decision':'CANCEL_DEMO','reason':'중복 관리자 결정은 금지해야 합니다.'}).status_code==409


def test_dispute_admin_cancel_releases_reservation_and_logs():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    req=post(buyer,f'/transactions/{txid}/disputes',{'reason_code':'RIGHTS_CONCERN','description':'외부 권리자 자료가 포함되어 구매 이전이 불가능해 보입니다.'})
    assert req.status_code==201,req.text
    case=req.json()
    assert post(admin,f'/admin/deal-disputes/{case["id"]}/decide',{'decision':'CANCEL_DEMO','reason':'권리 관련 문제를 먼저 해결해야 하므로 모의 거래를 취소합니다.'}).status_code==200
    assert buyer['client'].get(f'/api/v1/transactions/{txid}').json()['status']=='CANCELLED'
    with SessionLocal() as db:assert db.get(Listing,listing['id']).status=='ACTIVE'
    events=seller['client'].get(f'/api/v1/transactions/{txid}/deal-events').json()['items']
    assert events[-1]['event_type']=='DISPUTE_RESOLVED'


def test_human_only_ack_and_admin_conflict_prevention():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    grant=post(buyer,'/auth/agent-grants',{'scopes':['transaction:read'],'expires_in_hours':1}).json()
    digest=buyer['client'].get(f'/api/v1/transactions/{txid}/agreement').json()['agreement']['snapshot_sha256']
    r=TestClient(app).post(f'/api/v1/transactions/{txid}/agreement/acknowledge',json={'snapshot_sha256':digest,'understood_demo_only':True,'confirmed_terms':True},headers={'Authorization':'Bearer '+grant['token']})
    assert r.status_code==403


def test_fixed_document_access_and_admin_transaction_detail():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    assert stranger['client'].get(f'/api/v1/transactions/{txid}/agreement/document').status_code==404
    doc=buyer['client'].get(f'/api/v1/transactions/{txid}/agreement/document')
    assert doc.status_code==200 and doc.headers['cache-control']=='private, no-store'
    assert b'projectagain-demo-terms' in doc.headers['content-disposition'].encode()
    assert '대금 지급' in doc.content.decode('utf-8-sig')
    assert stranger['client'].get('/api/v1/admin/deal-transactions').status_code==403
    assert stranger['client'].get(f'/api/v1/admin/deal-transactions/{txid}').status_code==403
    detail=admin['client'].get(f'/api/v1/admin/deal-transactions/{txid}')
    assert detail.status_code==200 and detail.json()['agreement']['snapshot']['price_krw']==70000
    assert len(detail.json()['events'])>=2


def test_admin_cannot_approve_own_dispute_even_with_admin_role():
    seller,buyer,stranger,admin,listing,tx=new_deal();txid=tx['id']
    with SessionLocal() as db:
        db.get(User,buyer['id']).role='ADMIN'
        db.commit()
    case=post(buyer,f'/transactions/{txid}/disputes',{'reason_code':'OTHER','description':'모의 거래의 관리자 이해충돌을 테스트합니다.'}).json()
    result=post(buyer,f'/admin/deal-disputes/{case["id"]}/decide',{'decision':'CANCEL_DEMO','reason':'본인이 자신의 분쟁을 처리하면 안 됩니다.'})
    assert result.status_code==403
