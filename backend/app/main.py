"""Korean micro digital asset marketplace; v1 demo workflows; NO payments or seller-code execution."""
import hashlib
import json
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import jwt
from pydantic import ValidationError
from .db import get_db
from .models import (User, Listing, Offer, Transaction, Favorite, BuyerPreferences, HandoverCheck,
                     InspectionReport, AgentAction, ServiceGrant, ListingAsset, ModerationReport, AuditEvent, IdempotencyRecord, ListingSourceSummary, now, uid)
from .security import auth_context, human, allowed, only_human, hash_password, verify_password, token_for, COOKIE_NAME, COOKIE_SECURE, JWT_SECRET, APP_ENV
from .schemas import (Register, Login, ListingCreate, ListingPatch, PreferencesIn, OfferCreate, Counter,
                      Version, Transition, CheckCreate, CheckPatch, InspectionCreate, AgentActionCreate,
                      GrantCreate, ReportCreate, AgentListingSuggestion)

app = FastAPI(title='ProjectAgain Marketplace', version='0.13.0', description='디지털 프로젝트 거래 준비 및 DEMO 거래 플랫폼; 실제 결제/권리 이전 미지원')
if APP_ENV != 'production':
    app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],
                       allow_credentials=True, allow_methods=['*'], allow_headers=['*'])


def fail(status, detail):
    raise HTTPException(status_code=status, detail=detail)


def output(obj):
    if isinstance(obj, datetime): return obj.isoformat()
    if isinstance(obj, list): return [output(v) for v in obj]
    if isinstance(obj, dict): return {k: output(v) for k, v in obj.items()}
    return obj


def view(row, fields):
    return output({f: getattr(row, f) for f in fields})


PUBLIC_LISTING_FIELDS = ['id','seller_id','title','description','category','lifecycle_status','sale_rights_type',
                         'inventory_mode','price_krw','tech_stack','included_assets','excluded_assets',
                         'known_defects','required_services','monthly_cost_estimate_krw','handover_days_estimate',
                         'seller_support_days','has_revenue','revenue_krw_claimed','revenue_claim_verification',
                         'verification_status','status','is_demo','version','created_at','updated_at']


def listing_card_view(db, row):
    """Public-safe card cover; only image IDs (never object storage keys)."""
    from .marketplace_models import ListingMedia
    data=view(row,PUBLIC_LISTING_FIELDS)
    first=db.scalar(select(ListingMedia.id).where(ListingMedia.listing_id==row.id).order_by(ListingMedia.position,ListingMedia.created_at).limit(1))
    data['cover_image_url']=(f'/api/v1/listings/{row.id}/media/{first}/image'+('?demo=1' if row.is_demo else '')) if first else None
    return data

OFFER_FIELDS = ['id','listing_id','buyer_id','seller_id','parent_offer_id','proposed_by','offered_price_krw',
                'terms','status','version','is_demo','expires_at','created_at','thread_id','listing_version_at_proposal']
TX_FIELDS = ['id','listing_id','accepted_offer_id','buyer_id','seller_id','status','is_demo','version','created_at','completed_at']
CHECK_FIELDS = ['id','transaction_id','check_key','description','seller_submitted','agent_checked',
                'buyer_confirmed','result','evidence_refs','remarks','version']
ACTION_FIELDS = ['id','user_id','requesting_agent_id','action_type','resource_id','proposed_payload',
                 'payload_sha256','status','expires_at','created_at','approved_at','executed_at','result_resource_id']


def audit(db, ctx, action, type_, id_, old=None, new=None, demo=True):
    db.add(AuditEvent(actor_user_id=ctx['user'].id if ctx else None,
                      actor_type='AGENT' if ctx and ctx['kind'] == 'agent' else ('ADMIN' if ctx and ctx['user'].role == 'ADMIN' else 'USER'),
                      action=action, resource_type=type_, resource_id=id_, old_state=old, new_state=new, is_demo=demo))


def must_listing(db, id_):
    thing = db.get(Listing, id_)
    if not thing or thing.status == 'REMOVED': fail(404, '매물을 찾을 수 없습니다.')
    return thing


def must_offer(db, id_, ctx, lock=False):
    q = select(Offer).where(Offer.id == id_)
    if lock: q = q.with_for_update()
    thing = db.scalar(q)
    if not thing or ctx['user'].id not in (thing.buyer_id, thing.seller_id):
        fail(404, '제안을 찾을 수 없습니다.')
    return thing


def must_tx(db, id_, ctx, lock=False):
    q = select(Transaction).where(Transaction.id == id_)
    if lock: q = q.with_for_update()
    thing = db.scalar(q)
    if not thing or ctx['user'].id not in (thing.buyer_id, thing.seller_id):
        fail(404, '거래를 찾을 수 없습니다.')
    return thing


def future(dt):
    if dt.tzinfo is None or dt.astimezone(timezone.utc) <= now(): fail(422, '만료 시각은 미래의 타임존 포함 시각이어야 합니다.')
    if dt.astimezone(timezone.utc) > now() + timedelta(days=30): fail(422, '최대 30일 이내로 설정하세요.')


def version(row, expected):
    if row.version != expected: fail(409, '데이터가 변경되었습니다. 새로고침한 뒤 다시 시도하세요.')


def safe_terms(terms):
    raw = json.dumps(terms, ensure_ascii=False)
    if len(raw.encode('utf-8')) > 5000: fail(422, '제안 조건이 너무 깁니다.')
    if not isinstance(terms, dict): fail(422, '제안 조건 형식 오류')
    return terms


def agent_write_mode() -> str:
    """Fail closed: demo writes must be explicitly enabled outside isolated tests.

    Never support live paid transactions until payment, ownership and legal
    workflows have been separately reviewed and implemented.
    """
    requested = os.getenv('AGENT_WRITE_MODE', 'demo_only' if APP_ENV == 'test' else 'disabled')
    return 'demo_only' if requested == 'demo_only' else 'disabled'


def require_agent_demo_write(action_type: str, resource_is_demo: bool):
    # Existing read and draft endpoints remain available even in disabled mode.
    if not resource_is_demo or agent_write_mode() != 'demo_only':
        fail(403, '에이전트 실행은 현재 비활성화되어 있거나 DEMO 자산만 허용됩니다.')


def digest_payload(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def idem_replay(db, ctx, request, route, payload):
    key = request.headers.get('idempotency-key')
    if not key:
        return None
    if len(key) < 8 or len(key) > 128:
        fail(422, 'Idempotency-Key 길이는 8~128자여야 합니다.')
    row = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor_id==ctx['user'].id,
              IdempotencyRecord.route==route,IdempotencyRecord.request_key==key))
    if row:
        if row.body_sha256 != digest_payload(payload): fail(409, '같은 중복 방지 키로 다른 요청을 보낼 수 없습니다.')
        return row.response_json
    return None


def idem_record(db, ctx, request, route, payload, response):
    key = request.headers.get('idempotency-key')
    if key:
        db.add(IdempotencyRecord(actor_id=ctx['user'].id,route=route,request_key=key,
                                 body_sha256=digest_payload(payload),response_json=response))




@app.middleware('http')
async def attach_request_id(request: Request, call_next):
    supplied = request.headers.get('x-request-id', '')
    request.state.request_id = supplied if re.fullmatch(r'[a-zA-Z0-9_-]{8,64}', supplied) else secrets.token_hex(12)
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/v1/auth') or request.url.path.startswith('/api/v1/assets') or request.url.path.startswith('/api/v1/agent-actions'):
        response.headers['Cache-Control'] = 'no-store'
    if APP_ENV == 'production': response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


@app.exception_handler(RequestValidationError)
async def catch_validation(request: Request, exc: RequestValidationError):
    # Do not echo arbitrary submitted data or validation ctx exceptions.
    details = [{'field': '.'.join(str(v) for v in error['loc']), 'message': error['msg']}
               for error in exc.errors()[:20]]
    return JSONResponse(status_code=422, content={'error': {
        'code': 'VALIDATION_ERROR', 'message': '입력값을 확인해 주세요.',
        'request_id': getattr(request.state, 'request_id', ''), 'details': details}})

@app.exception_handler(HTTPException)
async def catch_http(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={'error': {'code': str(exc.status_code), 'message': str(exc.detail), 'request_id': getattr(request.state, 'request_id', '')}})


@app.get('/health')
def health(): return {'status': 'ok', 'service': 'micro-asset-market', 'payments_enabled': False}


