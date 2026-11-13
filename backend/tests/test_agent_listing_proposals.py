"""API-only listing suggestion handoff: no platform LLM, seller approves all updates."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from app.main import app, digest_payload
from test_workflows import people, setup_market, post


def token(user, scopes):
    out=post(user, '/auth/agent-grants', {'scopes':scopes,'expires_in_hours':1})
    assert out.status_code==201,out.text
    return {'Authorization':'Bearer '+out.json()['token']}


def request(header, action_type, resource_id, payload):
    return TestClient(app).post('/api/v1/agent-actions',headers=header,json={
        'action_type':action_type, 'resource_id':resource_id,'proposed_payload':payload,
        'payload_sha256':digest_payload(payload),
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()})


def payload(listing):
    return {'expected_version':listing['version'],'title':'개선된 판매 설명',
            'description':'기존에 제공되는 구성과 한계만 확인 가능한 범위에서 정리한 프로젝트 판매 안내입니다.'}


def test_platform_does_not_expose_seller_llm_or_require_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','would-not-be-used')
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    assert seller['client'].get(f'/api/v1/listings/{listing["id"]}/ai-assistant/status').status_code==404
    assert post(seller,f'/listings/{listing["id"]}/ai-assistant/drafts',{'send_to_openai':True}).status_code==404
    caps=seller['client'].get('/api/v1/system/capabilities').json()
    assert caps['platform_llm_calls'] is False
    assert caps['agent_listing_update_proposal'] is True
    paths=TestClient(app).get('/openapi.json').json()['paths']
    assert not any('/ai-assistant/' in key for key in paths)


def test_preparation_context_is_private_and_scoped():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    uri=f'/api/v1/agent/listings/{listing["id"]}/preparation-context'
    assert TestClient(app).get(uri).status_code==401
    assert seller['client'].get(uri).status_code==403
    assert TestClient(app).get(uri,headers=token(buyer,['listing:read'])).status_code==404
    assert TestClient(app).get(uri,headers=token(seller,['listing:draft'])).status_code==403
    t=token(seller,['listing:read'])
    result=TestClient(app).get(uri,headers=t)
    assert result.status_code==200,result.text
    assert result.json()['listing']['id']==listing['id']
    assert result.json()['code_execution_performed'] is False
    assert 'private_source' not in result.text


def test_agent_suggestion_approval_and_review_flow():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    draft_token=token(seller,['listing:draft'])
    execute_token=token(seller,['listing:execute'])
    initial=listing.copy()
    data=payload(listing)
    res=request(draft_token,'SUGGEST_LISTING_UPDATE',listing['id'],data)
    assert res.status_code==201,res.text
    action=res.json()
    assert action['status']=='PENDING_APPROVAL'
    # Creating and receiving proposals never changes the listing.
    check=seller['client'].get(f'/api/v1/listings/{listing["id"]}?include_demo=true').json()
    assert check['title']==initial['title'] and check['price_krw']==initial['price_krw']
    assert post(buyer,f'/agent-actions/{action["id"]}/approve').status_code==404
    assert post(seller,f'/agent-actions/{action["id"]}/execute').status_code==409
    assert TestClient(app).post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=draft_token).status_code==403
    approved=post(seller,f'/agent-actions/{action["id"]}/approve')
    assert approved.status_code==200,approved.text
    applied=TestClient(app).post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=execute_token)
    assert applied.status_code==200,applied.text
    assert applied.json()['status']=='EXECUTED'
    updated=seller['client'].get(f'/api/v1/listings/{listing["id"]}?include_demo=true').json()
    assert updated['title']==data['title']
    assert updated['description']==data['description']
    assert updated['price_krw']==initial['price_krw']
    assert updated['sale_rights_type']==initial['sale_rights_type']
    assert updated['status']=='PENDING_REVIEW'
    assert updated['version']==initial['version']+1
    assert TestClient(app).post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=execute_token).status_code==409


def test_human_can_apply_only_listing_updates_not_other_agent_actions():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    draft_token=token(seller,['listing:draft'])
    req=request(draft_token,'SUGGEST_LISTING_UPDATE',listing['id'],payload(listing)).json()
    assert post(seller,f'/agent-actions/{req["id"]}/approve').status_code==200
    done=post(seller,f'/agent-actions/{req["id"]}/execute')
    assert done.status_code==200,done.text
    assert done.json()['status']=='EXECUTED'


def test_no_privilege_escalation_no_price_change_and_no_unauthorized_scope():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    s=token(seller,['listing:draft'])
    forbidden={'expected_version':listing['version'],'title':'공격','price_krw':1}
    assert request(s,'SUGGEST_LISTING_UPDATE',listing['id'],forbidden).status_code==422
    assert request(token(buyer,['listing:draft']),'SUGGEST_LISTING_UPDATE',listing['id'],payload(listing)).status_code==404
    assert request(token(seller,['listing:read']),'SUGGEST_LISTING_UPDATE',listing['id'],payload(listing)).status_code==403
    assert request(s,'SUGGEST_LISTING_UPDATE',listing['id'],{'expected_version':listing['version']}).status_code==422
    invalid={'expected_version':listing['version'],'description':'no'}
    assert request(s,'SUGGEST_LISTING_UPDATE',listing['id'],invalid).status_code==422
    assert request(s,'SUGGEST_LISTING_UPDATE',listing['id'],{'expected_version':listing['version'],'status':'ACTIVE'}).status_code==422


def test_stale_draft_is_not_applied_even_if_approved():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    s=token(seller,['listing:draft','listing:execute'])
    action=request(s,'SUGGEST_LISTING_UPDATE',listing['id'],payload(listing)).json()
    updated=post(seller,f'/listings/{listing["id"]}',{'expected_version':listing['version'],'title':'판매자가 먼저 수정한 제목'},'patch')
    assert updated.status_code==200
    assert post(seller,f'/agent-actions/{action["id"]}/approve').status_code==200
    attempt=TestClient(app).post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=s)
    assert attempt.status_code==409
    actual=seller['client'].get(f'/api/v1/listings/{listing["id"]}?include_demo=true').json()
    assert actual['title']=='판매자가 먼저 수정한 제목'


def test_agent_may_read_only_actions_matching_its_draft_scope():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    s=token(seller,['listing:draft'])
    action=request(s,'SUGGEST_LISTING_UPDATE',listing['id'],payload(listing)).json()
    other=token(seller,['offer:draft'])
    assert TestClient(app).get('/api/v1/agent-actions',headers=other).json()['items']==[]
    assert TestClient(app).get(f'/api/v1/agent-actions/{action["id"]}',headers=other).status_code==403
    assert len(TestClient(app).get('/api/v1/agent-actions',headers=s).json()['items'])==1


def test_rejected_listing_suggestion_cannot_execute():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    s=token(seller,['listing:draft','listing:execute'])
    action=request(s,'SUGGEST_LISTING_UPDATE',listing['id'],payload(listing)).json()
    assert post(seller,f'/agent-actions/{action["id"]}/reject').status_code==200
    assert TestClient(app).post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=s).status_code==409


def test_other_agent_action_invalid_payload_is_cleanly_rejected():
    seller,buyer,stranger,admin=people(); listing=setup_market(seller,buyer,admin)
    t=token(buyer,['offer:draft'])
    invalid={'listing_id':listing['id'],'offered_price_krw':-1}
    r=request(t,'SUBMIT_OFFER',listing['id'],invalid)
    assert r.status_code==422,r.text
    assert 'price' not in r.text.lower() or r.json()['detail']
