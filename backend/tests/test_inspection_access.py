"""v0.3 regression & security boundary tests. Every test uses isolated temp SQLite."""
import hashlib
from fastapi.testclient import TestClient
from app.main import app
from test_phase2 import upload, make_zip
from test_workflows import people,setup_market,post,offer_payload,confirm_deal


def token_for(user,scopes):
    result=post(user,'/auth/agent-grants',{'scopes':scopes,'expires_in_hours':1})
    assert result.status_code==201,result.text
    return {'Authorization':'Bearer '+result.json()['token']}


def test_consent_scoped_access_is_private_reversible_and_logged(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    archive=make_zip()
    asset=upload(seller,listing,'source.zip',archive).json()
    asset_id=asset['id']
    post(admin,f'/admin/assets/{asset_id}/review',{'status':'APPROVED','reason':'DEMO 확인한 원본'})
    mine=token_for(seller,['asset:inspect'])
    no_scope=token_for(seller,['listing:read'])
    endpoint=f'/api/v1/agent/assets/{asset_id}/inspection-content'
    assert TestClient(app).get(endpoint,headers=mine).status_code==404
    assert TestClient(app).get(endpoint,headers=no_scope).status_code==403
    assert seller['client'].get(endpoint).status_code==403
    assert post(seller,f'/assets/{asset_id}/inspection-accesses',{'principal_user_id':seller['id'],'purpose':'인수 전 소스코드 실사','expires_in_hours':1,'consent':False}).status_code==422
    granted=post(seller,f'/assets/{asset_id}/inspection-accesses',{'principal_user_id':seller['id'],'purpose':'인수 전 소스코드 정적 검사','expires_in_hours':1,'consent':True})
    assert granted.status_code==201,granted.text
    assert TestClient(app).get(endpoint,headers=mine).content==archive
    assert TestClient(app).get(endpoint,headers=mine).headers['cache-control']=='no-store, private'
    assert post(stranger,f'/assets/inspection-accesses/{granted.json()["id"]}/revoke').status_code==404
    assert post(seller,f'/assets/inspection-accesses/{granted.json()["id"]}/revoke').status_code==200
    assert TestClient(app).get(endpoint,headers=mine).status_code==404


def test_consent_to_other_account_requires_buyer_relationship(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    asset=upload(seller,listing,'project.zip',make_zip()).json()
    post(admin,f'/admin/assets/{asset["id"]}/review',{'status':'APPROVED','reason':'DEMO 정상 파일'})
    req={'principal_user_id':buyer['id'],'purpose':'잠재 인수자의 코드 검토','expires_in_hours':1,'consent':True}
    assert post(seller,f'/assets/{asset["id"]}/inspection-accesses',req).status_code==403
    assert post(buyer,'/offers',offer_payload(listing['id'])).status_code==201
    assert post(seller,f'/assets/{asset["id"]}/inspection-accesses',req).status_code==201
    headers=token_for(buyer,['asset:inspect'])
    assert TestClient(app).get(f'/api/v1/agent/assets/{asset["id"]}/inspection-content',headers=headers).status_code==200
    stranger_token=token_for(stranger,['asset:inspect'])
    assert TestClient(app).get(f'/api/v1/agent/assets/{asset["id"]}/inspection-content',headers=stranger_token).status_code==404


def test_only_buyer_can_confirm_fix_before_demo_completion():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    offer=post(buyer,'/offers',offer_payload(listing['id'])).json()
    tx=post(seller,f'/offers/{offer["id"]}/accept',{'expected_version':1}).json()
    txid=tx['id']
    checks=seller['client'].get(f'/api/v1/transactions/{txid}/handover-checks').json()['items']
    confirm_deal(seller,buyer,txid)
    assert post(seller,f'/transactions/{txid}/transition',{'expected_version':1,'status':'HANDOVER_IN_PROGRESS'}).status_code==200
    for item in checks:
        r=post(seller,f'/transactions/{txid}/handover-checks/{item["id"]}',{'result':'SELLER_SUBMITTED','expected_version':item['version']},'patch')
        assert r.status_code==200,r.text
        r=post(buyer,f'/transactions/{txid}/handover-checks/{item["id"]}',{'result':'BUYER_CONFIRMED','expected_version':r.json()['version']},'patch')
        assert r.status_code==200,r.text
    fix=post(buyer,f'/transactions/{txid}/fix-requests',{'description':'필수 API 설정 문서를 다시 제출해 주세요.'}).json()
    assert post(seller,f'/transactions/{txid}/transition',{'expected_version':2,'status':'HANDOVER_REVIEW'}).status_code==200
    assert post(buyer,f'/transactions/{txid}/transition',{'expected_version':3,'status':'DEMO_COMPLETED'}).status_code==409
    assert post(seller,f'/transactions/{txid}/fix-requests/{fix["id"]}/resolve',{'status':'RESOLVED','resolution_note':'설정 문서 공유함'}).status_code==200
    assert post(buyer,f'/transactions/{txid}/transition',{'expected_version':3,'status':'DEMO_COMPLETED'}).status_code==409
    assert post(stranger,f'/transactions/{txid}/fix-requests/{fix["id"]}/confirm').status_code==404
    assert post(seller,f'/transactions/{txid}/fix-requests/{fix["id"]}/confirm').status_code==403
    assert post(buyer,f'/transactions/{txid}/fix-requests/{fix["id"]}/confirm').status_code==200
    assert post(buyer,f'/transactions/{txid}/transition',{'expected_version':3,'status':'DEMO_COMPLETED'}).status_code==200


def test_buyer_approval_reset_when_handover_result_changes():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    offer=post(buyer,'/offers',offer_payload(listing['id'])).json()
    tx=post(seller,f'/offers/{offer["id"]}/accept',{'expected_version':1}).json()
    checks=seller['client'].get(f'/api/v1/transactions/{tx["id"]}/handover-checks').json()['items']
    c=checks[0]
    submitted=post(seller,f'/transactions/{tx["id"]}/handover-checks/{c["id"]}',{'result':'SELLER_SUBMITTED','expected_version':c['version']},'patch').json()
    approved=post(buyer,f'/transactions/{tx["id"]}/handover-checks/{c["id"]}',{'result':'BUYER_CONFIRMED','expected_version':submitted['version']},'patch').json()
    assert approved['buyer_confirmed']
    needs=post(buyer,f'/transactions/{tx["id"]}/handover-checks/{c["id"]}',{'result':'NEEDS_FIX','expected_version':approved['version']},'patch').json()
    assert not needs['buyer_confirmed'] and not needs['seller_submitted']
    assert post(buyer,f'/transactions/{tx["id"]}/handover-checks/{c["id"]}',{'result':'BUYER_CONFIRMED','expected_version':needs['version']},'patch').status_code==409
    resubmitted=post(seller,f'/transactions/{tx["id"]}/handover-checks/{c["id"]}',{'result':'SELLER_SUBMITTED','expected_version':needs['version']},'patch').json()
    assert resubmitted['seller_submitted'] and not resubmitted['buyer_confirmed']


