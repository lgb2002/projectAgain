"""Buyer-only, versioned development plans; public previews never disclose private source."""
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Listing, ListingSourceSummary
from app.roadmap_engine import create_template
from app.roadmap_models import DevelopmentRoadmapTask
from test_workflows import people, setup_market, offer_payload, confirm_deal, post
from sqlalchemy import select


def deal():
    seller,buyer,stranger,admin=people()
    listing=setup_market(seller,buyer,admin)
    proposed=post(buyer,'/offers',offer_payload(listing['id'])).json()
    tx=post(seller,f'/offers/{proposed["id"]}/accept',{'expected_version':proposed['version']}).json()
    return seller,buyer,stranger,admin,listing,tx


def complete(seller,buyer,tx):
    txid=tx['id']
    confirm_deal(seller,buyer,txid)
    assert post(seller,f'/transactions/{txid}/transition',{'status':'HANDOVER_IN_PROGRESS','expected_version':1}).status_code==200
    checks=seller['client'].get(f'/api/v1/transactions/{txid}/handover-checks').json()['items']
    for check in checks:
        a=post(seller,f'/transactions/{txid}/handover-checks/{check["id"]}',{'result':'SELLER_SUBMITTED','expected_version':check['version']},'patch')
        assert a.status_code==200,a.text
        b=post(buyer,f'/transactions/{txid}/handover-checks/{check["id"]}',{'result':'BUYER_CONFIRMED','expected_version':a.json()['version']},'patch')
        assert b.status_code==200,b.text
    assert post(seller,f'/transactions/{txid}/transition',{'status':'HANDOVER_REVIEW','expected_version':2}).status_code==200
    finished=post(buyer,f'/transactions/{txid}/transition',{'status':'DEMO_COMPLETED','expected_version':3})
    assert finished.status_code==200,finished.text


def test_public_preview_visibility_and_not_real_verification():
    seller,buyer,stranger,admin,listing,tx=deal()
    path=f'/api/v1/listings/{listing["id"]}/development-roadmap-preview'
    # DEMO accept keeps the listing ACTIVE; public preview remains visible.
    assert stranger['client'].get(path+'?include_demo=true').status_code==200
    visible=seller['client'].get(path+'?include_demo=true')
    assert visible.status_code==200,visible.text
    data=visible.json()
    assert data['is_preview'] and data['simulation_only']
    assert data['analysis_basis']=='SELLER_DECLARATION_ONLY'
    assert len(data['tasks'])>=10 and not any('object_key' in str(x) for x in data['tasks'])
    assert any(t['assistance']=='EXPERT' for t in data['tasks'])
    assert not any('api_key' in str(x).lower() for x in data['tasks'])
    # Hide non-public listing details from unrelated actors even when ID is known.
    assert TestClient(app).get(path).status_code==404


def test_roadmap_requires_completed_handover_and_buyer_only():
    seller,buyer,stranger,admin,listing,tx=deal(); path=f'/transactions/{tx["id"]}/development-roadmap'
    assert post(buyer,path).status_code==409
    assert buyer['client'].get('/api/v1'+path).status_code==409
    assert post(seller,path).status_code==404
    assert post(stranger,path).status_code==404
    complete(seller,buyer,tx)
    assert post(seller,path).status_code==404
    assert post(stranger,path).status_code==404
    assert buyer['client'].get('/api/v1'+path).json()['created'] is False
    done=post(buyer,path)
    assert done.status_code==201,done.text
    data=done.json()
    assert data['created'] and data['progress_percent']==0
    assert data['total_tasks']>10 and data['simulation_only']
    assert post(buyer,path).json()['id']==data['id']
    assert seller['client'].get('/api/v1'+path).status_code==404
    assert stranger['client'].get('/api/v1'+path+'/export').status_code==404
    assert buyer['client'].get('/api/v1'+path+'/export').status_code==200


def test_task_dependencies_and_progress_versioning():
    seller,buyer,_,_,_,tx=deal();complete(seller,buyer,tx)
    base=f'/transactions/{tx["id"]}/development-roadmap';plan=post(buyer,base).json()
    tasks={t['key']:t for t in plan['tasks']}
    ready=tasks['ASSET_INVENTORY']; later=tasks['LOCAL_RUN']
    wrong=post(buyer,base+'/tasks/'+later['id'],{'status':'COMPLETED','buyer_note':'넘어가기','expected_version':later['version']},'patch')
    assert wrong.status_code==409
    start=post(buyer,base+'/tasks/'+ready['id'],{'status':'COMPLETED','buyer_note':'자료 검토 완료','expected_version':ready['version']},'patch')
    assert start.status_code==200,start.text
    changed={t['key']:t for t in start.json()['tasks']}
    assert changed['ASSET_INVENTORY']['buyer_note']=='자료 검토 완료'
    assert start.json()['completed_tasks']==1
    assert changed['ACCESS_SECURITY']['waiting_on']==[]
    assert post(buyer,base+'/tasks/'+ready['id'],{'status':'IN_PROGRESS','expected_version':ready['version']},'patch').status_code==409
    now_ready=changed['ASSET_INVENTORY']
    assert post(buyer,base+'/tasks/'+ready['id'],{'status':'INVALID','expected_version':now_ready['version']},'patch').status_code==422
    assert post(buyer,base+'/tasks/'+ready['id'],{'status':'BLOCKED','expected_version':now_ready['version'],'buyer_note':'보류 중','blocked_reason':'ENV_SETUP'},'patch').status_code==200


