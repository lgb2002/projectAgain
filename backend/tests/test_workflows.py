import json
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import Base, engine, SessionLocal
from app.main import app, digest_payload
from app.models import User, Listing, now



def create(client,email):
    password='Long-Unique-Test-Password-2026!'
    assert client.post('/api/v1/auth/register',json={'email':email,'password':password}).status_code==201
    response=client.post('/api/v1/auth/login',json={'email':email,'password':password})
    assert response.status_code==200,response.text
    return {'client':client,'csrf':response.json()['csrf_token'],'id':response.json()['user']['id']}


def post(user,path,data=None,method='post'):
    return getattr(user['client'],method)('/api/v1'+path,json=data or {},headers={'X-CSRF-Token':user['csrf']})


def listing_payload():
    return {'title':'작은 웹앱 프로젝트','description':'일정 관리와 완료 체크를 지원하는 검증 전 웹 애플리케이션입니다. 실행 환경은 판매자 설정입니다.',
            'category':'web_app','lifecycle_status':'FAILED_COMMERCIALIZATION','sale_rights_type':'FULL_IP_ASSIGNMENT',
            'price_krw':100000,'tech_stack':['FastAPI','React'],'included_assets':['소스코드'],'excluded_assets':['API 키'],
            'known_defects':['결제 미구현'],'monthly_cost_estimate_krw':0,'rights_attested':True,'is_demo':True}


def setup_market(seller,buyer,admin):
    create_res=post(seller,'/listings',listing_payload())
    assert create_res.status_code==201,create_res.text
    row=create_res.json()
    assert row['status']=='DRAFT'
    req=post(seller,f'/listings/{row["id"]}',{'status':'PENDING_REVIEW','expected_version':row['version']},'patch')
    assert req.status_code==200,req.text
    mod=post(admin,f'/admin/listings/{row["id"]}/moderate',{'status':'ACTIVE','reason':'testing'})
    assert mod.status_code==200,mod.text
    return mod.json()


def people():
    seller=create(TestClient(app),'seller@example.com')
    buyer=create(TestClient(app),'buyer@example.com')
    stranger=create(TestClient(app),'stranger@example.com')
    admin=create(TestClient(app),'admin@example.com')
    with SessionLocal() as db:
        db.get(User,admin['id']).role='ADMIN'
        db.commit()
    return seller,buyer,stranger,admin


def exp():return (datetime.now(timezone.utc)+timedelta(days=3)).isoformat()


def offer_payload(listing_id):
    return {'listing_id':listing_id,'offered_price_krw':70000,'terms':{'memo':'인수 후 실행 검증'},'expires_at':exp(),'is_demo':True}


def confirm_deal(seller,buyer,txid):
    res=buyer['client'].get(f'/api/v1/transactions/{txid}/agreement')
    digest=res.json()['agreement']['snapshot_sha256']
    for person in (seller,buyer):
        r=post(person,f'/transactions/{txid}/agreement/acknowledge',
               {'snapshot_sha256':digest,'understood_demo_only':True,'confirmed_terms':True})
        assert r.status_code==200,r.text


def test_register_login_csrf_and_owner_visibility():
    seller,buyer,stranger,admin=people()
    bad=seller['client'].post('/api/v1/listings',json=listing_payload())
    assert bad.status_code==403
    response=post(seller,'/listings',listing_payload())
    assert response.status_code==201
    row=response.json()
    assert row['status']=='DRAFT' and row['is_demo']
    assert buyer['client'].get('/api/v1/listings/'+row['id']).status_code==404
    assert post(buyer,f'/listings/{row["id"]}',{'expected_version':1,'title':'변조'},'patch').status_code==404
    assert buyer['client'].get('/api/v1/listings?include_demo=true').json()['total_estimate']==0


