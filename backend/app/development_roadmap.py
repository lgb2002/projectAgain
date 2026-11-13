"""Public roadmap preview, private buyer progress and deterministic creation.

Public previews reveal no code, paths, repository identity, credentials or private
transaction information. Persisted plans can only be created after DEMO handover.
"""
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_db
from .models import (AuditEvent, BuyerPreferences, Listing, ListingSourceSummary,
                     Transaction, now)
from .roadmap_models import DevelopmentRoadmap, DevelopmentRoadmapTask
from .roadmap_engine import create_template, PHASES, DISCLAIMER
from .security import human

router = APIRouter(prefix='/api/v1', tags=['Development roadmap'])
CLOSED = {'CANCELLED', 'DISPUTED'}
VALID_STATUSES = {'NOT_STARTED', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED'}


def reject(status, msg):
    raise HTTPException(status, msg)


def source_analysis(db, listing_id):
    row = db.get(ListingSourceSummary, listing_id)
    return row.analysis if row else None


def preview_data(db, listing):
    return create_template(listing, source_analysis(db, listing.id))


def buyer_transaction(db, transaction_id, ctx, *, lock=False):
    q = select(Transaction).where(Transaction.id == transaction_id)
    if lock: q = q.with_for_update()
    tx = db.scalar(q)
    if not tx or tx.buyer_id != ctx['user'].id:
        reject(404, '해당 로드맵에 접근할 수 없습니다.')
    if not tx.is_demo:
        reject(409, '현재 실제 결제·인수는 지원하지 않습니다. 시연 거래만 사용할 수 있습니다.')
    if tx.status != 'DEMO_COMPLETED':
        reject(409, '모의 인수인계가 완료된 후 구매자 로드맵을 생성할 수 있습니다.')
    return tx


def tasks_for(db, plan):
    return db.scalars(select(DevelopmentRoadmapTask)
                      .where(DevelopmentRoadmapTask.roadmap_id == plan.id)
                      .order_by(DevelopmentRoadmapTask.position, DevelopmentRoadmapTask.id)).all()


def task_data(row, by_key):
    waiting = [x for x in row.prerequisites if x not in by_key or by_key[x].status != 'COMPLETED']
    return {
        'id': row.id, 'key': row.task_key, 'phase': row.phase, 'title': row.title,
        'detail': row.detail, 'difficulty': row.difficulty, 'assistance': row.assistance,
        'priority': row.priority, 'prerequisites': row.prerequisites, 'waiting_on': waiting,
        'steps': row.steps, 'success_criteria': row.success_criteria, 'evidence': row.evidence,
        'source_kind': row.source_kind, 'status': row.status, 'buyer_note': row.buyer_note,
        'blocked_reason': row.blocked_reason,
        'position': row.position, 'version': row.version, 'updated_at': row.updated_at.isoformat(),
    }


def personalized_task_guidance(row, by_key, context):
    """Deterministic per-buyer explanation. No LLM or executable project code."""
    skill=context['skill_level']
    detail=context['preferred_guidance_level']
    beginners=skill in {'NONE','BASIC'}
    prerequisite_names=[by_key[key].title for key in row.prerequisites if key in by_key]
    waiting=[by_key[key].title for key in row.prerequisites
             if key in by_key and by_key[key].status!='COMPLETED']
    if detail=='BRIEF':
        checklist=list(row.steps or [])[:1]
    elif detail=='STANDARD':
        checklist=list(row.steps or [])[:2]
    else:
        checklist=list(row.steps or [])
    if not checklist:
        checklist=[row.detail]
    if beginners:
        intro=('이 작업은 인수 후 프로젝트를 안전하게 이어가기 위한 단계입니다. '
               '모르는 용어가 있으면 작업 전 판매자나 전문가에게 의미를 확인하세요.')
        before=('먼저 ' + ' → '.join(prerequisite_names) + ' 작업을 확인하세요. '
                if prerequisite_names else '받은 자료와 안내서를 준비하세요. ')
        before+='프로그램 실행과 계정 설정은 이해한 범위 안에서만 시도하세요.'
    else:
        intro='현재 프로젝트의 입력 정보와 정적 분석에 따른 작업 항목입니다. 실제 환경에서 확인이 필요합니다.'
        before=('선행: ' + ', '.join(prerequisite_names) + '. ' if prerequisite_names else '')
        before+='권한, 의존성 및 재현 가능한 증빙부터 확보하세요.'
    if row.assistance=='EXPERT':
        help_note='권리·보안 또는 전문적 기술 판단이 필요할 수 있어 자격을 갖춘 전문가 검토를 권장합니다.'
    elif row.assistance=='GUIDED':
        help_note='설치·설정 또는 테스트가 막히면 재현 방법을 기록하고 판매자에게 약정 범위인지 확인하세요.'
    else:
        help_note='직접 확인이 가능한 단계지만 누락된 인계 자료가 있으면 판매자에게 문의하세요.'
    if row.blocked_reason:
        blocker={'ENV_SETUP':'환경과 버전을 확인하고 오류 메시지에서 비밀값을 지운 뒤 문의하세요.',
                 'MISSING_FILE':'약정된 파일 목록과 실제 전달물을 비교하고 누락 자료로 분류하세요.',
                 'RUNTIME_ERROR':'실행 순서와 로그를 정리해 재현 가능한 문제로 기록하세요.',
                 'UNFAMILIAR_TECH':'필요한 기술·도구 이름을 구체화해 도움을 요청하세요.',
                 'OTHER':'진행을 막은 이유와 시도한 내용을 기록하세요.'}.get(row.blocked_reason)
    else: blocker=None
    return {'skill_level':skill,'guidance_level':detail,'intro':intro,
            'preparation':before,'checklist':checklist,
            'completion_checks':list(row.success_criteria or []),
            'help_guidance':help_note,'waiting_on_titles':waiting,
            'blocked_help':blocker,'objective_note':context['objective'][:500]}


def plan_data(db, tx, plan):
    listing = db.get(Listing, plan.listing_id)
    from .v012_models import RoadmapBuyerContext, RoadmapTaskHelpLink
    context=db.get(RoadmapBuyerContext,plan.id)
    prefs=db.get(BuyerPreferences,tx.buyer_id)
    buyer_context={'skill_level':context.skill_level if context else (prefs.skill_level if prefs else 'BASIC'),
                   'objective':context.objective if context else '',
                   'preferred_guidance_level':context.preferred_guidance_level if context else 'DETAILED',
                   'version':context.version if context else 1}
    rows = tasks_for(db, plan)
    links=db.scalars(select(RoadmapTaskHelpLink).where(RoadmapTaskHelpLink.roadmap_task_id.in_([r.id for r in rows]))).all() if rows else []
    support_links={r.id:[l.support_case_id for l in links if l.roadmap_task_id==r.id] for r in rows}
    by_key = {r.task_key: r for r in rows}
    completed = sum(r.status == 'COMPLETED' for r in rows)
    current_fingerprint = preview_data(db, listing)['source_fingerprint'] if listing else None
    return {
        'created': True, 'id': plan.id, 'transaction_id': tx.id,
        'listing_id': plan.listing_id, 'listing_title': listing.title if listing else '프로젝트',
        'analysis_basis': plan.analysis_basis, 'source_fingerprint': plan.source_fingerprint,
        'source_changed_since_creation': current_fingerprint != plan.source_fingerprint,
        'created_at': plan.created_at.isoformat(), 'phases': PHASES,
        'total_tasks': len(rows), 'completed_tasks': completed,
        'progress_percent': round(100 * completed / len(rows)) if rows else 0,
        'buyer_context':buyer_context,
        'tasks': [{**task_data(r, by_key), 'support_case_ids':support_links.get(r.id,[]),
                    'why_needed':r.detail,
                    'before_start':'선행 작업과 인수 자료, 필요한 서비스 자격을 확인하세요.',
                    'when_to_get_help':'환경 오류나 권리·보안 문제가 발생하면 기술 전문가와 함께 검토하세요.',
                    'personalized_guidance':personalized_task_guidance(r,by_key,buyer_context)}
                   for r in rows],
        'disclaimer': DISCLAIMER, 'simulation_only': True,
    }


def event(db, ctx, name, resource_id, detail):
    db.add(AuditEvent(actor_user_id=ctx['user'].id, actor_type='USER', action=name,
                      resource_type='development_roadmap', resource_id=resource_id,
                      old_state=None, new_state=detail, is_demo=True))


@router.get('/listings/{listing_id}/development-roadmap-preview')
def public_preview(listing_id: str, include_demo: bool = False,
                   request: Request = None, db: Session = Depends(get_db)):
    # Reuse exactly the same ownership / demo visibility logic as listing detail.
    from .main import listing_detail
    listing_detail(listing_id, include_demo=include_demo, db=db, request=request)
    listing = db.get(Listing, listing_id)
    candidate = preview_data(db, listing)
    return {
        'listing_id': listing_id, 'title': listing.title, 'phases': candidate['phase_definitions'],
        'tasks': candidate['tasks'], 'analysis_basis': candidate['analysis_basis'],
        'disclaimer': candidate['disclaimer'], 'notice': candidate['notice'],
        'is_preview': True, 'simulation_only': True,
    }


@router.get('/transactions/{transaction_id}/development-roadmap')
def get_roadmap(transaction_id: str, db: Session = Depends(get_db), ctx=Depends(human)):
    tx = buyer_transaction(db, transaction_id, ctx)
    plan = db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id == tx.id))
    if plan: return plan_data(db, tx, plan)
    listing = db.get(Listing, tx.listing_id)
    return {'created': False, 'transaction_id': tx.id, 'listing_id': tx.listing_id,
            'preview': preview_data(db, listing), 'simulation_only': True}


