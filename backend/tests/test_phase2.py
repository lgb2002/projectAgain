import hashlib
import io
import zipfile
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models import User
from app.db import SessionLocal
from test_workflows import people,setup_market,post,offer_payload,confirm_deal


def upload(seller,listing,filename,data):
    return seller['client'].post('/api/v1/listings/'+listing['id']+'/assets/upload',
        files={'file':(filename,data,'application/octet-stream')},headers={'X-CSRF-Token':seller['csrf']})


def make_zip(entries=None):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,content in (entries or {'README.md':'안전한 실행 안내','src/app.py':'print("hello")'}).items():z.writestr(name,content)
    return b.getvalue()


def ticket(user,id):return post(user,f'/assets/{id}/download-intents')


def test_files_are_private_single_use_and_expire(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    source=make_zip()
    missing=upload(stranger,listing,'source.zip',source)
    assert missing.status_code==404
    a=upload(seller,listing,'source.zip',source)
    assert a.status_code==201,a.text
    obj=a.json()
    assert obj['upload_status']=='QUARANTINED' and obj['malware_scan_status']=='NOT_PERFORMED'
    assert 'private_object_key' not in obj
    assert seller['client'].get(f'/api/v1/listings/{listing["id"]}/assets').status_code==200
    assert buyer['client'].get(f'/api/v1/listings/{listing["id"]}/assets').status_code==404
    assert ticket(seller,obj['id']).status_code==409
    approve=post(admin,f'/admin/assets/{obj["id"]}/review',{'status':'APPROVED','reason':'검수용 DEMO 전용 자료'})
    assert approve.status_code==200,approve.text
    assert ticket(stranger,obj['id']).status_code==404
    issued=ticket(seller,obj['id'])
    assert issued.status_code==201
    payload={'token':issued.json()['ticket']}
    assert post(buyer,'/assets/redeem',payload).status_code==404
    retrieved=post(seller,'/assets/redeem',payload)
    assert retrieved.status_code==200 and retrieved.content==source
    assert retrieved.headers['content-type'].startswith('application/octet-stream')
    assert post(seller,'/assets/redeem',payload).status_code==410
    assert len(list(tmp_path.rglob('*')))>0


def test_seller_explicit_share_after_demo_transaction_and_revoke(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    obj=upload(seller,listing,'transfer.zip',make_zip()).json()
    post(admin,f'/admin/assets/{obj["id"]}/review',{'status':'APPROVED','reason':'DEMO 검수 승인'})
    offer=post(buyer,'/offers',offer_payload(listing['id'])).json()
    tx=post(seller,f'/offers/{offer["id"]}/accept',{'expected_version':offer['version']}).json()
    assert buyer['client'].get(f'/api/v1/transactions/{tx["id"]}/shared-assets').json()['items']==[]
    assert post(buyer,f'/assets/{obj["id"]}/shares',{'transaction_id':tx['id']}).status_code==404
    assert post(seller,f'/assets/{obj["id"]}/shares',{'transaction_id':tx['id']}).status_code==409
    confirm_deal(seller,buyer,tx['id'])
    shared=post(seller,f'/assets/{obj["id"]}/shares',{'transaction_id':tx['id']})
    assert shared.status_code==201,shared.text
    assert ticket(buyer,obj['id']).status_code==201
    assert ticket(stranger,obj['id']).status_code==404
    assert buyer['client'].get(f'/api/v1/transactions/{tx["id"]}/shared-assets').json()['items'][0]['file_name']=='transfer.zip'
    assert post(seller,f'/assets/shares/{shared.json()["id"]}/revoke').status_code==200
    assert ticket(buyer,obj['id']).status_code==404


def test_archive_screen_rejects_traversal_and_credentials(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    for name,content in [ ('../escape',b'evil'),('.env',b'SECRET=x')]:
        bad=upload(seller,listing,'bad.zip',make_zip({name:content}))
        assert bad.status_code==422,bad.text
    assert upload(seller,listing,'file.pdf',b'malicious script').status_code==422
    assert upload(seller,listing,'bad.exe',b'foo').status_code==422
    assert upload(seller,listing,'safe.txt',b'text data').status_code==201


def test_no_production_release_without_external_antivirus(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    obj=upload(seller,listing,'source.zip',make_zip()).json()
    monkeypatch.setenv('APP_ENV','production')
    denied=post(admin,f'/admin/assets/{obj["id"]}/review',{'status':'APPROVED','reason':'검수했다고 주장함'})
    assert denied.status_code==409
    monkeypatch.setenv('APP_ENV','test')


def test_agent_bearer_direct_no_middle_agent_service_and_report_visibility():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    token=post(seller,'/auth/agent-grants',{'scopes':['listing:read','inspection:write','inspection:read'],'expires_in_hours':1}).json()['token']
    headers={'Authorization':'Bearer '+token}
    context=TestClient(app).get('/api/v1/agent/context',headers=headers)
    assert context.status_code==200 and context.json()['no_agent_server_required']
    own=TestClient(app).post(f'/api/v1/listings/{listing["id"]}/inspection-reports',headers=headers,json={
        'report_type':'STATIC','verdict':'PARTIAL','findings':[{'code':'ENV_DEPENDENCY','message':'API 설정을 다시 해야 합니다'}],
        'source_version_sha256':'a'*64,'evidence_refs':[]})
    assert own.status_code==201,own.text
    report=own.json()
    assert report['reviewer_kind']=='AI_AGENT'
    public=buyer['client'].get(f'/api/v1/listings/{listing["id"]}/inspection-reports')
    assert public.status_code==200 and public.json()['items']==[]
    released=post(seller,f'/listings/{listing["id"]}/inspection-reports/{report["id"]}/visibility',{'is_public':True})
    assert released.status_code==200
    visible=buyer['client'].get(f'/api/v1/listings/{listing["id"]}/inspection-reports')
    assert visible.status_code==200 and visible.json()['items'][0]['verdict']=='PARTIAL'
    assert TestClient(app).get('/api/v1/agent/context').status_code==401
    bad=post(buyer,f'/listings/{listing["id"]}/inspection-reports',{
        'report_type':'STATIC','verdict':'PASS','findings':[]})
    assert bad.status_code==403


def test_password_reset_revokes_existing_sessions_and_agent_grants():
    seller,buyer,stranger,admin=people()
    bearer=post(seller,'/auth/agent-grants',{'scopes':['listing:read'],'expires_in_hours':1}).json()['token']
    begin=TestClient(app).post('/api/v1/auth/request-password-reset',json={'email':'seller@example.com'})
    assert begin.status_code==200,begin.text
    token=begin.json()['development_reset_token']
    again=TestClient(app).post('/api/v1/auth/request-password-reset',json={'email':'seller@example.com'})
    assert again.status_code==429
    complete=TestClient(app).post('/api/v1/auth/confirm-password-reset',json={'token':token,'new_password':'DifferentPasswordIsLong2026!'})
    assert complete.status_code==200,complete.text
    assert TestClient(app).post('/api/v1/auth/confirm-password-reset',json={'token':token,'new_password':'AnotherLongPassword2026!!'}).status_code==400
    assert seller['client'].get('/api/v1/auth/me').status_code==401
    assert TestClient(app).get('/api/v1/agent/context',headers={'Authorization':'Bearer '+bearer}).status_code==401
    assert seller['client'].post('/api/v1/auth/login',json={'email':'seller@example.com','password':'DifferentPasswordIsLong2026!'}).status_code==200


def test_fix_request_seller_replies_and_notifications():
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    offer=post(buyer,'/offers',offer_payload(listing['id'])).json()
    notifications=seller['client'].get('/api/v1/notifications').json()['items']
    assert any(x['kind']=='OFFER_RECEIVED' for x in notifications)
    tx=post(seller,f'/offers/{offer["id"]}/accept',{'expected_version':1}).json()
    need=post(buyer,f'/transactions/{tx["id"]}/fix-requests',{'description':'실행 전에 환경변수 설정 문서가 필요합니다.'})
    assert need.status_code==201,need.text
    req=need.json()
    assert post(stranger,f'/transactions/{tx["id"]}/fix-requests/{req["id"]}/resolve',{'status':'RESOLVED','resolution_note':'처리되었습니다'}).status_code==404
    resolved=post(seller,f'/transactions/{tx["id"]}/fix-requests/{req["id"]}/resolve',{'status':'RESOLVED','resolution_note':'설정 문서를 전달했습니다.'})
    assert resolved.status_code==200
    assert post(seller,f'/transactions/{tx["id"]}/fix-requests/{req["id"]}/resolve',{'status':'RESOLVED','resolution_note':'처리되었습니다'}).status_code==409
    assert buyer['client'].get('/api/v1/notifications').json()['unread']>=1
    noti=buyer['client'].get('/api/v1/notifications').json()['items'][0]
    assert post(stranger,f'/notifications/{noti["id"]}/read').status_code==404
    assert post(buyer,f'/notifications/{noti["id"]}/read').status_code==200


def test_static_inspection_is_a_real_report_but_not_execution(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    archive=make_zip({'README.md':'설치 설명입니다.','package.json':'{"name":"small-tool","scripts":{"start":"node app.js"}}','app.js':'alert(1)'})
    asset=upload(seller,listing,'sample.zip',archive).json()
    forbidden=post(buyer,f'/assets/{asset["id"]}/static-inspections')
    assert forbidden.status_code==404
    scan=post(seller,f'/assets/{asset["id"]}/static-inspections')
    assert scan.status_code==201,scan.text
    result=scan.json()
    assert result['level']=='DETERMINISTIC_FILE_CHECK_ONLY'
    assert result['verdict']=='PARTIAL'
    assert result['source_version_sha256']==hashlib.sha256(archive).hexdigest()
    assert any(f['code']=='DEPLOYMENT' for f in result['findings'])
    assert any(f['code']=='STATIC_ONLY' for f in result['findings'])
    assert buyer['client'].get(f'/api/v1/listings/{listing["id"]}/inspection-reports').json()['items']==[]


def test_agent_fix_request_is_drafted_approved_then_executed():
    from datetime import datetime,timedelta,timezone
    from app.main import digest_payload
    seller,buyer,stranger,admin=people();listing=setup_market(seller,buyer,admin)
    offer=post(buyer,'/offers',offer_payload(listing['id'])).json()
    tx=post(seller,f'/offers/{offer["id"]}/accept',{'expected_version':1}).json()
    grant=post(buyer,'/auth/agent-grants',{'scopes':['handover:draft','handover:execute'],'expires_in_hours':1}).json()
    headers={'Authorization':'Bearer '+grant['token']}
    payload={'description':'실제 배포 재현용 환경변수 예시와 설정 설명이 누락되었습니다.'}
    expiry=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    req=TestClient(app).post('/api/v1/agent-actions',headers=headers,json={
        'action_type':'REQUEST_SELLER_FIX','resource_id':tx['id'],
        'proposed_payload':payload,'payload_sha256':digest_payload(payload),'expires_at':expiry})
    assert req.status_code==201,req.text
    rid=req.json()['id']
    assert TestClient(app).post(f'/api/v1/agent-actions/{rid}/execute',headers=headers).status_code==409
    assert post(seller,f'/agent-actions/{rid}/approve').status_code==404
    assert post(buyer,f'/agent-actions/{rid}/approve').status_code==200
    done=TestClient(app).post(f'/api/v1/agent-actions/{rid}/execute',headers=headers)
    assert done.status_code==200,done.text
    assert len(buyer['client'].get(f'/api/v1/transactions/{tx["id"]}/fix-requests').json()['items'])==1
    assert TestClient(app).post(f'/api/v1/agent-actions/{rid}/execute',headers=headers).status_code==409