@app.post('/api/v1/auth/register', status_code=201)
def register(data: Register, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email)): fail(409, '이미 가입된 이메일입니다.')
    user = User(email=data.email, password_hash=hash_password(data.password))
    db.add(user)
    try: db.commit()
    except IntegrityError:
        db.rollback(); fail(409, '이미 가입된 이메일입니다.')
    return {'id': user.id, 'email': user.email, 'role': user.role, 'email_verified': False}


@app.post('/api/v1/auth/login')
def login(data: Login, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(data.password, user.password_hash) or not user.is_active:
        from .stage2 import throttle
        throttle(db,f'{data.email.lower()}:{request.client.host if request.client else "unknown"}','login:failed',2)
        db.commit()
        fail(401, '이메일이나 비밀번호가 올바르지 않습니다.')
    token, csrf, expires = token_for(user)
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=COOKIE_SECURE, samesite='lax', max_age=8*3600, path='/')
    return {'user': {'id': user.id, 'email': user.email, 'role': user.role, 'email_verified': bool(user.email_verified_at)},
            'csrf_token': csrf, 'expires_at': expires.isoformat(), 'auth_mode': 'http_only_cookie'}


@app.post('/api/v1/auth/logout')
def logout(response: Response, ctx=Depends(human)):
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'ok': True}


@app.get('/api/v1/auth/me')
def me(ctx=Depends(auth_context)):
    u = ctx['user']
    data = {'id': u.id, 'email': u.email, 'role': u.role, 'email_verified': bool(u.email_verified_at)}
    if ctx['kind'] == 'session': data['csrf_token'] = ctx['csrf']
    else: data['scopes'] = ctx['scopes']
    return data


@app.post('/api/v1/auth/request-verification')
def request_verification(db: Session = Depends(get_db), ctx=Depends(human)):
    user = ctx['user']
    if user.email_verified_at: return {'message': '이미 인증된 이메일입니다.'}
    from .stage2 import throttle
    throttle(db,user.id,'email_verify',90)
    db.commit()
    base = os.getenv('PUBLIC_BASE_URL', 'http://localhost:5173').rstrip('/')
    token = jwt.encode({'sub': user.id, 'kind': 'verify_email', 'exp': now() + timedelta(minutes=30)}, JWT_SECRET, algorithm='HS256')
    link = f'{base}/verify-email?token={token}'
    server = os.getenv('SMTP_HOST')
    if not server:
        if APP_ENV == 'production': fail(503, '이메일 인증이 아직 설정되지 않았습니다.')
        return {'message': '개발 환경: 이메일 서버 미설정', 'development_verification_url': link}
    msg = EmailMessage()
    msg['From'] = os.getenv('SMTP_FROM', 'no-reply@example.invalid')
    msg['To'] = user.email
    msg['Subject'] = '이메일 인증 링크'
    msg.set_content(f'30분 안에 링크를 여세요.\n{link}')
    try:
        with smtplib.SMTP(server, int(os.getenv('SMTP_PORT', '587')), timeout=10) as smtp:
            smtp.starttls()
            smtp.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(msg)
    except Exception:
        fail(503, '이메일 발송에 실패했습니다.')
    return {'message': '인증 메일을 발송했습니다.'}


