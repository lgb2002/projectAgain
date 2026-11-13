"""v0.7 end-to-end permissions, safe media, questions and transactional alerts."""
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import SessionLocal
from app.main import app
from app.models import Notification
from app.marketplace_models import NotificationEmail, NotificationPreference, ListingMedia
from app.project_analyzer import analyze_archive, public_analysis
from test_workflows import people, setup_market, post, listing_payload
from test_project_imports import archive


def photo():
    f=BytesIO()
    im=Image.new('RGB',(120,90),(70,120,110))
    im.save(f,format='PNG')
    return f.getvalue()


def upload(user, listing_id, data=None):
    return user['client'].post('/api/v1/listings/'+listing_id+'/media',
        headers={'X-CSRF-Token':user['csrf']}, files={'file':('screen.png',data or photo(),'image/png')})


def test_gallery_private_public_and_re_review(tmp_path, monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people()
    created=post(seller,'/listings',listing_payload()).json()
    lid=created['id']
    assert upload(buyer,lid).status_code==404
    result=upload(seller,lid)
    assert result.status_code==201,result.text
    photo_id=result.json()['item']['id']
    assert buyer['client'].get(f'/api/v1/listings/{lid}/media/{photo_id}/image').status_code==404
    res=seller['client'].get(f'/api/v1/listings/{lid}/media/{photo_id}/image')
    assert res.status_code==200 and res.headers['content-type'].startswith('image/webp')
    assert res.headers['cache-control']=='private, no-store'
    assert not res.content.startswith(b'\x89PNG')
    info=post(seller,f'/listings/{lid}',{'expected_version':2,'status':'PENDING_REVIEW'},'patch')
    assert info.status_code==200,info.text
    assert post(admin,f'/admin/listings/{lid}/moderate',{'status':'ACTIVE'}).status_code==200
    assert buyer['client'].get(f'/api/v1/listings/{lid}/showcase?include_demo=true').json()['media'][0]['id']==photo_id
    assert buyer['client'].get(f'/api/v1/listings/{lid}/media/{photo_id}/image?demo=true').status_code==200
    assert buyer['client'].get(f'/api/v1/listings/{lid}/media/{photo_id}/image').status_code==404
    assert upload(seller,lid).json()['listing_status']=='PENDING_REVIEW'
    assert buyer['client'].get(f'/api/v1/listings/{lid}/showcase?include_demo=true').status_code==404
    assert post(buyer,f'/listings/{lid}/showcase',{} ,method='put').status_code==404


def test_showcase_url_validate_and_update_requires_review(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people()
    row=setup_market(seller,buyer,admin)
    lid=row['id']
    for demo in ['http://public.example','https://127.0.0.1/admin','https://user:pw@example.com','https://localhost:5000']:
        assert post(seller,f'/listings/{lid}/showcase',{'demo_url':demo,'video_url':None,'highlights':[]},method='put').status_code==422
    data={'demo_url':'https://demo.example.com','video_url':'https://youtu.be/example','highlights':['로그인 및 데이터 검색']}
    result=post(seller,f'/listings/{lid}/showcase',data,method='put')
    assert result.status_code==200,result.text
    assert result.json()['listing_status']=='PENDING_REVIEW'
    assert buyer['client'].get(f'/api/v1/listings/{lid}/showcase?include_demo=true').status_code==404
    assert post(admin,f'/admin/listings/{lid}/moderate',{'status':'ACTIVE'}).status_code==200
    saved=buyer['client'].get(f'/api/v1/listings/{lid}/showcase?include_demo=true').json()
    assert saved['demo_url']=='https://demo.example.com'
    assert saved['seller_provided'] and saved['demo_not_verified']
    assert post(seller,f'/listings/{lid}/showcase',{'demo_url':None,'video_url':None,'highlights':['변경']},method='put').status_code==200
    assert post(seller,f'/listings/{lid}/showcase',{'demo_url':None,'video_url':None,'highlights':['재수정']},method='put').json()['listing_status']=='DRAFT'


def test_inquiry_visibility_seller_reply_notification_and_read(monkeypatch):
    seller,buyer,stranger,admin=people()
    row=setup_market(seller,buyer,admin)
    lid=row['id']
    pub=post(buyer,f'/listings/{lid}/inquiries',{'question':'서버 실행 절차를 확인할 수 있을까요?','visibility':'PUBLIC'})
    assert pub.status_code==201,pub.text
    qid=pub.json()['id']
    assert len(stranger['client'].get(f'/api/v1/listings/{lid}/inquiries?include_demo=true').json()['items'])==1
    assert post(stranger,f'/inquiries/{qid}/answer',{'answer':'침해 답변'}).status_code==404
    ok=post(seller,f'/inquiries/{qid}/answer',{'answer':'README에 설치 절차가 정리되어 있습니다.'})
    assert ok.status_code==200,ok.text
    assert ok.json()['answer'].startswith('README')
    assert seller['client'].get('/api/v1/inquiries/inbox').json()['items'][0]['role']=='SELLER'
    assert buyer['client'].get('/api/v1/inquiries/inbox').json()['items'][0]['role']=='BUYER'
    alerts=seller['client'].get('/api/v1/notifications').json()
    assert any(n['kind']=='INQUIRY_RECEIVED' for n in alerts['items'])
    buyer_alerts=buyer['client'].get('/api/v1/notifications').json()
    assert any(n['kind']=='INQUIRY_ANSWERED' for n in buyer_alerts['items'])
    read=post(buyer,'/notifications/read-all',{})
    assert read.status_code==200
    assert buyer['client'].get('/api/v1/notifications').json()['unread']==0
    # Day quota is independent of email configuration.
    assert post(buyer,f'/listings/{lid}/inquiries',{'question':'이메일 test@example.com으로 연락해 주세요!','visibility':'PRIVATE'}).status_code==422


def test_inquiry_private_only_parties_and_moderation(monkeypatch):
    seller,buyer,stranger,admin=people()
    row=setup_market(seller,buyer,admin)
    lid=row['id']
    pr=post(buyer,f'/listings/{lid}/inquiries',{'question':'외부 서비스 계정은 인수 범위인가요?','visibility':'PRIVATE'})
    assert pr.status_code==201,pr.text
    qid=pr.json()['id']
    assert stranger['client'].get(f'/api/v1/listings/{lid}/inquiries?include_demo=true').json()['items']==[]
    assert len(buyer['client'].get(f'/api/v1/listings/{lid}/inquiries?include_demo=true').json()['items'])==1
    assert len(seller['client'].get(f'/api/v1/listings/{lid}/inquiries?include_demo=true').json()['items'])==1
    assert post(stranger,f'/admin/inquiries/{qid}/hide').status_code==403
    assert post(admin,f'/admin/inquiries/{qid}/hide').status_code==200
    assert buyer['client'].get(f'/api/v1/listings/{lid}/inquiries?include_demo=true').json()['items']==[]


def test_alert_preference_persists_and_email_outbox(monkeypatch):
    seller,buyer,stranger,admin=people()
    row=setup_market(seller,buyer,admin)
    lid=row['id']
    result=post(seller,'/notifications/preferences',{'email_enabled':False},method='put')
    assert result.status_code==200
    assert seller['client'].get('/api/v1/notifications/preferences').json()['email_enabled'] is False
    prior_count=None
    with SessionLocal() as db:
        prior_count=db.query(NotificationEmail).filter(NotificationEmail.user_id==seller['id']).count()
    assert post(buyer,f'/listings/{lid}/inquiries',{'question':'파일 구성 정보가 최신 버전인가요?','visibility':'PUBLIC'}).status_code==201
    with SessionLocal() as db:
        assert db.query(NotificationEmail).filter(NotificationEmail.user_id==seller['id']).count()==prior_count
    assert post(seller,'/notifications/preferences',{'email_enabled':True},method='put').status_code==200
    # independent buyer signal, delivered through same outbox.
    assert post(seller,f'/listings/{lid}/showcase',{'demo_url':None,'video_url':None,'highlights':['목록']},method='put').status_code==200
    assert not seller['client'].get('/api/v1/notifications/preferences').json()['email_delivery_configured']


def test_static_takeover_checklist_is_evidence_only():
    blob=archive({'sample/README.md':'# Nice project\nTest app',
                  'sample/package.json':'{"dependencies":{"react":"1.0"}}',
                  'sample/package-lock.json':'{}',
                  'sample/.env.example':'EXAMPLE=placeholder',
                  'sample/src/main.tsx':'export const demo = 1;',
                  'sample/tests/test_main.py':'def test_valid(): pass'})
    report=analyze_archive(blob)
    assert report['analysis_version']=='static-v2'
    assert report['code_executed'] is False and report['llm_used'] is False
    checks={x['key']:x for x in report['takeover_checks']}
    assert checks['PROJECT_GUIDE']['status']=='FOUND'
    assert checks['DEPENDENCY_LOCK']['status']=='FOUND'
    assert checks['ENVIRONMENT']['status']=='FOUND'
    assert checks['DEPLOY']['status']=='REVIEW'
    public=public_analysis(report)
    assert 'takeover_checks' in public and 'description_suggestion' not in public
    assert len(public['takeover_next_steps'])>0


def test_email_outbox_worker_success_retry_and_opt_out(monkeypatch):
    from app.notifications_v07 import notify, send_due
    from app.models import User, now
    buyer=create_test_user_for_worker()
    emails=[]
    monkeypatch.setenv('SMTP_HOST','smtp.test.invalid')
    monkeypatch.setenv('SMTP_FROM','noreply@test.invalid')
    monkeypatch.setattr('app.notifications_v07._deliver',lambda recipient,note: emails.append((recipient,note.title)))
    with SessionLocal() as db:
        notify(db,buyer['id'],'INQUIRY_ANSWERED','판매자 답변이 등록됐습니다.','inquiry','test-000')
        db.commit()
        result=send_due(db)
        assert result['sent']==1
        assert len(emails)==1
        assert send_due(db)['sent']==0
        out=db.query(NotificationEmail).filter(NotificationEmail.user_id==buyer['id']).one()
        assert out.status=='SENT' and out.sent_at is not None
        db.add(NotificationPreference(user_id=buyer['id'],email_enabled=False))
        notify(db,buyer['id'],'INQUIRY_ANSWERED','새 답변입니다.','inquiry','test-001')
        db.commit()
        assert db.query(NotificationEmail).filter(NotificationEmail.user_id==buyer['id']).count()==1


def create_test_user_for_worker():
    from test_workflows import create
    return create(TestClient(app),'worker-buyer@example.com')


def test_media_representative_change_and_invalid_image(tmp_path,monkeypatch):
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people()
    listing=post(seller,'/listings',listing_payload()).json()
    lid=listing['id']
    assert upload(seller,lid,b'this is not a PNG').status_code==422
    first=upload(seller,lid).json()['item']['id']
    second=upload(seller,lid).json()['item']['id']
    changed=post(seller,f'/listings/{lid}/media/{second}',{'caption':'대시보드 화면','set_cover':True},method='patch')
    assert changed.status_code==200,changed.text
    view=seller['client'].get(f'/api/v1/listings/{lid}/showcase?include_demo=true').json()
    assert view['media'][0]['id']==second
    assert view['media'][0]['caption']=='대시보드 화면'
    assert post(buyer,f'/listings/{lid}/media/{second}',{'caption':'변조'},method='patch').status_code==404
    assert seller['client'].get(f'/api/v1/listings/{lid}').json()['cover_image_url'].endswith(second+'/image?demo=1')
    assert seller['client'].delete(f'/api/v1/listings/{lid}/media/{first}',headers={'X-CSRF-Token':seller['csrf']}).status_code==200


def test_upgrade_old_source_analysis_without_leaking_or_running_source(tmp_path,monkeypatch):
    from app.models import ListingSourceSummary
    from test_project_imports import upload_import
    monkeypatch.setenv('PRIVATE_STORAGE_DIR',str(tmp_path))
    seller,buyer,stranger,admin=people()
    imported=upload_import(seller)
    assert imported.status_code==201,imported.text
    payload=listing_payload();payload['import_id']=imported.json()['id']
    listing=post(seller,'/listings',payload).json()
    lid=listing['id']
    with SessionLocal() as db:
        summary=db.get(ListingSourceSummary,lid)
        summary.analysis={'analysis_version':'static-v1','tech_stack':['React']}
        db.commit()
    assert post(buyer,f'/listings/{lid}/source-summary/reanalyze',{}).status_code==404
    result=post(seller,f'/listings/{lid}/source-summary/reanalyze',{})
    assert result.status_code==200,result.text
    assert result.json()['analysis']['analysis_version']=='static-v2'
    assert result.json()['analysis']['takeover_checks']
    assert 'description_suggestion' not in result.json()['analysis']
