"""Security and API-contract tests for direct Streamlit -> ProjectAgain integration."""
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app, digest_payload
from test_phase2 import upload, make_zip
from test_workflows import people, setup_market, listing_payload, post, offer_payload


def agent_token(user, scopes):
    r=post(user,'/auth/agent-grants',{'scopes':scopes,'expires_in_hours':1})
    assert r.status_code==201, r.text
    return {'Authorization':'Bearer '+r.json()['token']}


def draft_action(token, listing_id):
    payload=offer_payload(listing_id)
    data={'action_type':'SUBMIT_OFFER','resource_id':listing_id,
          'proposed_payload':payload,'payload_sha256':digest_payload(payload),
          'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    return data


def test_my_listings_response_remains_array_and_public_pagination_is_offset():
    seller,buyer,stranger,admin=people(); l=setup_market(seller,buyer,admin)
    mine=seller['client'].get('/api/v1/my/listings').json()
    assert isinstance(mine,list) and mine[0]['id']==l['id']
    q=TestClient(app).get('/api/v1/listings?include_demo=true&limit=1&cursor=0')
    assert q.status_code==200
    assert isinstance(q.json()['items'],list)
    assert q.json()['next_cursor'] is None or q.json()['next_cursor'].isdigit()
    assert isinstance(q.json()['total_estimate'],int)
    assert 'proposed_by' in post(buyer,'/offers',offer_payload(l['id'])).json()


def test_only_seller_authorized_assets_are_discoverable(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people(); l=setup_market(seller,buyer,admin)
    asset=upload(seller,l,'confidential.zip',make_zip()).json()
    endpoint=f'/api/v1/agent/listings/{l["id"]}/inspection-assets'
    buyer_hdr=agent_token(buyer,['asset:inspect','inspection:write'])
    stranger_hdr=agent_token(stranger,['asset:inspect'])
    seller_no_scope=agent_token(seller,['listing:read'])
    assert TestClient(app).get(endpoint,headers=buyer_hdr).json()['items']==[]
    assert TestClient(app).get(endpoint,headers=seller_no_scope).status_code==403
    assert TestClient(app).get(endpoint,headers=stranger_hdr).json()['items']==[]
    assert seller['client'].get(endpoint).status_code==403
    post(admin,f'/admin/assets/{asset["id"]}/review',{'status':'APPROVED','reason':'DEMO 파일 검토 완료'})
    # No buyer relationship yet, so seller cannot approve direct access.
    consent={'principal_user_id':buyer['id'],'purpose':'구매 전 소스코드 정적 실사 수행','expires_in_hours':1,'consent':True}
    assert post(seller,f'/assets/{asset["id"]}/inspection-accesses',consent).status_code==403
    assert post(buyer,'/offers',offer_payload(l['id'])).status_code==201
    granted=post(seller,f'/assets/{asset["id"]}/inspection-accesses',consent)
    assert granted.status_code==201,granted.text
    result=TestClient(app).get(endpoint,headers=buyer_hdr)
    assert result.status_code==200,result.text
    items=result.json()['items']
    assert len(items)==1 and items[0]['id']==asset['id']
    assert items[0]['checksum_sha256']==asset['checksum_sha256']
    assert 'private_object_key' not in str(items)
    assert TestClient(app).get(endpoint,headers=stranger_hdr).json()['items']==[]
    assert post(seller,f'/assets/inspection-accesses/{granted.json()["id"]}/revoke').status_code==200
    assert TestClient(app).get(endpoint,headers=buyer_hdr).json()['items']==[]


def test_buyer_agent_report_requires_matching_approved_file_and_consent(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people(); l=setup_market(seller,buyer,admin)
    asset=upload(seller,l,'project.zip',make_zip()).json()
    post(admin,f'/admin/assets/{asset["id"]}/review',{'status':'APPROVED','reason':'DEMO 원본 확인'})
    hdr=agent_token(buyer,['inspection:write','asset:inspect','inspection:read'])
    url=f'/api/v1/listings/{l["id"]}/inspection-reports'
    report={'report_type':'STATIC','verdict':'PARTIAL','findings':[{'issue':'needs setup'}],
            'evidence_refs':[],'source_version_sha256':asset['checksum_sha256']}
    assert TestClient(app).post(url,json=report,headers=hdr).status_code==403
    post(buyer,'/offers',offer_payload(l['id']))
    consent={'principal_user_id':buyer['id'],'purpose':'구매 전 정적 코드 실사와 보고','expires_in_hours':1,'consent':True}
    grant=post(seller,f'/assets/{asset["id"]}/inspection-accesses',consent).json()
    assert TestClient(app).post(url,json={**report,'source_version_sha256':'b'*64},headers=hdr).status_code==403
    idempotent={**hdr,'Idempotency-Key':'report-unique-request-0001'}
    result=TestClient(app).post(url,json=report,headers=idempotent)
    assert result.status_code==201,result.text
    assert result.json()['reviewer_kind']=='AI_AGENT' and result.json()['is_public'] is False
    assert TestClient(app).post(url,json=report,headers=idempotent).json()['id']==result.json()['id']
    assert TestClient(app).post(url,json={**report,'verdict':'FAIL'},headers=idempotent).status_code==409
    # Original seller and submitting buyer can read; other buyer cannot view private findings.
    assert len(seller['client'].get(url).json()['items'])==1
    assert len(TestClient(app).get(url,headers=hdr).json()['items'])==1
    assert stranger['client'].get(url).json()['items']==[]
    assert post(seller,f'/listings/{l["id"]}/inspection-reports/{result.json()["id"]}/visibility',{'is_public':True}).status_code==403
    post(seller,f'/assets/inspection-accesses/{grant["id"]}/revoke')
    assert TestClient(app).post(url,json=report,headers={**hdr,'Idempotency-Key':'report-unique-request-0002'}).status_code==403


def test_agent_drafts_and_execution_idempotency_and_mode(monkeypatch):
    seller,buyer,stranger,admin=people(); l=setup_market(seller,buyer,admin)
    hdr=agent_token(buyer,['offer:draft','offer:execute'])
    uri='/api/v1/agent-actions'
    data=draft_action(hdr,l['id'])
    h={**hdr,'Idempotency-Key':'draft-1234567890'}
    first=TestClient(app).post(uri,json=data,headers=h)
    assert first.status_code==201,first.text
    assert TestClient(app).post(uri,json=data,headers=h).json()['id']==first.json()['id']
    assert TestClient(app).post(uri,json={**data,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()},headers=h).status_code==409
    id_=first.json()['id']
    assert post(buyer,f'/agent-actions/{id_}/approve').status_code==200
    monkeypatch.setenv('AGENT_WRITE_MODE','disabled')
    assert TestClient(app).post(f'{uri}/{id_}/execute',headers={**hdr,'Idempotency-Key':'execute-123456789'}).status_code==403
    monkeypatch.setenv('AGENT_WRITE_MODE','demo_only')
    eh={**hdr,'Idempotency-Key':'execute-123456789'}
    ok=TestClient(app).post(f'{uri}/{id_}/execute',headers=eh)
    assert ok.status_code==200,ok.text
    again=TestClient(app).post(f'{uri}/{id_}/execute',headers=eh)
    assert again.status_code==200 and again.json()['result_resource_id']==ok.json()['result_resource_id']
    assert TestClient(app).post(f'{uri}/{id_}/execute',headers={**hdr,'Idempotency-Key':'execute-different-key'}).status_code==409
    caps=TestClient(app).get('/api/v1/system/capabilities').json()
    assert caps['agent_live_writes'] is False and caps['agent_write_mode']=='demo_only'
    assert caps['agent_inspection_asset_discovery'] is True


def test_non_demo_listing_cannot_be_modified_by_agent(monkeypatch):
    seller,buyer,stranger,admin=people()
    payload=listing_payload();payload['is_demo']=False
    row=post(seller,'/listings',payload).json()
    hdr=agent_token(seller,['listing:draft','listing:execute'])
    proposal={'expected_version':row['version'],'title':'판매 정보를 정리한 매물'}
    data={'action_type':'SUGGEST_LISTING_UPDATE','resource_id':row['id'],
          'proposed_payload':proposal,'payload_sha256':digest_payload(proposal),
          'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    create=TestClient(app).post('/api/v1/agent-actions',headers=hdr,json=data)
    assert create.status_code==201,create.text
    action=create.json()
    assert post(seller,f'/agent-actions/{action["id"]}/approve').status_code==200
    monkeypatch.setenv('AGENT_WRITE_MODE','demo_only')
    assert TestClient(app).post(f'/api/v1/agent-actions/{action["id"]}/execute',headers=hdr).status_code==403
    assert post(seller,f'/agent-actions/{action["id"]}/execute').status_code==403
    assert seller['client'].get(f'/api/v1/listings/{row["id"]}').json()['title']==row['title']