def test_offer_counter_accept_handover_workflow():
    seller,buyer,stranger,admin=people();row=setup_market(seller,buyer,admin)
    assert seller['client'].get('/api/v1/listings').json()['total_estimate']==0
    assert seller['client'].get('/api/v1/listings?include_demo=true').json()['total_estimate']==1
    denied=post(seller,'/offers',offer_payload(row['id']))
    assert denied.status_code==403
    create_offer=post(buyer,'/offers',offer_payload(row['id']))
    assert create_offer.status_code==201,create_offer.text
    o=create_offer.json()
    assert post(stranger,f'/offers/{o["id"]}/accept',{'expected_version':o['version']}).status_code==404
    assert post(buyer,f'/offers/{o["id"]}/accept',{'expected_version':o['version']}).status_code==403
    counter=post(seller,f'/offers/{o["id"]}/counter',{'offered_price_krw':90000,'terms':{'fix':'API 설정'},'expires_at':exp(),'expected_version':o['version']})
    assert counter.status_code==201,counter.text
    c=counter.json()
    assert c['parent_offer_id']==o['id']
    assert post(seller,f'/offers/{c["id"]}/accept',{'expected_version':c['version']}).status_code==403
    accepted=post(buyer,f'/offers/{c["id"]}/accept',{'expected_version':c['version']})
    assert accepted.status_code==201,accepted.text
    tx=accepted.json()
    assert tx['is_demo'] and tx['status']=='AWAITING_HANDOVER'
    assert post(buyer,f'/offers/{c["id"]}/accept',{'expected_version':c['version']}).status_code==409
    assert post(buyer,'/offers',offer_payload(row['id'])).status_code==409
    checks=seller['client'].get(f'/api/v1/transactions/{tx["id"]}/handover-checks').json()['items']
    assert len(checks)==4
    assert post(buyer,f'/transactions/{tx["id"]}/transition',{'expected_version':1,'status':'DEMO_COMPLETED'}).status_code==409
    confirm_deal(seller,buyer,tx['id'])
    started=post(seller,f'/transactions/{tx["id"]}/transition',{'expected_version':1,'status':'HANDOVER_IN_PROGRESS'})
    assert started.status_code==200
    for check in checks:
        x=post(seller,f'/transactions/{tx["id"]}/handover-checks/{check["id"]}',{'result':'SELLER_SUBMITTED','expected_version':check['version']},'patch')
        assert x.status_code==200,x.text
        y=post(buyer,f'/transactions/{tx["id"]}/handover-checks/{check["id"]}',{'result':'BUYER_CONFIRMED','expected_version':x.json()['version']},'patch')
        assert y.status_code==200,y.text
    review=post(seller,f'/transactions/{tx["id"]}/transition',{'expected_version':2,'status':'HANDOVER_REVIEW'})
    assert review.status_code==200
    done=post(buyer,f'/transactions/{tx["id"]}/transition',{'expected_version':3,'status':'DEMO_COMPLETED'})
    assert done.status_code==200,done.text
    assert done.json()['status']=='DEMO_COMPLETED'
    assert stranger['client'].get(f'/api/v1/transactions/{tx["id"]}').status_code==404


def test_agent_requires_approval_and_scoped_token():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    grant=post(buyer,'/auth/agent-grants',{'scopes':['offer:draft','offer:execute'],'expires_in_hours':1})
    assert grant.status_code==201,grant.text
    token=grant.json()['token']
    payload=offer_payload(listing['id'])
    agent={'client':TestClient(app),'id':buyer['id'],'csrf':''}
    headers={'Authorization':'Bearer '+token}
    create=agent['client'].post('/api/v1/agent-actions',json={'action_type':'SUBMIT_OFFER','resource_id':listing['id'],
                                                            'proposed_payload':payload,'payload_sha256':digest_payload(payload),'expires_at':exp()},headers=headers)
    assert create.status_code==201,create.text
    action=create.json()
    assert agent['client'].post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=headers).status_code==409
    assert agent['client'].post(f'/api/v1/agent-actions/{action["id"]}/approve',headers=headers).status_code==403
    assert post(seller,f'/agent-actions/{action["id"]}/approve').status_code==404
    assert post(buyer,f'/agent-actions/{action["id"]}/approve').status_code==200
    executed=agent['client'].post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=headers)
    assert executed.status_code==200,executed.text
    assert executed.json()['status']=='EXECUTED'
    assert agent['client'].post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=headers).status_code==409
    assert post(buyer,f'/auth/agent-grants/{grant.json()["id"]}/revoke').status_code==200
    assert agent['client'].get('/api/v1/offers',headers=headers).status_code==401


def test_moderation_rights_and_no_private_asset_leak():
    seller,buyer,stranger,admin=people();row=setup_market(seller,buyer,admin)
    assert TestClient(app).get(f'/api/v1/listings/{row["id"]}/assets').status_code==401
    # Authentication required; unrelated account cannot inspect source metadata.
    assert buyer['client'].get(f'/api/v1/listings/{row["id"]}/assets').status_code==404
    assert post(seller,f'/listings/{row["id"]}/asset-upload-intents').status_code==501
    assert post(buyer,f'/assets/{uuid4()}/download-intents').status_code==404
    assert post(admin,f'/admin/listings/{row["id"]}/moderate',{'status':'REMOVED','reason':'권리 침해 의심 신고 접수'}).status_code==200
    assert seller['client'].get('/api/v1/listings?include_demo=true').json()['total_estimate']==0