@router.post('/transactions/{transaction_id}/development-roadmap', status_code=201)
def create_roadmap(transaction_id: str, db: Session = Depends(get_db), ctx=Depends(human)):
    tx = buyer_transaction(db, transaction_id, ctx, lock=True)
    existing = db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id == tx.id))
    if existing: return plan_data(db, tx, existing)
    listing = db.get(Listing, tx.listing_id)
    template = preview_data(db, listing)
    plan = DevelopmentRoadmap(transaction_id=tx.id, listing_id=listing.id, buyer_id=tx.buyer_id,
                              source_fingerprint=template['source_fingerprint'],
                              analysis_basis=template['analysis_basis'])
    db.add(plan)
    db.flush()
    for item in template['tasks']:
        db.add(DevelopmentRoadmapTask(
            roadmap_id=plan.id, task_key=item['key'], position=item['position'],
            phase=item['phase'], title=item['title'], detail=item['detail'],
            difficulty=item['difficulty'], assistance=item['assistance'], priority=item['priority'],
            prerequisites=item['prerequisites'], steps=item['steps'],
            success_criteria=item['success_criteria'], evidence=item['evidence'],
            source_kind=item['source_kind']))
    event(db, ctx, 'roadmap.created', plan.id,
          {'transaction_id': tx.id, 'task_count': len(template['tasks'])})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        reject(409, '동시에 로드맵이 생성되었습니다. 새로고침해 주세요.')
    return plan_data(db, tx, plan)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TaskProgress(Strict):
    status: str
    buyer_note: str = Field(default='', max_length=2000)
    expected_version: int = Field(ge=1)
    blocked_reason: str | None = None