def test_cannot_undo_prerequisite_with_active_dependent():
    seller,buyer,_,_,_,tx=deal();complete(seller,buyer,tx)
    base=f'/transactions/{tx["id"]}/development-roadmap'
    initial=post(buyer,base).json()
    first={t['key']:t for t in initial['tasks']}['ASSET_INVENTORY']
    completed=post(buyer,base+'/tasks/'+first['id'],
                   {'status':'COMPLETED','buyer_note':'인수 확인','expected_version':first['version']},'patch').json()
    next_task={t['key']:t for t in completed['tasks']}['ACCESS_SECURITY']
    active=post(buyer,base+'/tasks/'+next_task['id'],
                {'status':'IN_PROGRESS','buyer_note':'키 교체 중','expected_version':next_task['version']},'patch')
    assert active.status_code==200,active.text
    new_first={t['key']:t for t in active.json()['tasks']}['ASSET_INVENTORY']
    denied=post(buyer,base+'/tasks/'+new_first['id'],
                {'status':'NOT_STARTED','expected_version':new_first['version']},'patch')
    assert denied.status_code==409
    # Reset dependent first, then prerequisite may be reopened.
    dependent={t['key']:t for t in active.json()['tasks']}['ACCESS_SECURITY']
    changed=post(buyer,base+'/tasks/'+dependent['id'],
                 {'status':'NOT_STARTED','expected_version':dependent['version']},'patch')
    assert changed.status_code==200
    new_first={t['key']:t for t in changed.json()['tasks']}['ASSET_INVENTORY']
    assert post(buyer,base+'/tasks/'+new_first['id'],
                {'status':'NOT_STARTED','expected_version':new_first['version']},'patch').status_code==200


def test_custom_tasks_validation_and_audit():
    seller,buyer,stranger,_,_,tx=deal();complete(seller,buyer,tx)
    base=f'/transactions/{tx["id"]}/development-roadmap'
    plan=post(buyer,base).json(); key=plan['tasks'][0]['key']
    payload={'title':'특정 서비스 점검 추가','detail':'데이터 이전 후 로그와 알림 경로를 확인합니다.',
             'phase':'VERIFY','difficulty':'MEDIUM','assistance':'GUIDED','priority':'MEDIUM','prerequisites':[key]}
    assert post(stranger,base+'/tasks',payload).status_code==404
    assert post(buyer,base+'/tasks',{**payload,'prerequisites':['DOES_NOT_EXIST']}).status_code==422
    assert post(buyer,base+'/tasks',{**payload,'difficulty':'SUPER_HARD'}).status_code==422
    added=post(buyer,base+'/tasks',payload)
    assert added.status_code==201,added.text
    task=added.json()['tasks'][-1]
    assert task['source_kind']=='BUYER' and task['waiting_on']==[key]
    assert post(buyer,base+'/tasks/'+task['id'],{'status':'IN_PROGRESS','expected_version':1},'patch').status_code==409
    with SessionLocal() as db:
        row=db.scalar(select(DevelopmentRoadmapTask).where(DevelopmentRoadmapTask.id==task['id']))
        assert row is not None and row.source_kind=='BUYER'


def test_source_metadata_changes_roadmap_and_snapshot_does_not_overwrite():
    seller,buyer,_,_,listing,tx=deal()
    complete(seller,buyer,tx)
    base=f'/transactions/{tx["id"]}/development-roadmap'
    original=post(buyer,base).json();old_id=original['id']
    with SessionLocal() as db:
        row=db.get(Listing,listing['id']);row.known_defects=['등록된 문제'];row.version+=1;db.commit()
    current=buyer['client'].get('/api/v1'+base).json()
    assert current['source_changed_since_creation'] is True
    assert current['id']==old_id and current['total_tasks']==original['total_tasks']


def test_engine_seller_context_and_prerequisite_topology():
    seller,buyer,_,_,listing,_=deal()
    with SessionLocal() as db:
        row=db.get(Listing,listing['id'])
        candidates=create_template(row, {'takeover_checks':[{'key':'DATA','status':'FOUND'},
                    {'key':'TESTS','status':'REVIEW'},{'key':'ENVIRONMENT','status':'FOUND'}],
                    'possible_services':['PostgreSQL'],'warnings':['ARCHIVE_WARNING']})
    tasks=candidates['tasks'];keys=[t['key'] for t in tasks]
    assert len(keys)==len(set(keys))
    assert all(keys.index(dep)<i for i,t in enumerate(tasks) for dep in t['prerequisites'])
    assert 'DATABASE_SETUP' in keys and 'ARCHIVE_INTEGRITY' in keys and 'TEST_REGRESSION' in keys
    assert candidates['analysis_basis']=='PUBLIC_STATIC_SUMMARY'
    assert all(len(t['steps'])>=2 and len(t['success_criteria'])>=1 for t in tasks)


def test_content_asset_roadmap_does_not_require_running_server():
    seller,buyer,_,_,listing,tx=deal()
    with SessionLocal() as db:
        row=db.get(Listing,listing['id'])
        row.category='content_asset'
        db.commit()
        candidate=create_template(row)
    keys=[t['key'] for t in candidate['tasks']]
    assert 'EDITABLE_FILES' in keys and 'CONTENT_PACKAGE' in keys
    assert 'LOCAL_RUN' not in keys and 'DEPENDENCY_SETUP' not in keys
    assert all(keys.index(dep)<i for i,t in enumerate(candidate['tasks']) for dep in t['prerequisites'])


def test_category_specific_ai_agent_and_game_support():
    seller,buyer,_,_,listing,tx=deal()
    with SessionLocal() as db:
        row=db.get(Listing,listing['id'])
        row.category='ai_agent'
        assert 'AGENT_EVALUATION' in [x['key'] for x in create_template(row)['tasks']]
        row.category='game'
        assert 'GAME_PLAYTEST' in [x['key'] for x in create_template(row)['tasks']]