def test_invalid_listing_and_repeat_license_guard():
    seller,buyer,stranger,admin=people()
    payload=listing_payload()
    payload['sale_rights_type']='FULL_IP_ASSIGNMENT';payload['inventory_mode']='REPEAT_LICENSE'
    response=post(seller,'/listings',payload)
    assert response.status_code==422
    payload=listing_payload();payload['rights_attested']=False
    assert post(seller,'/listings',payload).status_code==422


def test_cancelled_demo_returns_one_time_listing_to_catalog():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    o=post(buyer,'/offers',offer_payload(listing['id'])).json()
    tx=post(seller,f'/offers/{o["id"]}/accept',{'expected_version':o['version']}).json()
    assert tx['status']=='AWAITING_HANDOVER'
    requested=post(seller,f'/transactions/{tx["id"]}/cancellations',{'reason':'판매자의 사정으로 모의 거래를 취소합니다.'})
    assert requested.status_code==201,requested.text
    cancelled=post(buyer,f'/transactions/{tx["id"]}/cancellations/{requested.json()["id"]}/respond',{'accept':True,'response_note':'상대방의 취소에 동의합니다.'})
    assert cancelled.status_code==200,cancelled.text
    new_offer=post(buyer,'/offers',offer_payload(listing['id']))
    assert new_offer.status_code==201,new_offer.text
    subsequent=post(seller,f'/offers/{new_offer.json()["id"]}/accept',{'expected_version':1})
    assert subsequent.status_code==201,subsequent.text


def test_offer_unauthorized_agent_scope_and_no_unsolicited_approval():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    grant=post(buyer,'/auth/agent-grants',{'scopes':['listing:read'],'expires_in_hours':1}).json()
    payload=offer_payload(listing['id'])
    headers={'Authorization':'Bearer '+grant['token']}
    r=TestClient(app).post('/api/v1/agent-actions',json={'action_type':'SUBMIT_OFFER','resource_id':listing['id'],
                      'proposed_payload':payload,'payload_sha256':digest_payload(payload),'expires_at':exp()},headers=headers)
    assert r.status_code==403
    assert buyer['client'].get('/api/v1/agent-actions').status_code==200
    assert buyer['client'].get('/api/v1/agent-actions').json()['items']==[]


def test_email_verification_development_flow_and_live_listing_review():
    seller,buyer,stranger,admin=people()
    data=listing_payload();data['is_demo']=False
    created=post(seller,'/listings',data)
    assert created.status_code==201
    rid=created.json()['id']
    req=post(seller,f'/listings/{rid}',{'status':'PENDING_REVIEW','expected_version':1},'patch')
    assert req.status_code==403
    mail=post(seller,'/auth/request-verification')
    assert mail.status_code==200,mail.text
    from urllib.parse import urlsplit,parse_qs
    url=mail.json()['development_verification_url']
    token=parse_qs(urlsplit(url).query)['token'][0]
    verified=seller['client'].post('/api/v1/auth/verify-email',json={'token':token})
    assert verified.status_code==200,verified.text
    req=post(seller,f'/listings/{rid}',{'status':'PENDING_REVIEW','expected_version':1},'patch')
    assert req.status_code==200,req.text


def test_offer_idempotent_post_and_accept():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    request=offer_payload(listing['id'])
    headers={'X-CSRF-Token':buyer['csrf'],'Idempotency-Key':'replay-12345'}
    a=buyer['client'].post('/api/v1/offers',json=request,headers=headers)
    b=buyer['client'].post('/api/v1/offers',json=request,headers=headers)
    assert a.status_code==201 and b.status_code==201
    assert a.json()['id']==b.json()['id']
    altered=dict(request,offered_price_krw=1000)
    assert buyer['client'].post('/api/v1/offers',json=altered,headers=headers).status_code==409
    h={'X-CSRF-Token':seller['csrf'],'Idempotency-Key':'accepted-replay-12345'}
    pa={'expected_version':a.json()['version']}
    first=seller['client'].post('/api/v1/offers/'+a.json()['id']+'/accept',json=pa,headers=h)
    second=seller['client'].post('/api/v1/offers/'+a.json()['id']+'/accept',json=pa,headers=h)
    assert first.status_code==201 and second.status_code==201
    assert first.json()['id']==second.json()['id']