def managed_task(db, tx, task_id):
    # Serialize status changes on the plan row so dependency checks remain consistent.
    plan = db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id == tx.id).with_for_update())
    if not plan: reject(404, '먼저 로드맵을 만들어 주세요.')
    task = db.scalar(select(DevelopmentRoadmapTask).where(
        DevelopmentRoadmapTask.id == task_id, DevelopmentRoadmapTask.roadmap_id == plan.id).with_for_update())
    if not task: reject(404, '해당 작업을 찾을 수 없습니다.')
    return plan, task


@router.patch('/transactions/{transaction_id}/development-roadmap/tasks/{task_id}')
def update_task(transaction_id: str, task_id: str, data: TaskProgress,
                db: Session = Depends(get_db), ctx=Depends(human)):
    tx = buyer_transaction(db, transaction_id, ctx)
    plan, task = managed_task(db, tx, task_id)
    if data.status not in VALID_STATUSES: reject(422, '허용되지 않은 작업 상태입니다.')
    if task.version != data.expected_version: reject(409, '다른 변경 사항이 있습니다. 새로고침해 주세요.')
    all_tasks = tasks_for(db, plan)
    current = {t.task_key: t for t in all_tasks}
    if data.status in ('COMPLETED', 'IN_PROGRESS'):
        unmet = [key for key in task.prerequisites
                 if key not in current or current[key].status != 'COMPLETED']
        if unmet:
            reject(409, '먼저 선행 작업을 완료해 주세요: ' + ', '.join(unmet))
    if task.status == 'COMPLETED' and data.status != 'COMPLETED':
        dependents = [t.title for t in all_tasks if task.task_key in t.prerequisites
                      and t.status in ('IN_PROGRESS', 'COMPLETED')]
        if dependents:
            reject(409, '후속 작업이 이미 진행 중입니다. 먼저 후속 작업의 상태를 되돌려 주세요.')
    allowed_reasons={'ENV_SETUP','MISSING_FILE','RUNTIME_ERROR','UNFAMILIAR_TECH','OTHER'}
    if data.status=='BLOCKED' and data.blocked_reason not in allowed_reasons:
        reject(422,'막힘 사유를 선택해 주세요.')
    previous = task.status
    task.blocked_reason=data.blocked_reason if data.status=='BLOCKED' else None
    task.status = data.status
    task.buyer_note = data.buyer_note.strip()
    task.version += 1
    task.updated_at = now()
    event(db, ctx, 'roadmap.task.updated', plan.id,
          {'task_key': task.task_key, 'from': previous, 'to': task.status})
    db.commit()
    return plan_data(db, tx, plan)


