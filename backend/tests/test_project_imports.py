"""Source import must be seller-owned, bounded, and never leak private source."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import SessionLocal
from app.main import app
from app.models import ListingAsset, ProjectImport, ListingSourceSummary
from app.github_source import parse_repo, verify_oauth_state
from test_workflows import create, post, listing_payload


def archive(files=None):
    result = BytesIO()
    with ZipFile(result, 'w', ZIP_DEFLATED) as z:
        for name, content in (files or {
            'project/README.md': '# Sample app',
            'project/package.json': '{"dependencies":{"react":"19.0.0","vite":"6.0.0"}}',
            'project/src/auth.ts': 'export function login() {}',
            'project/tests/test_auth.py': 'def test_auth(): pass',
        }).items(): z.writestr(name, content)
    return result.getvalue()


def upload_import(seller, blob=None):
    return seller['client'].post('/api/v1/listing-imports/zip',
        headers={'X-CSRF-Token':seller['csrf']},
        files={'file': ('sample.zip', blob or archive(), 'application/zip')})


def test_zip_auto_fills_and_private_source_gated(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR', str(tmp_path))
    seller = create(TestClient(app), 'seller-import@example.com')
    buyer = create(TestClient(app), 'buyer-import@example.com')
    pending = upload_import(seller)
    assert pending.status_code == 201, pending.text
    imported = pending.json()
    assert imported['analysis']['tech_stack'] == ['JavaScript', 'React', 'Vite']
    assert imported['analysis']['code_executed'] is False
    assert '인증 관련 코드' in imported['analysis']['possible_features']
    assert buyer['client'].get('/api/v1/listing-imports/'+imported['id']).status_code == 404
    info = seller['client'].get('/api/v1/listing-imports/'+imported['id'])
    assert info.status_code == 200
    payload = listing_payload(); payload['import_id'] = imported['id']; payload['tech_stack'] = imported['analysis']['tech_stack']
    response = post(seller, '/listings', payload)
    assert response.status_code == 201, response.text
    listing = response.json()
    assert post(seller, '/listings', payload).status_code == 409
    assert buyer['client'].get('/api/v1/listings/'+listing['id']+'/source-summary').status_code == 404
    summary = seller['client'].get('/api/v1/listings/'+listing['id']+'/source-summary').json()
    assert summary['available'] and summary['source_type']=='ZIP'
    assert 'description_suggestion' not in summary['analysis']
    assert 'source_label' not in summary
    with SessionLocal() as db:
        asset = db.scalar(select(ListingAsset).where(ListingAsset.listing_id==listing['id']))
        source = db.get(ProjectImport, imported['id'])
        assert source.status=='ATTACHED' and source.listing_id==listing['id']
        assert asset.private_object_key==source.object_key and asset.upload_status=='QUARANTINED'
        assert asset.checksum_sha256==imported['checksum_sha256']
        assert db.get(ListingSourceSummary, listing['id'])
    assert buyer['client'].get('/api/v1/listings/'+listing['id']+'/assets').status_code==404


def test_source_ownership_rights_and_reject_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR', str(tmp_path))
    seller = create(TestClient(app), 'source-seller@example.com')
    intruder = create(TestClient(app), 'source-intruder@example.com')
    imported = upload_import(seller).json()
    payload = listing_payload();payload['import_id']=imported['id']
    assert post(intruder,'/listings', payload).status_code == 409
    payload['rights_attested'] = False
    assert post(seller,'/listings', payload).status_code == 422
    assert upload_import(seller,archive({'project/.env':'PASSWORD=private'})).status_code == 422
    assert upload_import(seller,archive({'../escape.txt':'malicious'})).status_code == 422
    assert post(seller,'/listings',listing_payload()).status_code == 201


def test_public_github_import_uses_pinned_revision(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR', str(tmp_path))
    seller = create(TestClient(app), 'github-import@example.com')
    from app import project_imports
    calls=[]
    def mock_api(path, token=None, params=None):
        calls.append((path,token))
        if path=='/repos/demo/booking':
            return {'full_name':'demo/booking','private':False,'default_branch':'main','size':400}
        if path=='/repos/demo/booking/commits/main':return {'sha':'a'*40}
        raise AssertionError(path)
    monkeypatch.setattr(project_imports, 'get_api', mock_api)
    def mock_download(full_name,sha,token):
        assert full_name=='demo/booking' and sha=='a'*40 and token is None
        return archive()
    monkeypatch.setattr(project_imports,'download_archive',mock_download)
    response = post(seller,'/listing-imports/github',{'repository':'https://github.com/demo/booking'})
    assert response.status_code==201,response.text
    assert response.json()['revision']=='a'*12
    assert response.json()['source_type']=='GITHUB'
    assert calls==[('/repos/demo/booking',None),('/repos/demo/booking/commits/main',None)]


def test_github_validation_and_agent_separation():
    seller=create(TestClient(app),'auth-import@example.com')
    assert post(seller,'/listing-imports/github',{'repository':'http://localhost/internal'}).status_code==422
    assert post(seller,'/listing-imports/github',{'repository':'https://github.com/user/repo?branch=main'}).status_code==422
    assert post(seller,'/listing-imports/github',{'repository':'https://evil.example/repo'}).status_code==422
    assert post(seller,'/listing-imports/github',{'repository':'org/repo','installation_id':123}).status_code==409
    assert parse_repo('https://github.com/org/repo.git')=='org/repo'
    assert seller['client'].get('/api/v1/github/status').json()['public_url_import']


def test_encrypted_tokens_and_oauth_state(monkeypatch):
    from app.github_source import oauth_url, encrypt, decrypt
    monkeypatch.setenv('GITHUB_CLIENT_ID','github_app_client')
    monkeypatch.setenv('GITHUB_CLIENT_SECRET','github_app_secret')
    monkeypatch.setenv('GITHUB_CALLBACK_URL','https://project.example/api/v1/github/callback')
    link = oauth_url('seller-id')
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(link).query)['state'][0]
    verify_oauth_state(state,'seller-id')
    from fastapi import HTTPException
    try: verify_oauth_state(state,'different-user')
    except HTTPException as err: assert err.status_code==403
    else: assert False
    secret='very private token'
    cipher=encrypt(secret)
    assert secret not in cipher and decrypt(cipher)==secret


def test_github_app_private_flow_keeps_token_and_repo_out_of_public(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    monkeypatch.setenv('GITHUB_CLIENT_ID','client-id')
    monkeypatch.setenv('GITHUB_CLIENT_SECRET','client-secret')
    monkeypatch.setenv('GITHUB_CALLBACK_URL','https://project.example/api/v1/github/callback')
    seller=create(TestClient(app),'private-github@example.com')
    start=post(seller,'/github/connect',{})
    assert start.status_code==200,start.text
    from urllib.parse import urlparse,parse_qs
    state=parse_qs(urlparse(start.json()['authorize_url']).query)['state'][0]
    from app import project_imports
    monkeypatch.setattr(project_imports,'exchange_code',lambda code:{'access_token':'example-secret-access-token','expires_in':3600})
    actual={'full_name':'company/confidential-app','private':True,'default_branch':'main','size':20}
    def fake_api(path, token=None, params=None):
        if path=='/user': return {'id':333,'login':'demo-account'}
        if path=='/repos/company/confidential-app': return actual
        if path=='/repos/company/confidential-app/commits/main':return {'sha':'f'*40}
        raise AssertionError(path)
    monkeypatch.setattr(project_imports,'get_api',fake_api)
    callback=seller['client'].get('/api/v1/github/callback',params={'code':'single-use-code','state':state},follow_redirects=False)
    assert callback.status_code==303 and callback.headers['location']=='/sell/new?github=connected'
    from app.models import GithubConnection
    with SessionLocal() as db:
        conn=db.get(GithubConnection,seller['id'])
        assert 'example-secret-access-token' not in conn.access_token_ciphertext
    monkeypatch.setattr(project_imports,'user_token',lambda db,id:'example-secret-access-token')
    monkeypatch.setattr(project_imports,'authorized_repo',lambda token,installation_id,name:actual)
    monkeypatch.setattr(project_imports,'download_archive',lambda name,sha,token:archive())
    response=post(seller,'/listing-imports/github',{'repository':'company/confidential-app','installation_id':444})
    assert response.status_code==201,response.text
    source=response.json()
    assert source['source_private'] and source['source_label']=='company/confidential-app'
    payload=listing_payload();payload['import_id']=source['id']
    listing=post(seller,'/listings',payload).json()
    report=seller['client'].get('/api/v1/listings/'+listing['id']+'/source-summary').json()
    assert 'company/confidential-app' not in str(report)
    assert 'example-secret-access-token' not in str(report)
    assert 'source_label' not in report
    assert seller['client'].delete('/api/v1/github/connection',headers={'X-CSRF-Token':seller['csrf']}).status_code==200


def test_staged_import_cleanup_never_deletes_attached_archive(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller=create(TestClient(app),'cleanup-seller@example.com')
    first=upload_import(seller).json()
    second=upload_import(seller).json()
    payload=listing_payload();payload['import_id']=first['id']
    assert post(seller,'/listings',payload).status_code==201
    from app.models import ProjectImport
    from app.import_cleanup import cleanup
    from app.private_storage import download
    from app.models import now
    from datetime import timedelta
    with SessionLocal() as db:
        staged=db.get(ProjectImport,second['id']);staged.expires_at=now()-timedelta(seconds=2);db.commit()
        attached=db.get(ProjectImport,first['id']);attached_object_key=attached.object_key
        expired_object_key=staged.object_key
    result=cleanup()
    assert result['expired_cleaned']==1
    assert download(attached_object_key)==archive()
    from pathlib import Path
    assert not (tmp_path / expired_object_key).exists()
