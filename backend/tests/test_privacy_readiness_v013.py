"""v0.13 erasure (identity and source) and unconditional takeover evidence."""
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import SessionLocal
from app.main import app
from app.models import (User, Listing, ProjectImport, ServiceGrant, GithubConnection,
                        ListingAsset, Offer, Transaction)
from app.privacy import PrivacyErasure, PrivacyErasureObject, cleanup_objects
from app.readiness_report import ListingReadinessReport
from app.github_ci import observe_ci
from test_workflows import create, post, listing_payload, people, setup_market, offer_payload
from test_project_imports import upload_import


def test_manual_project_always_gets_report_and_persists():
    seller=create(TestClient(app),'readiness-seller@example.com')
    row=post(seller,'/listings',listing_payload()).json()
    report=seller['client'].get('/api/v1/listings/'+row['id']+'/takeover-report')
    assert report.status_code==200,report.text
    a=report.json()['analysis']
    assert a['source_analyzed'] is False
    assert a['readiness_status']=='INDEPENDENT_REVIEW_REQUIRED'
    assert a['rights_verified'] is False
    assert any(x['key']=='SOURCE_NOT_PROVIDED' for x in a['checks'])
    with SessionLocal() as db:
        assert db.get(ListingReadinessReport,row['id']) is not None