@app.post('/api/v1/auth/verify-email')
def verify_email(data: dict, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(str(data.get('token','')), JWT_SECRET, algorithms=['HS256'])
        if claims.get('kind') != 'verify_email': raise ValueError()
    except (jwt.PyJWTError, ValueError): fail(400, '인증 링크가 유효하지 않습니다.')
    user = db.get(User, claims['sub'])
    if not user: fail(404, '사용자가 없습니다.')
    user.email_verified_at = now()
    db.commit()
    return {'ok': True}


@app.get('/api/v1/listings')
def listings(q: str | None = None, category: str | None = None, lifecycle_status: str | None = None,
             sale_rights_type: str | None = None, min_price_krw: int | None = Query(default=None, ge=0),
             max_price_krw: int | None = Query(default=None, ge=0), limit: int = Query(default=24, ge=1, le=100),
             cursor: int = Query(default=0, ge=0), sort: str = 'newest', include_demo: bool = False,
             db: Session = Depends(get_db)):
    query = select(Listing).where(Listing.status == 'ACTIVE')
    if not include_demo: query = query.where(Listing.is_demo.is_(False))
    if q: query = query.where(or_(Listing.title.ilike(f'%{q[:100]}%'), Listing.description.ilike(f'%{q[:100]}%')))
    if category: query = query.where(Listing.category == category)
    if lifecycle_status: query = query.where(Listing.lifecycle_status == lifecycle_status)
    if sale_rights_type: query = query.where(Listing.sale_rights_type == sale_rights_type)
    if min_price_krw is not None: query = query.where(Listing.price_krw >= min_price_krw)
    if max_price_krw is not None: query = query.where(Listing.price_krw <= max_price_krw)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    sort_order = {'newest': [Listing.created_at.desc(), Listing.id.desc()],
                  'price_asc': [Listing.price_krw.asc(), Listing.id.asc()],
                  'price_desc': [Listing.price_krw.desc(), Listing.id.desc()]}.get(sort)
    if not sort_order: fail(422, '정렬 기준을 확인하세요.')
    rows = db.scalars(query.order_by(*sort_order).offset(cursor).limit(limit)).all()
    return {'items': [listing_card_view(db,r) for r in rows], 'next_cursor': str(cursor+len(rows)) if cursor+len(rows) < total else None, 'total_estimate': total}


@app.get('/api/v1/my/listings')
def my_listings(db: Session = Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'listing:read')
    return [listing_card_view(db,row) for row in db.scalars(select(Listing).where(Listing.seller_id == ctx['user'].id).order_by(Listing.created_at.desc())).all()]


@app.post('/api/v1/listings', status_code=201)
def create_listing(data: ListingCreate, db: Session = Depends(get_db), ctx=Depends(human)):
    if not data.rights_attested: fail(422, '본인이 판매 권리를 보유하고 있다는 진술이 필요합니다.')
    row = Listing(seller_id=ctx['user'].id, **data.model_dump(exclude={'import_id'}))
    row.import_id = data.import_id  # transient reference; not part of Listing schema
    if row.has_revenue: row.revenue_claim_verification = 'SELLER_CLAIMED_UNVERIFIED'
    db.add(row); db.flush()
    if data.import_id:
        from .project_imports import attach_import
        attached = attach_import(db, ctx['user'].id, row)
        audit(db, ctx, 'listing.import.attached', 'listing', row.id,
              new={'source_type':attached.source_type,'snapshot_sha256':attached.checksum_sha256},demo=row.is_demo)
    del row.import_id
    db.flush()  # attached ListingSourceSummary exists in the identity map for report generation
    from .readiness_report import save_report
    source = db.get(ListingSourceSummary, row.id)
    save_report(db, row, source.analysis if source else None)
    audit(db, ctx, 'listing.create', 'listing', row.id, new={'status': 'DRAFT'}, demo=row.is_demo)
    db.commit()
    return listing_card_view(db,row)


@app.get('/api/v1/listings/{listing_id}')
def listing_detail(listing_id: str, include_demo: bool = False, db: Session = Depends(get_db), request: Request = None):
    row = must_listing(db, listing_id)
    public = row.status == 'ACTIVE' and (not row.is_demo or include_demo)
    if not public:
        # A private listing is visible to its seller or admin; invalid sessions do not reveal its existence.
        try:
            ctx = auth_context(request, db)
            if ctx['user'].id != row.seller_id and ctx['user'].role != 'ADMIN': fail(404, '매물을 찾을 수 없습니다.')
            allowed(ctx, 'listing:read')
        except HTTPException:
            fail(404, '매물을 찾을 수 없습니다.')
    return listing_card_view(db,row)


@app.get('/api/v1/listings/{listing_id}/source-summary')
def listing_source_summary(listing_id: str, include_demo: bool = False,
                           db:Session=Depends(get_db), request:Request=None):
    # Keep report availability consistent with listing detail visibility.
    listing_detail(listing_id, include_demo=include_demo, db=db, request=request)
    row = db.get(ListingSourceSummary, listing_id)
    if not row: return {'available': False}
    return {'available': True, 'source_type': row.source_type,
            'analysis': row.analysis, 'created_at': output(row.created_at),
            'source_archive_visibility': 'PRIVATE_REVIEW_ONLY',
            'verification_status': 'STATIC_ONLY_UNVERIFIED'}


@app.get('/api/v1/listings/{listing_id}/takeover-report')
def takeover_report(listing_id: str, include_demo: bool = False,
                    db:Session=Depends(get_db), request:Request=None):
    listing_detail(listing_id, include_demo=include_demo, db=db, request=request)
    from .readiness_report import current_report
    from .models import InspectionReport
    report=current_report(db, db.get(Listing,listing_id))
    # Complement source evidence with independently submitted inspection records.
    # A submission is evidence of a claim, not proof that tests actually ran.
    inspections=db.scalars(select(InspectionReport).where(
        InspectionReport.listing_id==listing_id, InspectionReport.is_public==True
    ).order_by(InspectionReport.created_at.desc()).limit(10)).all()
    public_inspections=[{'report_type':x.report_type,'verdict':x.verdict,
                         'reviewer_kind':x.reviewer_kind,'created_at':output(x.created_at)} for x in inspections]
    return {'available':True,'analysis':report,'independent_report_summaries':public_inspections}


@app.api_route('/api/v1/listings/{listing_id}/ai-assistant/{path:path}',
               methods=['GET','POST','PATCH','PUT','DELETE'], include_in_schema=False)
def removed_builtin_ai_listing_route(listing_id: str, path: str):
    # Removed in v0.4. Avoid SPA's POST fallback turning a missing endpoint into 405.
    fail(404, '이 기능은 외부 에이전트 승인 흐름으로 이전했습니다.')


@app.patch('/api/v1/listings/{listing_id}')
def patch_listing(listing_id: str, data: ListingPatch, db: Session = Depends(get_db), ctx=Depends(human)):
    row = must_listing(db, listing_id)
    if row.seller_id != ctx['user'].id: fail(404, '수정할 매물이 없습니다.')
    version(row, data.expected_version)
    if row.status in ('RESERVED','CLOSED','REMOVED'): fail(409, '거래 중이거나 종료된 매물을 수정할 수 없습니다.')
    values = data.model_dump(exclude_unset=True, exclude={'expected_version'})
    if values.get('status') == 'ACTIVE': fail(403, '매물 공개는 관리자 검토가 필요합니다.')
    status = values.pop('status', None)
    if status == 'PENDING_REVIEW':
        if not row.rights_attested: fail(422, '권리 진술이 필요합니다.')
        # Live listings require verified email; test/demo listings can request review in development.
        if not row.is_demo and not ctx['user'].email_verified_at: fail(403, '일반 매물 공개 전 이메일 인증이 필요합니다.')
    if row.status == 'ACTIVE' and any(k != 'status' for k in values):
        status = 'PENDING_REVIEW'  # Changed public claims must be reviewed again.
    before = row.status
    for key, val in values.items(): setattr(row, key, val)
    if status:
        allowed_transitions = {'DRAFT': ['PENDING_REVIEW'], 'PENDING_REVIEW': ['DRAFT'],
                               'ACTIVE': ['PAUSED','PENDING_REVIEW'], 'PAUSED': ['PENDING_REVIEW','DRAFT']}
        if status not in allowed_transitions.get(row.status, []): fail(409, '허용되지 않은 매물 상태 전이입니다.')
        row.status = status
    row.version += 1
    if status=='PENDING_REVIEW':
        from .stage2 import notify
        admins=db.scalars(select(User).where(User.role=='ADMIN',User.is_active.is_(True))).all()
        for admin in admins:
            if admin.id!=row.seller_id:
                notify(db,admin.id,'LISTING_REVIEW_REQUEST','새로운 프로젝트 검토 요청이 도착했습니다.','listing',row.id)
    from .readiness_report import save_report
    source = db.get(ListingSourceSummary,row.id)
    save_report(db, row, source.analysis if source else None)
    audit(db, ctx, 'listing.update', 'listing', row.id, {'status': before}, {'status': row.status, 'version': row.version}, row.is_demo)
    db.commit()
    return listing_card_view(db,row)


@app.get('/api/v1/buyer-preferences/me')
def get_preferences(db: Session = Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'buyer_profile:read')
    row = db.get(BuyerPreferences, ctx['user'].id)
    if not row: return PreferencesIn().model_dump()
    return view(row, list(PreferencesIn.model_fields))


@app.put('/api/v1/buyer-preferences/me')
def save_preferences(data: PreferencesIn, db: Session = Depends(get_db), ctx=Depends(human)):
    row = db.get(BuyerPreferences, ctx['user'].id)
    if not row: row = BuyerPreferences(user_id=ctx['user'].id); db.add(row)
    for name,val in data.model_dump().items(): setattr(row,name,val)
    db.commit()
    return data


@app.get('/api/v1/favorites')
def get_favorites(db: Session = Depends(get_db), ctx=Depends(auth_context)):
    only_human(ctx)
    rows = db.scalars(select(Listing).join(Favorite, Favorite.listing_id == Listing.id).where(Favorite.user_id == ctx['user'].id, Listing.status == 'ACTIVE')).all()
    return {'items': [listing_card_view(db,x) for x in rows]}


@app.post('/api/v1/favorites', status_code=201)
def save_favorite(data: dict, db: Session = Depends(get_db), ctx=Depends(human)):
    row = must_listing(db, str(data.get('listing_id','')))
    if row.status != 'ACTIVE': fail(404, '게시된 매물이 아닙니다.')
    if not db.get(Favorite, {'user_id': ctx['user'].id, 'listing_id': row.id}):
        db.add(Favorite(user_id=ctx['user'].id, listing_id=row.id))
        db.commit()
    return {'ok': True}


@app.delete('/api/v1/favorites/{listing_id}')
def remove_favorite(listing_id: str, db: Session = Depends(get_db), ctx=Depends(human)):
    row = db.get(Favorite, {'user_id': ctx['user'].id, 'listing_id': listing_id})
    if row: db.delete(row); db.commit()
    return {'ok': True}


def do_offer(db, ctx, data: OfferCreate):
    row = db.scalar(select(Listing).where(Listing.id == data.listing_id).with_for_update())
    if not row or row.status != 'ACTIVE': fail(409, '현재 제안할 수 없는 매물입니다.')
    if row.seller_id == ctx['user'].id: fail(403, '본인 매물에는 제안할 수 없습니다.')
    future(data.expires_at); safe_terms(data.terms)
    from .v012_models import OfferThread
    from .offer_terms_v2 import validated_terms
    terms=validated_terms(data.terms,data.offered_price_krw,row)
    active=db.scalar(select(Offer).where(Offer.listing_id==row.id,Offer.buyer_id==ctx['user'].id,
        Offer.status=='PENDING').limit(1))
    if active: fail(409,'이미 진행 중인 협상이 있습니다. 기존 제안에서 이어가 주세요.')
    running=db.scalar(select(Transaction).where(Transaction.listing_id==row.id,
        Transaction.buyer_id==ctx['user'].id,Transaction.status.notin_(['CANCELLED'])).limit(1))
    if running: fail(409,'이 프로젝트에 이미 진행하거나 완료한 시연 거래가 있습니다.')
    thread=OfferThread(listing_id=row.id,buyer_id=ctx['user'].id,seller_id=row.seller_id)
    db.add(thread);db.flush()
    offer = Offer(listing_id=row.id, seller_id=row.seller_id, buyer_id=ctx['user'].id,
                  proposed_by=ctx['user'].id, offered_price_krw=data.offered_price_krw,
                  terms=terms, expires_at=data.expires_at, is_demo=True, thread_id=thread.id, listing_version_at_proposal=row.version)
    db.add(offer); db.flush()
    thread.last_offer_id=offer.id
    audit(db,ctx,'offer.create','offer',offer.id,new={'status':'PENDING','price':offer.offered_price_krw})
    from .stage2 import notify
    notify(db,row.seller_id,'OFFER_RECEIVED','새로운 시연 구매 제안이 도착했습니다.','offer',offer.id)
    return offer


@app.post('/api/v1/offers', status_code=201)
def create_offer(data: OfferCreate, request: Request, db: Session = Depends(get_db), ctx=Depends(human)):
    old=idem_replay(db,ctx,request,'offer.create',data.model_dump(mode='json'))
    if old is not None:return old
    row=do_offer(db,ctx,data)
    result=view(row,OFFER_FIELDS)
    idem_record(db,ctx,request,'offer.create',data.model_dump(mode='json'),result)
    try:db.commit()
    except IntegrityError:
        db.rollback();fail(409,'이미 처리된 중복 제안입니다.')
    return result


@app.get('/api/v1/offers')
def get_offers(listing_id: str | None = None, status: str | None = None, db: Session = Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'offer:read')
    q=select(Offer).where(or_(Offer.seller_id == ctx['user'].id, Offer.buyer_id == ctx['user'].id))
    if listing_id: q=q.where(Offer.listing_id == listing_id)
    if status: q=q.where(Offer.status == status)
    items=db.scalars(q.order_by(Offer.created_at.desc()).limit(200)).all()
    return {'items':[view(row,OFFER_FIELDS) for row in items], 'next_cursor': None}


@app.get('/api/v1/offers/{offer_id}')
def get_offer(offer_id: str, db: Session = Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'offer:read')
    return view(must_offer(db,offer_id,ctx),OFFER_FIELDS)


def respondable(offer, ctx, expected):
    version(offer,expected)
    if offer.status != 'PENDING': fail(409, '이미 처리된 제안입니다.')
    if offer.expires_at.replace(tzinfo=timezone.utc) <= now():
        offer.status='EXPIRED'; offer.version+=1
        fail(409, '만료된 제안입니다.')
    if offer.proposed_by == ctx['user'].id: fail(403, '본인이 보낸 제안은 수락하거나 역제안할 수 없습니다.')


def do_counter(db,ctx,offer,data):
    respondable(offer,ctx,data.expected_version)
    future(data.expires_at);safe_terms(data.terms)
    listing=must_listing(db,offer.listing_id)
    from .offer_terms_v2 import validated_terms
    terms=validated_terms(data.terms,data.offered_price_krw,listing)
    from .v012_models import OfferThread
    thread=db.get(OfferThread,offer.thread_id) if offer.thread_id else None
    if listing.status != 'ACTIVE': fail(409,'거래할 수 없는 매물입니다.')
    offer.status='COUNTERED';offer.version+=1
    child=Offer(listing_id=offer.listing_id,buyer_id=offer.buyer_id,seller_id=offer.seller_id,
                parent_offer_id=offer.id,proposed_by=ctx['user'].id,offered_price_krw=data.offered_price_krw,
                terms=terms,expires_at=data.expires_at,thread_id=offer.thread_id,listing_version_at_proposal=listing.version)
    db.add(child);db.flush()
    if thread:
        thread.last_offer_id=child.id;thread.version+=1;thread.last_activity_at=now()
    audit(db,ctx,'offer.counter','offer',offer.id,{'status':'PENDING'}, {'status':'COUNTERED','child_offer_id':child.id})
    from .stage2 import notify
    receiver=offer.buyer_id if ctx['user'].id==offer.seller_id else offer.seller_id
    notify(db,receiver,'COUNTER_OFFER','시연 거래 역제안이 도착했습니다.','offer',child.id)
    return child


@app.post('/api/v1/offers/{offer_id}/counter', status_code=201)
def counter_offer(offer_id: str, data: Counter, request: Request, db: Session = Depends(get_db), ctx=Depends(human)):
    route=f'offer.counter:{offer_id}'
    old=idem_replay(db,ctx,request,route,data.model_dump(mode='json'))
    if old is not None:return old
    row=must_offer(db,offer_id,ctx,lock=True)
    child=do_counter(db,ctx,row,data)
    result=view(child,OFFER_FIELDS)
    idem_record(db,ctx,request,route,data.model_dump(mode='json'),result)
    try:db.commit()
    except IntegrityError:
        db.rollback();fail(409,'중복 역제안 요청입니다.')
    return result


@app.post('/api/v1/offers/{offer_id}/decline')
def decline_offer(offer_id: str, data: Version, db: Session = Depends(get_db), ctx=Depends(human)):
    row=must_offer(db,offer_id,ctx,lock=True)
    respondable(row,ctx,data.expected_version)
    row.status='DECLINED';row.version+=1
    from .v012_models import OfferThread
    thread=db.get(OfferThread,row.thread_id) if row.thread_id else None
    if thread:thread.status='DECLINED';thread.version+=1;thread.last_activity_at=now()
    audit(db,ctx,'offer.decline','offer',row.id,{'status':'PENDING'},{'status':'DECLINED'})
    db.commit();return view(row,OFFER_FIELDS)


@app.post('/api/v1/offers/{offer_id}/withdraw')
def withdraw_offer(offer_id: str, data: Version, db: Session = Depends(get_db), ctx=Depends(human)):
    row=must_offer(db,offer_id,ctx,lock=True)
    version(row,data.expected_version)
    if row.status != 'PENDING' or row.proposed_by != ctx['user'].id: fail(409,'철회할 수 없는 제안입니다.')
    row.status='WITHDRAWN';row.version+=1
    from .v012_models import OfferThread
    thread=db.get(OfferThread,row.thread_id) if row.thread_id else None
    if thread:thread.status='WITHDRAWN';thread.version+=1;thread.last_activity_at=now()
    audit(db,ctx,'offer.withdraw','offer',row.id,{'status':'PENDING'},{'status':'WITHDRAWN'})
    db.commit();return view(row,OFFER_FIELDS)


def do_accept(db,ctx,offer,expected):
    respondable(offer,ctx,expected)
    listing=db.scalar(select(Listing).where(Listing.id==offer.listing_id).with_for_update())
    if not listing or listing.status!='ACTIVE': fail(409,'제안 대상 매물이 활성 상태가 아닙니다.')
    if offer.listing_version_at_proposal is not None and listing.version != offer.listing_version_at_proposal:
        fail(409,'매물의 권리·자산 정보가 변경되었습니다. 새로운 조건을 확인하고 다시 제안해 주세요.')
    from .v012_models import OfferThread
    thread=db.scalar(select(OfferThread).where(OfferThread.id==offer.thread_id).with_for_update()) if offer.thread_id else None
    if thread and (thread.status!='UNRESOLVED' or thread.last_offer_id!=offer.id):
        fail(409,'최신 활성 제안만 수락할 수 있습니다.')
    # Prevent duplicate demo handovers by the same buyer, not other buyers' simulations.
    existing=db.scalar(select(Transaction).where(Transaction.listing_id==listing.id,
        Transaction.buyer_id==offer.buyer_id,Transaction.status!='CANCELLED').limit(1))
    if existing: fail(409,'이미 이 프로젝트에 진행 또는 완료된 모의 인수가 있습니다.')
    tx=Transaction(listing_id=listing.id,accepted_offer_id=offer.id,buyer_id=offer.buyer_id,
                   seller_id=offer.seller_id,exclusive_guard_listing_id=None,is_demo=True)
    db.add(tx)
    offer.status='ACCEPTED';offer.version+=1
    if thread:thread.status='ACCEPTED';thread.version+=1;thread.last_activity_at=now()
    # CRITICAL: DEMO never reserves or closes a real-world listing.
    db.flush()
    from .deal_management import prepare_agreement, evt
    prepare_agreement(db,tx,ctx)
    evt(db,tx,ctx,'DEAL_CREATED',{'offer_id':offer.id,'listing_id':listing.id,'demo_only':True})
    for key,desc in [('source','소스코드와 필수 프로젝트 파일'),('docs','설치·운영 문서'),('licenses','권리 및 외부 라이선스'),('deploy','새 환경 실행 확인')]:
        db.add(HandoverCheck(transaction_id=tx.id,check_key=key,description=desc))
    audit(db,ctx,'offer.accept','offer',offer.id,{'status':'PENDING'},{'status':'ACCEPTED','transaction_id':tx.id})
    from .stage2 import notify
    receiver=offer.buyer_id if ctx['user'].id==offer.seller_id else offer.seller_id
    notify(db,receiver,'OFFER_ACCEPTED','시연 거래가 수락되고 인수인계가 시작됐습니다.','transaction',tx.id)
    return tx


@app.post('/api/v1/offers/{offer_id}/accept', status_code=201)
def accept_offer(offer_id: str, data: Version, request: Request, db: Session = Depends(get_db), ctx=Depends(human)):
    route=f'offer.accept:{offer_id}'
    old=idem_replay(db,ctx,request,route,data.model_dump())
    if old is not None:return old
    offer=must_offer(db,offer_id,ctx,lock=True)
    tx=do_accept(db,ctx,offer,data.expected_version)
    result=view(tx,TX_FIELDS)
    idem_record(db,ctx,request,route,data.model_dump(),result)
    try: db.commit()
    except IntegrityError:
        db.rollback();fail(409,'이미 수락된 매물입니다.')
    return result


@app.get('/api/v1/transactions')
def my_transactions(db: Session = Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'transaction:read')
    rows=db.scalars(select(Transaction).where(or_(Transaction.buyer_id==ctx['user'].id,Transaction.seller_id==ctx['user'].id)).order_by(Transaction.created_at.desc()).limit(100)).all()
    return {'items':[view(x,TX_FIELDS) for x in rows]}


@app.get('/api/v1/transactions/{transaction_id}')
def get_transaction(transaction_id: str, db: Session = Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'transaction:read')
    return view(must_tx(db,transaction_id,ctx),TX_FIELDS)


@app.post('/api/v1/transactions/{transaction_id}/transition')
def transition_transaction(transaction_id: str,data: Transition,db: Session = Depends(get_db),ctx=Depends(human)):
    row=must_tx(db,transaction_id,ctx,lock=True)
    version(row,data.expected_version)
    if data.status in ('DISPUTED','CANCELLED'):
        fail(409,'분쟁 접수와 거래 취소는 거래 관리 화면의 별도 절차를 이용해야 합니다.')
    from .deal_models import DealAgreement, DealCancellation
    if db.scalar(select(DealCancellation.id).where(DealCancellation.transaction_id==row.id,DealCancellation.status=='PENDING')):
        fail(409,'거래 취소 요청에 응답한 뒤 인수인계 단계를 진행해 주세요.')
    agreement=db.scalar(select(DealAgreement).where(DealAgreement.transaction_id==row.id))
    if not agreement or agreement.status!='ACKNOWLEDGED':
        fail(409,'구매자와 판매자가 거래 조건을 모두 확인해야 인수인계를 진행할 수 있습니다.')
    allowed_moves={'AWAITING_HANDOVER':['HANDOVER_IN_PROGRESS','DISPUTED','CANCELLED'],
                   'HANDOVER_IN_PROGRESS':['HANDOVER_REVIEW','DISPUTED','CANCELLED'],
                   'HANDOVER_REVIEW':['HANDOVER_IN_PROGRESS','DEMO_COMPLETED','DISPUTED','CANCELLED'],
                   'DISPUTED':['HANDOVER_IN_PROGRESS','CANCELLED']}
    if data.status not in allowed_moves.get(row.status,[]): fail(409,'허용되지 않은 거래 상태 전이입니다.')
    if data.status in ('HANDOVER_IN_PROGRESS','HANDOVER_REVIEW') and row.seller_id!=ctx['user'].id:
        fail(403,'판매자만 해당 단계를 변경할 수 있습니다.')
    if data.status=='DEMO_COMPLETED':
        if row.buyer_id != ctx['user'].id: fail(403,'구매자만 최종 검수를 승인합니다.')
        checks=db.scalars(select(HandoverCheck).where(HandoverCheck.transaction_id==row.id)).all()
        if not checks or any(not ch.seller_submitted or not ch.buyer_confirmed or ch.result != 'BUYER_CONFIRMED' for ch in checks):
            fail(409,'모든 인수인계 항목이 판매자 제출 및 구매자 최종 확인 상태여야 합니다.')
        from .models import FixRequest
        outstanding=db.scalar(select(func.count()).select_from(FixRequest).where(
            FixRequest.transaction_id==row.id, FixRequest.status!='CONFIRMED')) or 0
        if outstanding:fail(409,'구매자가 최종 확인하지 않은 보완 요청이 있습니다.')
    old=row.status;row.status=data.status;row.version+=1
    if data.status == 'DEMO_COMPLETED':
        row.completed_at=now()
        from .v012_support import start_support_policy
        start_support_policy(db,row,ctx)
    # Simulated stages never mutate Listing.status or exclusive inventory guards.
    audit(db,ctx,'transaction.transition','transaction',row.id,{'status':old},{'status':row.status})
    from .deal_management import evt
    evt(db,row,ctx,'HANDOVER_STAGE_CHANGED',{'from':old,'to':row.status})
    from .notifications_v07 import notify
    notify(db,row.seller_id if ctx['user'].id==row.buyer_id else row.buyer_id,'DEAL_HANDOVER','모의 거래 인수인계 상태가 변경됐습니다.','transaction',row.id)
    db.commit();return view(row,TX_FIELDS)


@app.get('/api/v1/transactions/{transaction_id}/handover-checks')
def get_checks(transaction_id: str,db: Session=Depends(get_db),ctx=Depends(auth_context)):
    allowed(ctx, 'handover:read')
    must_tx(db,transaction_id,ctx)
    return {'items':[view(x,CHECK_FIELDS) for x in db.scalars(select(HandoverCheck).where(HandoverCheck.transaction_id==transaction_id)).all()]}


def update_check_internal(db,ctx,row,body,agent=False):
    version(row,body.expected_version)
    tx=must_tx(db,row.transaction_id,ctx)
    if tx.status in ('DEMO_COMPLETED','CANCELLED'): fail(409,'종료된 모의 거래입니다.')
    role = 'AGENT' if agent else ('SELLER' if tx.seller_id==ctx['user'].id else 'BUYER')
    result=body.result
    if result=='SELLER_SUBMITTED' and role!='SELLER': fail(403,'판매자만 자료 제출을 기록할 수 있습니다.')
    if result=='BUYER_CONFIRMED' and role!='BUYER': fail(403,'구매자만 수락 여부를 확인할 수 있습니다.')
    if result=='AGENT_CHECKED' and role!='AGENT': fail(403,'검사 서비스만 자동 검사 결과를 기록합니다.')
    if result=='BUYER_CONFIRMED' and not row.seller_submitted: fail(409,'판매자의 자료 제출이 선행되어야 합니다.')
    old=row.result;row.result=result;row.version+=1
    # A changed handover state invalidates stale buyer approval. In particular,
    # seller resubmission and agent reinspection must require new buyer consent.
    if result != 'BUYER_CONFIRMED':row.buyer_confirmed=False
    if result == 'SELLER_SUBMITTED':
        row.seller_submitted=True
        row.agent_checked=False
    elif result == 'AGENT_CHECKED':
        if not row.seller_submitted:fail(409,'판매자가 먼저 자료를 제출해야 합니다.')
        row.agent_checked=True
    elif result == 'BUYER_CONFIRMED':row.buyer_confirmed=True
    elif result in ('NEEDS_FIX','NOT_TESTED'):
        row.seller_submitted=False
        row.agent_checked=False
    row.evidence_refs=body.evidence_refs;row.remarks=body.remarks
    audit(db,ctx,'handover.update','handover_check',row.id,{'result':old},{'result':result})
    from .deal_management import evt
    evt(db,tx,ctx,'HANDOVER_ITEM_UPDATED',{'check_key':row.check_key,'result':result})
    return row


@app.post('/api/v1/transactions/{transaction_id}/handover-checks', status_code=201)
def add_check(transaction_id:str,data:CheckCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    tx=must_tx(db,transaction_id,ctx)
    if ctx['user'].id!=tx.seller_id: fail(403,'판매자만 인계 항목을 추가합니다.')
    if tx.status in ('DEMO_COMPLETED','CANCELLED'):fail(409,'종료된 거래입니다.')
    if db.scalar(select(HandoverCheck).where(HandoverCheck.transaction_id==tx.id,HandoverCheck.check_key==data.check_key)):
        fail(409,'중복된 항목입니다.')
    if data.result not in ('NOT_TESTED','SELLER_SUBMITTED'): fail(422,'신규 항목은 미검사 또는 판매자 제출만 가능합니다.')
    ch=HandoverCheck(transaction_id=tx.id,**data.model_dump(),seller_submitted=data.result=='SELLER_SUBMITTED')
    db.add(ch);db.flush();audit(db,ctx,'handover.add','handover_check',ch.id,new={'result':ch.result})
    db.commit();return view(ch,CHECK_FIELDS)


@app.patch('/api/v1/transactions/{transaction_id}/handover-checks/{check_id}')
def update_check(transaction_id:str,check_id:str,data:CheckPatch,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    tx=must_tx(db,transaction_id,ctx)
    row=db.get(HandoverCheck,check_id)
    if not row or row.transaction_id!=tx.id:fail(404,'검수 항목이 없습니다.')
    if ctx['kind']=='agent':allowed(ctx,'handover:report')
    row=update_check_internal(db,ctx,row,data,ctx['kind']=='agent')
    db.commit();return view(row,CHECK_FIELDS)

@app.get('/api/v1/listings/{listing_id}/inspection-reports')
def get_inspections(listing_id: str, db: Session=Depends(get_db), ctx=Depends(auth_context)):
    allowed(ctx, 'inspection:read')
    listing=must_listing(db,listing_id)
    if listing.seller_id != ctx['user'].id and ctx['user'].role != 'ADMIN':
        if listing.status!='ACTIVE': fail(404,'매물에 접근할 수 없습니다.')
        q=select(InspectionReport).where(InspectionReport.listing_id==listing_id,
                  or_(InspectionReport.is_public.is_(True), InspectionReport.submitted_by_user_id==ctx['user'].id))
    else:q=select(InspectionReport).where(InspectionReport.listing_id==listing_id)
    return {'items':[view(r,['id','listing_id','report_type','verdict','reviewer_kind','findings','evidence_refs','is_public','created_at']) for r in db.scalars(q.order_by(InspectionReport.created_at.desc())).all()]}


@app.post('/api/v1/listings/{listing_id}/inspection-reports',status_code=201)
def create_inspection(listing_id:str,data:InspectionCreate,request:Request,
                      db:Session=Depends(get_db),ctx=Depends(auth_context)):
    listing=must_listing(db,listing_id)
    if ctx['kind']=='agent':allowed(ctx,'inspection:write')
    if listing.seller_id != ctx['user'].id and ctx['user'].role!='ADMIN':
        # A buyer's delegated agent may submit PRIVATE evidence only after a seller
        # explicitly granted that buyer temporary inspection access to the exact file.
        if ctx['kind']!='agent':fail(403,'매수자 실사 보고서는 에이전트 위임 토큰으로 제출해야 합니다.')
        if listing.status!='ACTIVE':fail(403,'실사 보고서를 제출할 수 없는 매물입니다.')
        if not data.source_version_sha256:
            fail(422,'구매자 보고서는 승인된 원본 파일의 SHA-256이 필요합니다.')
        from .models import InspectionAccess
        allowed_source=db.scalar(select(ListingAsset.id).join(
            InspectionAccess,InspectionAccess.asset_id==ListingAsset.id).where(
            ListingAsset.listing_id==listing_id,
            ListingAsset.upload_status=='APPROVED',
            ListingAsset.checksum_sha256==data.source_version_sha256,
            InspectionAccess.principal_user_id==ctx['user'].id,
            InspectionAccess.revoked_at.is_(None),
            InspectionAccess.expires_at>now()).limit(1))
        if not allowed_source:fail(403,'판매자가 승인한 해당 원본 파일의 실사 권한이 없습니다.')
    payload={'listing_id':listing_id,**data.model_dump(mode='json')}
    replay=idem_replay(db,ctx,request,'inspection.create',payload)
    if replay is not None:return replay
    row=InspectionReport(listing_id=listing_id,submitted_by_user_id=ctx['user'].id,
                         reviewer_kind='AI_AGENT' if ctx['kind']=='agent' else 'HUMAN',
                         **data.model_dump(),is_public=False)
    db.add(row);db.flush();audit(db,ctx,'inspection.create','inspection',row.id,new={'verdict':row.verdict})
    result=view(row,['id','listing_id','report_type','verdict','reviewer_kind','findings','evidence_refs','is_public','created_at'])
    idem_record(db,ctx,request,'inspection.create',payload,result)
    try:db.commit()
    except IntegrityError:
        db.rollback();fail(409,'동일한 실사 보고서 요청이 처리 중입니다. 조회 후 재시도하세요.')
    return result


@app.post('/api/v1/auth/agent-grants',status_code=201)
def create_agent_grant(data:GrantCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    token=secrets.token_urlsafe(48)
    grant=ServiceGrant(principal_user_id=ctx['user'].id,client_id='streamlit_test_agent',
                       token_hash=hashlib.sha256(token.encode()).hexdigest(),scopes=list(set(data.scopes)),
                       expires_at=now()+timedelta(hours=data.expires_in_hours))
    db.add(grant);db.flush()
    audit(db,ctx,'agent_grant.create','service_grant',grant.id,new={'scopes':grant.scopes})
    db.commit()
    # Display once; never store raw token in DB or logs.
    return {'id':grant.id,'token':token,'scopes':grant.scopes,'expires_at':grant.expires_at.isoformat(),
            'warning':'토큰은 1회만 표시됩니다. 에이전트 실행 환경의 비밀 저장소에 보관하세요.'}


@app.get('/api/v1/auth/agent-grants')
def get_agent_grants(db:Session=Depends(get_db),ctx=Depends(human)):
    rows=db.scalars(select(ServiceGrant).where(ServiceGrant.principal_user_id==ctx['user'].id).order_by(ServiceGrant.created_at.desc())).all()
    return {'items':[view(r,['id','client_id','scopes','expires_at','revoked_at','created_at']) for r in rows]}


@app.post('/api/v1/auth/agent-grants/{grant_id}/revoke')
def revoke_agent_grant(grant_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    row=db.get(ServiceGrant,grant_id)
    if not row or row.principal_user_id!=ctx['user'].id:fail(404,'연동 토큰이 없습니다.')
    row.revoked_at=now();audit(db,ctx,'agent_grant.revoke','service_grant',row.id)
    db.commit();return {'ok':True}



@app.get('/api/v1/agent/listings/{listing_id}/preparation-context')
def agent_listing_context(listing_id:str,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    """Seller's listing facts for an external agent. Never includes private source archives."""
    if ctx['kind']!='agent':fail(403,'에이전트 위임 토큰이 필요합니다.')
    allowed(ctx,'listing:read')
    listing=must_listing(db,listing_id)
    if listing.seller_id!=ctx['user'].id:fail(404,'매물이 없습니다.')
    # Only listing facts the seller entered. No private evidence or personal data.
    return {'listing':listing_card_view(db,listing),
            'authoritative_fields':['title','description','category','lifecycle_status','tech_stack',
                                    'included_assets','excluded_assets','known_defects','required_services'],
            'seller_claims_are_unverified':True,
            'code_execution_performed':False}


def action_scope(action_type:str, *, execute:bool) -> str:
    if action_type=='SUGGEST_LISTING_UPDATE':
        return 'listing:execute' if execute else 'listing:draft'
    if action_type=='REQUEST_SELLER_FIX':
        return 'handover:execute' if execute else 'handover:draft'
    return 'offer:execute' if execute else 'offer:draft'

@app.post('/api/v1/agent-actions',status_code=201)
def create_agent_action(data:AgentActionCreate,request:Request,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    if ctx['kind']!='agent':fail(403,'에이전트 토큰으로 제출해야 합니다.')
    allowed(ctx,action_scope(data.action_type,execute=False))
    future(data.expires_at)
    if len(json.dumps(data.proposed_payload,ensure_ascii=False).encode('utf-8'))>50000:
        fail(422,'작업 제안 데이터가 너무 큽니다.')
    if digest_payload(data.proposed_payload)!=data.payload_sha256:fail(422,'제안 내용 해시가 일치하지 않습니다.')
    if data.action_type not in ('SUBMIT_OFFER','COUNTER_OFFER','REQUEST_SELLER_FIX','SUGGEST_LISTING_UPDATE'):
        fail(422,'이 유형의 액션 실행은 다음 버전에서 지원됩니다.')
    # Retry of an already accepted request returns the exact original draft.
    # Authorization happens above, never bypass token scope checks.
    payload=data.model_dump(mode='json')
    replay=idem_replay(db,ctx,request,'agent_action.create',payload)
    if replay is not None:return replay
    if data.action_type=='SUBMIT_OFFER':
        try:parsed=OfferCreate.model_validate(data.proposed_payload)
        except ValidationError:fail(422,'매수 제안 형식이 올바르지 않습니다.')
        if parsed.listing_id!=data.resource_id:fail(422,'매물 ID가 다릅니다.')
        listing=must_listing(db,data.resource_id)
        if listing.status!='ACTIVE' or listing.seller_id==ctx['user'].id:fail(403,'자신의 매물 또는 비공개 매물에는 제안할 수 없습니다.')
    elif data.action_type=='SUGGEST_LISTING_UPDATE':
        try:
            parsed=AgentListingSuggestion.model_validate(data.proposed_payload)
        except ValidationError:
            fail(422,'매물 수정 제안은 제목·설명·매물 버전만 포함해야 합니다.')
        listing=must_listing(db,data.resource_id)
        if listing.seller_id!=ctx['user'].id:fail(404,'매물이 없습니다.')
        if listing.status in ('RESERVED','CLOSED','REMOVED'):
            fail(409,'거래 중이거나 종료된 매물은 수정할 수 없습니다.')
        version(listing, parsed.expected_version)
    elif data.action_type=='REQUEST_SELLER_FIX':
        from .stage2 import FixCreate
        try:parsed=FixCreate.model_validate(data.proposed_payload)
        except ValidationError:fail(422,'보완 요청 형식이 올바르지 않습니다.')
        tx=must_tx(db,data.resource_id,ctx)
        if tx.buyer_id!=ctx['user'].id or tx.status in ('CANCELLED','DEMO_COMPLETED'):
            fail(403,'인수인계 진행 중인 매수자만 보완 요청할 수 있습니다.')
    else:
        try:parsed=Counter.model_validate(data.proposed_payload)
        except ValidationError:fail(422,'역제안 형식이 올바르지 않습니다.')
        offer=must_offer(db,data.resource_id,ctx)
        if offer.proposed_by==ctx['user'].id:fail(403,'자신이 만든 제안을 역제안할 수 없습니다.')
    row=AgentAction(user_id=ctx['user'].id,requesting_agent_id='streamlit_test_agent',**data.model_dump())
    db.add(row);db.flush();audit(db,ctx,'agent_action.draft','agent_action',row.id,new={'status':row.status})
    from .stage2 import notify
    notify(db,ctx['user'].id,'AGENT_APPROVAL','에이전트가 작성한 작업 제안이 승인을 기다립니다.','agent_action',row.id)
    result=view(row,ACTION_FIELDS)
    idem_record(db,ctx,request,'agent_action.create',payload,result)
    try:db.commit()
    except IntegrityError:
        db.rollback();fail(409,'중복된 에이전트 초안 요청이 처리 중입니다. 조회 후 재시도하세요.')
    return result


@app.get('/api/v1/agent-actions')
def get_my_actions(db:Session=Depends(get_db),ctx=Depends(auth_context)):
    if ctx['kind']=='agent' and not ({'offer:draft','handover:draft','listing:draft'} & set(ctx['scopes'])):
        fail(403,'작업 조회 권한이 없습니다.')
    rows=db.scalars(select(AgentAction).where(AgentAction.user_id==ctx['user'].id).order_by(AgentAction.created_at.desc()).limit(100)).all()
    if ctx['kind']=='agent':
        rows=[r for r in rows if action_scope(r.action_type,execute=False) in ctx['scopes']]
    return {'items':[view(r,ACTION_FIELDS) for r in rows]}


@app.get('/api/v1/agent-actions/{action_id}')
def get_action(action_id:str,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    if ctx['kind']=='agent' and not ({'offer:draft','handover:draft','listing:draft'} & set(ctx['scopes'])):fail(403,'작업 조회 권한이 없습니다.')
    row=db.get(AgentAction,action_id)
    if not row or row.user_id!=ctx['user'].id:fail(404,'승인 요청이 없습니다.')
    if ctx['kind']=='agent':allowed(ctx,action_scope(row.action_type,execute=False))
    return view(row,ACTION_FIELDS)


@app.post('/api/v1/agent-actions/{action_id}/approve')
def approve_action(action_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    row=db.scalar(select(AgentAction).where(AgentAction.id==action_id).with_for_update())
    if not row or row.user_id!=ctx['user'].id:fail(404,'승인 요청이 없습니다.')
    if row.status!='PENDING_APPROVAL':fail(409,'승인 가능한 상태가 아닙니다.')
    if row.expires_at.replace(tzinfo=timezone.utc)<=now():fail(409,'승인 요청이 만료되었습니다.')
    if digest_payload(row.proposed_payload)!=row.payload_sha256:fail(409,'요청 내용이 변경됐습니다.')
    row.status='APPROVED';row.approved_at=now()
    audit(db,ctx,'agent_action.approve','agent_action',row.id,new={'status':'APPROVED'})
    db.commit();return view(row,ACTION_FIELDS)


@app.post('/api/v1/agent-actions/{action_id}/reject')
def reject_action(action_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    row=db.scalar(select(AgentAction).where(AgentAction.id==action_id).with_for_update())
    if not row or row.user_id!=ctx['user'].id:fail(404,'승인 요청이 없습니다.')
    if row.status!='PENDING_APPROVAL':fail(409,'거절 가능한 상태가 아닙니다.')
    row.status='REJECTED'
    audit(db,ctx,'agent_action.reject','agent_action',row.id,new={'status':'REJECTED'})
    db.commit();return view(row,ACTION_FIELDS)


@app.post('/api/v1/agent-actions/{action_id}/execute')
def execute_action(action_id:str,request:Request,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    row=db.scalar(select(AgentAction).where(AgentAction.id==action_id).with_for_update())
    if not row or row.user_id!=ctx['user'].id:fail(404,'승인 요청이 없습니다.')
    # Human users can finalize seller copy proposals; other writes remain delegated-only.
    if ctx['kind']=='agent':
        allowed(ctx,action_scope(row.action_type,execute=True))
    elif row.action_type!='SUGGEST_LISTING_UPDATE':
        fail(403,'이 작업은 위임된 에이전트만 실행할 수 있습니다.')
    replay=idem_replay(db,ctx,request,f'agent_action.execute:{action_id}',{'action_id':action_id})
    if replay is not None:return replay
    if row.status!='APPROVED' or not row.approved_at or row.expires_at.replace(tzinfo=timezone.utc)<=now():
        fail(409,'승인되지 않았거나 만료된 작업입니다.')
    if row.action_type=='SUGGEST_LISTING_UPDATE':
        listing_for_mode=must_listing(db,row.resource_id)
        if not listing_for_mode.is_demo and agent_write_mode()!='live':
            fail(403,'비시연 매물의 에이전트 수정은 아직 지원하지 않습니다.')
        if ctx['kind']=='agent':require_agent_demo_write(row.action_type,listing_for_mode.is_demo)
    elif ctx['kind']=='agent':
        if row.action_type=='SUBMIT_OFFER':
            target_is_demo=must_listing(db,row.resource_id).is_demo
        elif row.action_type=='COUNTER_OFFER':
            offer_for_mode=must_offer(db,row.resource_id,ctx)
            target_is_demo=must_listing(db,offer_for_mode.listing_id).is_demo
        else:
            tx_for_mode=must_tx(db,row.resource_id,ctx)
            target_is_demo=tx_for_mode.is_demo and must_listing(db,tx_for_mode.listing_id).is_demo
        require_agent_demo_write(row.action_type,target_is_demo)
    if digest_payload(row.proposed_payload)!=row.payload_sha256:fail(409,'내용 해시 불일치')
    if row.action_type=='SUGGEST_LISTING_UPDATE':
        body=AgentListingSuggestion.model_validate(row.proposed_payload)
        listing=db.scalar(select(Listing).where(Listing.id==row.resource_id).with_for_update())
        if not listing or listing.status=='REMOVED' or listing.seller_id!=ctx['user'].id:
            fail(404,'매물이 없습니다.')
        version(listing,body.expected_version)
        if listing.status in ('RESERVED','CLOSED'):
            fail(409,'거래 중이거나 종료된 매물은 수정할 수 없습니다.')
        before={'status':listing.status,'version':listing.version}
        if body.title is not None:listing.title=body.title
        if body.description is not None:listing.description=body.description
        if listing.status=='ACTIVE':listing.status='PENDING_REVIEW'
        listing.version+=1
        audit(db,ctx,'listing.agent_update_approved','listing',listing.id,old=before,
              new={'status':listing.status,'version':listing.version},demo=listing.is_demo)
        result=listing
    elif row.action_type=='SUBMIT_OFFER':
        body=OfferCreate.model_validate(row.proposed_payload)
        if body.listing_id!=row.resource_id:fail(409,'리소스가 변경되었습니다.')
        result=do_offer(db,ctx,body)
    elif row.action_type=='COUNTER_OFFER':
        body=Counter.model_validate(row.proposed_payload)
        offer=must_offer(db,row.resource_id,ctx,lock=True)
        result=do_counter(db,ctx,offer,body)
    elif row.action_type=='REQUEST_SELLER_FIX':
        from .stage2 import FixCreate, notify
        from .models import FixRequest
        body=FixCreate.model_validate(row.proposed_payload)
        tx=must_tx(db,row.resource_id,ctx,lock=True)
        if tx.buyer_id!=ctx['user'].id or tx.status in ('CANCELLED','DEMO_COMPLETED'):fail(409,'보완 요청이 불가능한 상태입니다.')
        result=FixRequest(transaction_id=tx.id,raised_by_user_id=ctx['user'].id,
                          seller_id=tx.seller_id,description=body.description)
        db.add(result);db.flush()
        notify(db,tx.seller_id,'FIX_REQUEST','에이전트가 준비한 보완 요청을 매수자가 승인했습니다.','transaction',tx.id)
    else:fail(422,'지원하지 않는 액션입니다.')
    row.status='EXECUTED';row.executed_at=now();row.result_resource_id=result.id
    audit(db,ctx,'agent_action.execute','agent_action',row.id,new={'result_resource_id':result.id})
    response=view(row,ACTION_FIELDS)
    idem_record(db,ctx,request,f'agent_action.execute:{action_id}',{'action_id':action_id},response)
    try:db.commit()
    except IntegrityError:
        db.rollback();fail(409,'중복 실행 요청이 처리 중입니다. 해당 작업 상태를 조회하세요.')
    return response


@app.post('/api/v1/reports',status_code=201)
def report_listing(data:ReportCreate,db:Session=Depends(get_db),ctx=Depends(human)):
    must_listing(db,data.listing_id)
    row=ModerationReport(listing_id=data.listing_id,reported_by=ctx['user'].id,
                         reason_code=data.reason_code,description=data.description)
    db.add(row);db.flush();audit(db,ctx,'moderation.report','moderation_report',row.id)
    db.commit();return {'id':row.id,'status':row.status}


def admin_only(ctx):
    only_human(ctx)
    if ctx['user'].role!='ADMIN':fail(403,'관리자 권한이 필요합니다.')


@app.get('/api/v1/admin/listings')
def admin_listings(db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    return {'items':[listing_card_view(db,x) for x in db.scalars(select(Listing).order_by(Listing.created_at.desc()).limit(300)).all()]}


@app.post('/api/v1/admin/listings/{listing_id}/moderate')
def moderate(listing_id:str,data:dict,db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    status=data.get('status');reason=str(data.get('reason',''))[:1000]
    if status not in ('ACTIVE','PAUSED','REMOVED'):fail(422,'허용되지 않은 상태입니다.')
    listing=db.scalar(select(Listing).where(Listing.id==listing_id).with_for_update())
    if not listing:fail(404,'매물이 없습니다.')
    if status=='ACTIVE':
        if listing.status not in ('PENDING_REVIEW','PAUSED'):fail(409,'검토 중인 매물만 공개할 수 있습니다.')
        if not listing.rights_attested:fail(409,'권리자 확인 진술이 없습니다.')
        if not listing.is_demo:
            seller=db.get(User,listing.seller_id)
            if not seller.email_verified_at:fail(409,'이메일 미인증 계정입니다.')
    if status=='REMOVED' and len(reason)<5:fail(422,'삭제 사유는 5글자 이상이어야 합니다.')
    old=listing.status;listing.status=status;listing.version+=1
    from .stage2 import notify
    notify(db,listing.seller_id,'LISTING_MODERATED',
           '프로젝트 검토가 완료되었습니다.' if status=='ACTIVE' else '프로젝트 게시 상태가 변경되었습니다.',
           'listing',listing.id)
    audit(db,ctx,'admin.listing.moderate','listing',listing.id,{'status':old},{'status':status,'reason':reason},listing.is_demo)
    db.commit();return listing_card_view(db,listing)


@app.get('/api/v1/admin/reports')
def admin_reports(db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    return {'items':[view(r,['id','listing_id','reported_by','reason_code','description','status','created_at']) for r in db.scalars(select(ModerationReport).order_by(ModerationReport.created_at.desc()).limit(200)).all()]}


@app.get('/api/v1/admin/audit-events')
def admin_audit(db:Session=Depends(get_db),ctx=Depends(human)):
    admin_only(ctx)
    rows=db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(150)).all()
    return {'items':[view(x,['id','actor_user_id','actor_type','action','resource_type','resource_id','old_state','new_state','is_demo','created_at']) for x in rows]}


@app.get('/api/v1/listings/{listing_id}/assets')
def get_listing_assets(listing_id:str,db:Session=Depends(get_db),ctx=Depends(auth_context)):
    row=must_listing(db,listing_id)
    if row.seller_id!=ctx['user'].id and ctx['user'].role!='ADMIN':fail(404,'비공개 자료를 볼 수 없습니다.')
    if ctx['kind']=='agent':fail(403,'에이전트는 원본 첨부 접근 권한이 없습니다.')
    assets=db.scalars(select(ListingAsset).where(ListingAsset.listing_id==listing_id)).all()
    return {'items':[view(a,['id','listing_id','asset_type','file_name','size_bytes','checksum_sha256','visibility','upload_status','malware_scan_status','created_at']) for a in assets]}


@app.post('/api/v1/listings/{listing_id}/asset-upload-intents')
def upload_intent(listing_id:str,db:Session=Depends(get_db),ctx=Depends(human)):
    row=must_listing(db,listing_id)
    if row.seller_id!=ctx['user'].id:fail(404,'매물이 없습니다.')
    fail(501,'외부 비공개 객체 저장소 연동 전입니다. 안전한 업로드 링크를 발급하지 않습니다.')


@app.get('/api/v1/system/capabilities')
def capabilities():
    return {'phase':'MVP_P0','payments':False,'escrow':False,'automatic_ip_transfer':False,
            'private_asset_upload':True,'private_asset_download':True,'automated_code_execution':False,
            'agent_draft_offer':True,'agent_human_approval':True,'simulation_only_transactions':True,'standalone_agent_server_required':False, 'public_malware_scan':False,'static_zip_inspection':True,'agent_fix_request_approval':True,'platform_llm_calls':False,'agent_listing_update_proposal':True,'seller_consented_agent_asset_inspection':True,'fix_request_buyer_confirmation':True,
            'agent_write_mode':agent_write_mode(),'agent_live_writes':False,
            'agent_demo_write_requires_explicit_enable':True,
            'agent_inspection_asset_discovery':True,'buyer_consented_inspection_reports':True,
            'agent_mutations_idempotency':True, 'github_app_import':True,
            'public_github_url_import':True,'zip_prelisting_analysis':True,'showcase_media':True,'takeover_readiness_checklist':True,'always_on_takeover_report':True,'github_ci_observation':True,'account_erasure':True,'listing_inquiries':True,'email_outbox':True,'demo_agreement_snapshots':True,'bilateral_demo_cancellation':True,'admin_dispute_review':True,'deal_timeline':True,'post_handover_roadmap':True,'roadmap_preview':True,'buyer_roadmap_progress':True,'legal_e_signature':False,'real_settlement':False,
            'import_source_snapshot_private':True, 'deterministic_only':True,'pagination':'offset_string_v1',
            'api_base_path':'/api/v1','nullable_fields_follow_openapi':True}


# Stage 2 endpoints are included before the SPA fallback to avoid route shadowing.
from .stage2 import router as stage2_router
app.include_router(stage2_router)
from .project_imports import router as project_imports_router
app.include_router(project_imports_router)
from .marketplace_v07 import router as marketplace_v07_router
app.include_router(marketplace_v07_router)
from .deal_management import router as deal_router
app.include_router(deal_router)
from .development_roadmap import router as development_roadmap_router
app.include_router(development_roadmap_router)
from .v012_support import router as integrated_workspace_router
app.include_router(integrated_workspace_router)
from .privacy import router as privacy_router
app.include_router(privacy_router)

# In a Replit manual deployment, build frontend/dist first. FastAPI serves SPA under the same origin.
frontend_dir = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if os.getenv('VERCEL') != '1' and frontend_dir.exists():
    from fastapi.responses import FileResponse
    app.mount('/assets', StaticFiles(directory=str(frontend_dir / 'assets')), name='frontend-assets')
    @app.get('/{path:path}', include_in_schema=False)
    def spa(path: str):
        if path.startswith('api/') or path.startswith('assets/') or path.startswith('docs'):
            fail(404,'찾을 수 없습니다.')
        return FileResponse(str(frontend_dir / 'index.html'))