class AddTask(Strict):
    title: str = Field(min_length=3, max_length=120)
    detail: str = Field(min_length=10, max_length=1500)
    phase: str = 'VERIFY'
    difficulty: str = 'MEDIUM'
    assistance: str = 'GUIDED'
    priority: str = 'MEDIUM'
    prerequisites: list[str] = Field(default_factory=list, max_length=6)


@router.post('/transactions/{transaction_id}/development-roadmap/tasks', status_code=201)
def add_task(transaction_id: str, data: AddTask,
             db: Session = Depends(get_db), ctx=Depends(human)):
    tx = buyer_transaction(db, transaction_id, ctx, lock=True)
    plan = db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id == tx.id))
    if not plan: reject(404, '먼저 로드맵을 만들어 주세요.')
    rows = tasks_for(db, plan)
    if sum(r.source_kind == 'BUYER' for r in rows) >= 30:
        reject(409, '개인 추가 작업은 최대 30개입니다.')
    if data.phase not in {p['key'] for p in PHASES} or data.difficulty not in {'EASY', 'MEDIUM', 'HARD'} \
       or data.assistance not in {'SELF', 'GUIDED', 'EXPERT'} or data.priority not in {'LOW', 'MEDIUM', 'HIGH'}:
        reject(422, '단계·난이도·도움 유형 또는 우선순위가 올바르지 않습니다.')
    if not data.title.strip() or not data.detail.strip():
        reject(422, '작업 제목과 내용을 입력해 주세요.')
    if len(data.prerequisites) != len(set(data.prerequisites)) or set(data.prerequisites) - {r.task_key for r in rows}:
        reject(422, '선행 작업은 현재 로드맵의 기존 작업에서만 선택할 수 있습니다.')
    task = DevelopmentRoadmapTask(
        roadmap_id=plan.id, task_key='CUSTOM_' + uuid4().hex[:20],
        position=max((r.position for r in rows), default=0) + 1,
        phase=data.phase, title=data.title.strip(), detail=data.detail.strip(),
        difficulty=data.difficulty, assistance=data.assistance, priority=data.priority,
        prerequisites=data.prerequisites, steps=[], success_criteria=[],
        evidence='BUYER_ADDED', source_kind='BUYER')
    db.add(task)
    db.flush()
    event(db, ctx, 'roadmap.task.created', plan.id, {'task_key': task.task_key})
    db.commit()
    return plan_data(db, tx, plan)


@router.get('/transactions/{transaction_id}/development-roadmap/export')
def export_roadmap(transaction_id: str, db: Session = Depends(get_db), ctx=Depends(human)):
    tx = buyer_transaction(db, transaction_id, ctx)
    plan = db.scalar(select(DevelopmentRoadmap).where(DevelopmentRoadmap.transaction_id == tx.id))
    if not plan: reject(404, '먼저 로드맵을 만들어 주세요.')
    data = plan_data(db, tx, plan)
    lines = ['# ProjectAgain · 인수 후 개발 로드맵 (시연)', '',
             f'프로젝트: {data["listing_title"]}',
             f'진행: {data["completed_tasks"]}/{data["total_tasks"]}', '', DISCLAIMER, '']
    for phase in PHASES:
        lines.extend(['', '## ' + phase['label'], ''])
        for item in data['tasks']:
            if item['phase'] != phase['key']: continue
            lines.extend([f'- [{"x" if item["status"]=="COMPLETED" else " "}] {item["title"]} ({item["difficulty"]}, {item["assistance"]})',
                          '  - ' + item['detail'], '  - 상태: ' + item['status']])
            if item['prerequisites']: lines.append('  - 선행 작업: ' + ', '.join(item['prerequisites']))
            if item['buyer_note']: lines.append('  - 메모: ' + item['buyer_note'].replace('\n', ' '))
    return Response(content='\ufeff'+'\n'.join(lines)+'\n', media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="projectagain-roadmap-{tx.id[:8]}.md"',
                             'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