def test_least_privilege_agent_token_cannot_read_offers_transactions_or_favorites():
    seller, buyer, stranger, admin = people()
    listing = setup_market(seller, buyer, admin)
    created = post(buyer, '/offers', offer_payload(listing['id']))
    assert created.status_code == 201
    offer = created.json()
    accepted = post(seller, f'/offers/{offer["id"]}/accept', {'expected_version': offer['version']})
    assert accepted.status_code == 201
    tx = accepted.json()
    grant = post(buyer, '/auth/agent-grants', {'scopes': ['listing:read'], 'expires_in_hours': 1})
    assert grant.status_code == 201
    headers = {'Authorization': 'Bearer ' + grant.json()['token']}
    agent = TestClient(app)
    assert agent.get('/api/v1/listings', headers=headers).status_code == 200  # listings themselves are public
    assert agent.get('/api/v1/my/listings', headers=headers).status_code == 200
    forbidden = [
        '/api/v1/offers', f'/api/v1/offers/{offer["id"]}',
        '/api/v1/transactions', f'/api/v1/transactions/{tx["id"]}',
        f'/api/v1/transactions/{tx["id"]}/handover-checks',
        f'/api/v1/listings/{listing["id"]}/inspection-reports',
        '/api/v1/favorites',
    ]
    for endpoint in forbidden:
        response = agent.get(endpoint, headers=headers)
        assert response.status_code == 403, (endpoint, response.text)


def test_scoped_agent_can_read_only_own_offers_and_not_others():
    seller, buyer, stranger, admin = people()
    listing = setup_market(seller, buyer, admin)
    created = post(buyer, '/offers', offer_payload(listing['id']))
    grant = post(buyer, '/auth/agent-grants', {'scopes': ['offer:read'], 'expires_in_hours': 1})
    headers = {'Authorization': 'Bearer ' + grant.json()['token']}
    client = TestClient(app)
    assert client.get('/api/v1/offers', headers=headers).status_code == 200
    assert len(client.get('/api/v1/offers', headers=headers).json()['items']) == 1
    grant2 = post(stranger, '/auth/agent-grants', {'scopes': ['offer:read'], 'expires_in_hours': 1})
    headers2 = {'Authorization': 'Bearer ' + grant2.json()['token']}
    assert client.get(f'/api/v1/offers/{created.json()["id"]}', headers=headers2).status_code == 404


def test_schema_and_payment_capability_guardrails():
    client = TestClient(app)
    capabilities = client.get('/api/v1/system/capabilities').json()
    assert capabilities['payments'] is False
    assert capabilities['private_asset_upload'] is True
    assert capabilities['automated_code_execution'] is False
    assert client.get('/openapi.json').status_code == 200
    assert 'POST' not in client.get('/openapi.json').json().get('paths', {}).get('/api/v1/payments', {})


def test_multiple_demo_offers_do_not_reserve_exclusive_asset():
    seller, buyer, other_buyer, admin = people()
    listing = setup_market(seller, buyer, admin)
    first = post(buyer, '/offers', offer_payload(listing['id'])).json()
    second = post(other_buyer, '/offers', offer_payload(listing['id'])).json()
    accepted = post(seller, f'/offers/{first["id"]}/accept', {'expected_version': first['version']})
    assert accepted.status_code == 201
    second_demo = post(seller, f'/offers/{second["id"]}/accept', {'expected_version': second['version']})
    assert second_demo.status_code == 201
    assert accepted.json()['is_demo'] is True
    assert len(seller['client'].get('/api/v1/transactions').json()['items']) == 2


def test_public_listing_response_does_not_include_private_upload_keys_or_passwords():
    seller, buyer, outsider, admin = people()
    listing = setup_market(seller, buyer, admin)
    response = outsider['client'].get(f'/api/v1/listings/{listing["id"]}?include_demo=true')
    assert response.status_code == 200
    result = response.json()
    for name in ['password_hash', 'private_object_key', 'token_hash', 'email', 'uploaded_by']:
        assert name not in result
    assert result['verification_status'] == 'UNVERIFIED'
    assert result['is_demo'] is True


def test_invalid_offer_requires_valid_future_expiration_and_no_self_dealing():
    seller, buyer, outsider, admin = people()
    listing = setup_market(seller, buyer, admin)
    assert post(seller, '/offers', offer_payload(listing['id'])).status_code == 403
    old = offer_payload(listing['id'])
    old['expires_at'] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert post(buyer, '/offers', old).status_code == 422
    bad = offer_payload(listing['id'])
    bad['offered_price_krw'] = 0
    assert post(buyer, '/offers', bad).status_code == 422


def test_validation_error_uses_safe_structured_contract_and_request_id():
    client = TestClient(app)
    request = client.post('/api/v1/auth/register', json={'email': 'invalid', 'password': 'short'},
                          headers={'X-Request-ID': 'regression-12345'})
    assert request.status_code == 422
    payload = request.json()
    assert payload['error']['code'] == 'VALIDATION_ERROR'
    assert payload['error']['request_id'] == 'regression-12345'
    assert request.headers['X-Request-ID'] == 'regression-12345'
    assert 'password_hash' not in request.text
    assert isinstance(payload['error']['details'], list)