def test_uploaded_source_takes_priority_without_exposing_private_repo(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller=create(TestClient(app),'readiness-source@example.com')
    res=upload_import(seller)
    assert res.status_code==201,res.text
    payload=listing_payload();payload['import_id']=res.json()['id']
    row=post(seller,'/listings',payload).json()
    report=seller['client'].get('/api/v1/listings/'+row['id']+'/takeover-report').json()['analysis']
    assert report['source_analyzed'] is True and report['file_count']>=3
    assert any(x['key'].startswith('SOURCE_') for x in report['checks'])
    assert 'source_label' not in report and 'sample.zip' not in str(report)


def test_observed_ci_is_commit_matched_and_does_not_execute(monkeypatch):
    monkeypatch.delenv('GITHUB_CI_LOOKUP_DISABLED',raising=False)
    from app import github_ci
    sha='a'*40
    monkeypatch.setattr(github_ci,'get_api',lambda path,token,params:{'workflow_runs':[
        {'head_sha':sha,'status':'completed','conclusion':'success'},
        {'head_sha':'b'*40,'status':'completed','conclusion':'success'}]})
    status=observe_ci('sample/project',sha)
    assert status['status']=='OBSERVED_SUCCESS' and status['runs_checked']==1 and status['observed_sha_match']


def test_deletion_requires_password_confirmation_and_revokes_tokens(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller=create(TestClient(app),'privacy-owner@example.com')
    buyer=create(TestClient(app),'privacy-buyer@example.com')
    upload=upload_import(seller)
    assert upload.status_code==201,upload.text
    payload=listing_payload();payload['import_id']=upload.json()['id']
    listing=post(seller,'/listings',payload).json()
    source_id=upload.json()['id']
    private_path=None
    with SessionLocal() as db:
        imp=db.get(ProjectImport,source_id)
        private_path=tmp_path/imp.object_key
        assert private_path.exists()
    overview=seller['client'].get('/api/v1/auth/privacy/summary')
    assert overview.status_code==200
    assert overview.json()['impact']['source_archives']==1
    assert seller['client'].post('/api/v1/auth/privacy/delete',json={
        'password':'Long-Unique-Test-Password-2026!','confirmation':'계정 탈퇴'}).status_code==403
    assert post(seller,'/auth/privacy/delete',{'password':'wrong','confirmation':'계정 탈퇴'}).status_code==403
    assert post(seller,'/auth/privacy/delete',{'password':'Long-Unique-Test-Password-2026!','confirmation':'delete'}).status_code==422
    # Verify another account can still sign in after tombstone.
    result=post(seller,'/auth/privacy/delete',{
        'password':'Long-Unique-Test-Password-2026!','confirmation':'계정 탈퇴'})
    assert result.status_code==202,result.text
    assert result.json()['private_objects_queued']>=1
    assert seller['client'].get('/api/v1/auth/me').status_code==401
    assert seller['client'].post('/api/v1/auth/login',json={
        'email':'privacy-owner@example.com','password':'Long-Unique-Test-Password-2026!'}).status_code==401
    assert buyer['client'].get('/api/v1/auth/me').status_code==200
    with SessionLocal() as db:
        user=db.get(User,seller['id'])
        assert user.deleted_at is not None and user.email.endswith('@invalid.local')
        assert not user.is_active
        item=db.get(Listing,listing['id'])
        assert item.status=='REMOVED' and item.title=='삭제된 프로젝트'
        asset=db.scalar(select(ListingAsset).where(ListingAsset.listing_id==listing['id']))
        assert asset.upload_status=='DELETED'
        erasure=db.get(PrivacyErasure,user.id)
        assert erasure.status=='OBJECTS_PENDING'
        assert private_path.exists()  # DB commit before deletion; durable queue.
        cleanup=cleanup_objects(db)
        assert cleanup['processed']>=1 and cleanup['failed']==0
        assert db.get(PrivacyErasure,user.id).status=='COMPLETED'
    assert not private_path.exists()


def test_seller_deletion_cancel_unfinished_demo_and_anonymize_terms():
    seller,buyer,_,admin=people()
    listing=setup_market(seller,buyer,admin)
    offer=post(buyer,'/offers',offer_payload(listing['id']))
    assert offer.status_code==201,offer.text
    accepted=post(seller,f'/offers/{offer.json()["id"]}/accept',{'expected_version':offer.json()['version']})
    assert accepted.status_code==201,accepted.text
    deleted=post(seller,'/auth/privacy/delete',{'password':'Long-Unique-Test-Password-2026!','confirmation':'계정 탈퇴'})
    assert deleted.status_code==202,deleted.text
    with SessionLocal() as db:
        tx=db.get(Transaction,accepted.json()['id']);row=db.get(Offer,offer.json()['id'])
        assert tx.status=='CANCELLED' and row.terms=={}
        assert db.get(Listing,listing['id']).status=='REMOVED'


def test_admin_account_cannot_self_delete():
    seller,buyer,stranger,admin=people()
    response=post(admin,'/auth/privacy/delete',{'password':'Long-Unique-Test-Password-2026!','confirmation':'계정 탈퇴'})
    assert response.status_code==403


def test_completed_demo_retained_but_support_disabled_after_seller_deletion():
    from test_integrated_workspace_v012 import create as make_deal, case_payload
    from test_development_roadmap_v09 import complete
    seller,buyer,_,admin=people()
    listing=setup_market(seller,buyer,admin)
    _,tx=make_deal(seller,buyer,listing)
    complete(seller,buyer,tx)
    assert post(seller,'/auth/privacy/delete',{
        'password':'Long-Unique-Test-Password-2026!','confirmation':'계정 탈퇴'}).status_code==202
    with SessionLocal() as db:
        assert db.get(Transaction,tx['id']).status=='DEMO_COMPLETED'
    denied=post(buyer,f'/transactions/{tx["id"]}/support-cases',case_payload('MISSING_ASSET'))
    assert denied.status_code==409,denied.text


def test_deletion_queue_retries_failed_storage(tmp_path,monkeypatch):
    from app import private_storage
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller=create(TestClient(app),'privacy-retry@example.com')
    assert upload_import(seller).status_code==201
    assert post(seller,'/auth/privacy/delete',{
        'password':'Long-Unique-Test-Password-2026!','confirmation':'계정 탈퇴'}).status_code==202
    saved=private_storage.delete
    monkeypatch.setattr(private_storage,'delete',lambda key: (_ for _ in ()).throw(OSError('offline')))
    with SessionLocal() as db:
        failed=cleanup_objects(db)
        assert failed['failed']==1
        assert db.get(PrivacyErasure,seller['id']).status=='OBJECTS_PENDING'
    monkeypatch.setattr(private_storage,'delete',saved)
    with SessionLocal() as db:
        passed=cleanup_objects(db)
        assert passed['processed']==1
        assert db.get(PrivacyErasure,seller['id']).status=='COMPLETED'
