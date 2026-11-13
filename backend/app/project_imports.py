"""ProjectAgain source import API: GitHub App or user ZIP, static analysis and private staging."""
import hashlib
import os
import re
from datetime import timedelta, timezone
from uuid import uuid4
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .github_source import (github_configured, oauth_url, verify_oauth_state, exchange_code,
                            get_api, get_installations, repos_for_installation, authorized_repo,
                            parse_repo, download_archive, user_token, save_connection)
from .models import GithubConnection, ProjectImport, Listing, ListingAsset, ListingSourceSummary, now
from .private_storage import upload as store_upload, delete as store_delete, download as store_download, presign_put, object_size, StorageUnavailable
from .static_screen import screen, RejectedFile, MAX_FILE
from .malware_scan import scan_bytes
from .project_analyzer import analyze_archive, public_analysis
from .security import human

router = APIRouter(prefix='/api/v1', tags=['Project imports'])
MAX_STAGED = 3
STAGING_HOURS = 2


class GithubSourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repository: str = Field(min_length=3, max_length=280)
    installation_id: int | None = Field(default=None, ge=1)


def _public_response(row: ProjectImport):
    return {'id': row.id, 'source_type': row.source_type, 'source_label': row.source_label,
            'source_private': row.source_private, 'revision': row.revision_sha[:12] if row.revision_sha else None,
            'checksum_sha256': row.checksum_sha256, 'size_bytes': row.size_bytes,
            'expires_at': row.expires_at.isoformat(), 'analysis': row.analysis,
            'asset_review_status': 'QUARANTINED', 'malware_scan_status': row.malware_status}


def _stage(db, user_id, *, blob, filename, source_type, source_label, is_private, revision=None, ci_evidence=None):
    existing = db.scalar(select(func.count()).select_from(ProjectImport).where(
        ProjectImport.user_id == user_id, ProjectImport.status == 'STAGED',
        ProjectImport.expires_at > now())) or 0
    if existing >= MAX_STAGED:
        raise HTTPException(429, '미완료 분석이 최대 3개입니다. 기존 분석으로 등록하거나 2시간 후 다시 시도하세요.')
    try: screen(filename, blob)
    except RejectedFile as exc: raise HTTPException(422, str(exc)) from exc
    result, _ = scan_bytes(blob)
    if result == 'INFECTED':
        raise HTTPException(422, '악성코드가 발견되어 가져오기를 차단했습니다.')
    if result == 'ERROR' and os.getenv('APP_ENV') == 'production':
        raise HTTPException(503, '파일 검사기 오류로 소스를 보관하지 않았습니다.')
    try: analysis = analyze_archive(blob, source_label=source_label.split('/')[-1])
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(422, 'ZIP 정적 분석에 실패했습니다.') from exc
    analysis['ci_evidence'] = ci_evidence or {'status':'NOT_AVAILABLE','origin':'GITHUB_ACTIONS','runs_checked':0,'observed_sha_match':False}
    object_key = f'private/imports/{uuid4().hex}'
    try: store_upload(object_key, blob)
    except (StorageUnavailable, OSError) as exc:
        raise HTTPException(503, '비공개 소스 보관소에 접근하지 못했습니다.') from exc
    row = ProjectImport(user_id=user_id, source_type=source_type,
                        source_label=source_label[:220], source_private=is_private,
                        filename=filename, revision_sha=revision,
                        object_key=object_key, checksum_sha256=hashlib.sha256(blob).hexdigest(),
                        size_bytes=len(blob), malware_status=result,
                        analysis=analysis, expires_at=now() + timedelta(hours=STAGING_HOURS))
    try:
        db.add(row); db.commit(); db.refresh(row)
    except Exception:
        db.rollback()
        try: store_delete(object_key)
        except Exception: pass
        raise
    return _public_response(row)


@router.get('/github/status')
def status(db:Session=Depends(get_db), ctx=Depends(human)):
    row = db.get(GithubConnection, ctx['user'].id)
    app_slug=os.getenv('GITHUB_APP_SLUG','')
    install_url=('https://github.com/apps/'+app_slug+'/installations/new'
                 if re.fullmatch(r'[a-zA-Z0-9-]{1,100}',app_slug) else None)
    return {'install_url':install_url, 'configured': bool(github_configured()), 'connected': bool(row),
            'github_login': row.github_login if row else None,
            'public_url_import': True, 'private_repo_import': bool(github_configured())}


@router.post('/github/connect')
def connect(ctx=Depends(human)):
    return {'authorize_url': oauth_url(ctx['user'].id)}


@router.get('/github/callback', include_in_schema=True)
def callback(code: str = '', state: str = '', error: str = '',
             db:Session=Depends(get_db), ctx=Depends(human)):
    verify_oauth_state(state, ctx['user'].id)
    if error or not code: return RedirectResponse('/sell/new?github=cancelled', status_code=303)
    result = exchange_code(code)
    account = get_api('/user', result['access_token'])
    save_connection(db, ctx['user'].id, result, account)
    return RedirectResponse('/sell/new?github=connected', status_code=303)


@router.delete('/github/connection')
def disconnect(db:Session=Depends(get_db), ctx=Depends(human)):
    row = db.get(GithubConnection, ctx['user'].id)
    if row: db.delete(row); db.commit()
    return {'connected': False}


@router.get('/github/repositories')
def repositories(db:Session=Depends(get_db), ctx=Depends(human)):
    token = user_token(db, ctx['user'].id)
    installs = get_installations(token)
    items = []
    for ins in installs[:10]:
        for repo in repos_for_installation(token, ins)[:500]:
            items.append({'full_name': repo['full_name'], 'private': bool(repo['private']),
                          'installation_id': ins, 'description': (repo.get('description') or '')[:250]})
    return {'items': items[:500], 'truncated': len(installs)>10 or len(items)>500}


@router.post('/listing-imports/github', status_code=201)
def import_github(data:GithubSourceInput, db:Session=Depends(get_db), ctx=Depends(human)):
    full_name = parse_repo(data.repository)
    token = None
    if data.installation_id is not None:
        token = user_token(db, ctx['user'].id)
        authorized_repo(token, data.installation_id, full_name)
    repo = get_api('/repos/' + full_name, token)
    if not token and repo.get('private'):
        raise HTTPException(403, '비공개 저장소는 GitHub 연결 후 선택해 주세요.')
    if repo.get('full_name', '').lower() != full_name.lower():
        raise HTTPException(422, '요청한 저장소와 GitHub의 응답이 다릅니다.')
    if repo.get('size', 0) > 50000:
        raise HTTPException(413, '규모가 큰 저장소입니다. 필요 파일만 ZIP으로 제출하세요.')
    default_branch = repo.get('default_branch')
    if not default_branch or len(default_branch) > 200:
        raise HTTPException(422, '저장소에 기본 브랜치가 없거나 비정상적입니다.')
    commit = get_api('/repos/' + full_name + '/commits/' + quote(default_branch, safe=''), token)
    sha = commit.get('sha', '')
    if len(sha) != 40 or not all(c in '0123456789abcdef' for c in sha):
        raise HTTPException(502, 'GitHub 커밋 정보를 확인하지 못했습니다.')
    blob = download_archive(full_name, sha, token)
    filename = f'github-{full_name.split("/")[-1][:75]}-{sha[:12]}.zip'
    from .github_ci import observe_ci
    ci = observe_ci(repo['full_name'], sha, token)
    return _stage(db, ctx['user'].id, blob=blob, filename=filename, source_type='GITHUB',
                  source_label=repo['full_name'], is_private=bool(repo.get('private')), revision=sha, ci_evidence=ci)


class DirectZipIntent(BaseModel):
    filename: str = Field(min_length=5, max_length=220)
    size_bytes: int = Field(ge=1, le=MAX_FILE)
    checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class DirectZipComplete(BaseModel):
    token: str


@router.post('/listing-imports/zip/direct-intent')
def zip_direct_intent(data: DirectZipIntent, ctx=Depends(human)):
    """Short-lived, user-bound upload authorization. The object is quarantined."""
    import jwt
    from .security import JWT_SECRET
    if os.getenv('PRIVATE_STORAGE_BACKEND') != 's3':
        raise HTTPException(503, '직접 업로드 저장소가 설정되지 않았습니다.')
    filename = data.filename.replace('\\', '/').split('/')[-1]
    if filename != data.filename or not filename.lower().endswith('.zip'):
        raise HTTPException(422, '올바른 ZIP 파일 이름이 필요합니다.')
    key = f'private/pending-imports/{ctx["user"].id}/{uuid4().hex}'
    claims = {'sub': ctx['user'].id, 'key': key, 'filename': filename,
              'size': data.size_bytes, 'sha256': data.checksum_sha256,
              'purpose': 'zip-direct', 'exp': now() + timedelta(minutes=10)}
    token = jwt.encode(claims, JWT_SECRET, algorithm='HS256')
    try:
        url = presign_put(key, expires=300)
    except Exception as exc:
        raise HTTPException(503, '업로드 주소 발급 실패') from exc
    return {'upload_url': url, 'token': token, 'method': 'PUT',
            'headers': {'Content-Type': 'application/zip'}, 'expires_in_seconds': 300}


@router.post('/listing-imports/zip/direct-complete', status_code=201)
def zip_direct_complete(data: DirectZipComplete, db:Session=Depends(get_db), ctx=Depends(human)):
    import jwt
    from .security import JWT_SECRET
    try:
        claims = jwt.decode(data.token, JWT_SECRET, algorithms=['HS256'])
    except jwt.PyJWTError as exc:
        raise HTTPException(403, '업로드 승인이 만료되었거나 올바르지 않습니다.') from exc
    if claims.get('purpose') != 'zip-direct' or claims.get('sub') != ctx['user'].id:
        raise HTTPException(403, '업로드 소유자가 일치하지 않습니다.')
    key = claims['key']
    if not key.startswith(f'private/pending-imports/{ctx["user"].id}/'):
        raise HTTPException(403, '허용되지 않은 저장소 경로입니다.')
    try:
        size = object_size(key)
        if size != claims['size'] or size > MAX_FILE:
            raise HTTPException(422, '업로드 파일 크기가 승인 정보와 다릅니다.')
        blob = store_download(key)
        if hashlib.sha256(blob).hexdigest() != claims['sha256']:
            raise HTTPException(422, '업로드 파일 체크섬이 일치하지 않습니다.')
        return _stage(db, ctx['user'].id, blob=blob, filename=claims['filename'],
                      source_type='ZIP', source_label=claims['filename'][:220], is_private=True)
    except StorageUnavailable as exc:
        raise HTTPException(503, '비공개 파일 확인 실패') from exc
    finally:
        try: store_delete(key)
        except Exception: pass  # Expired orphan objects require bucket lifecycle cleanup.


@router.post('/listing-imports/zip', status_code=201)
async def import_zip(file: UploadFile = File(...), db:Session=Depends(get_db), ctx=Depends(human)):
    filename = (file.filename or '').replace('\\','/').split('/')[-1]
    if not filename.lower().endswith('.zip'):
        raise HTTPException(422, '소스 자동 분석에는 ZIP 파일만 사용할 수 있습니다.')
    blob = await file.read(MAX_FILE + 1)
    return _stage(db, ctx['user'].id, blob=blob, filename=filename,
                  source_type='ZIP', source_label=filename[:220], is_private=True)


@router.get('/listing-imports/{import_id}')
def get_import(import_id:str, db:Session=Depends(get_db), ctx=Depends(human)):
    row = db.get(ProjectImport, import_id)
    if not row or row.user_id != ctx['user'].id:
        raise HTTPException(404, '분석 자료를 찾을 수 없습니다.')
    if row.status != 'STAGED' or _utc(row.expires_at) <= now():
        raise HTTPException(410, '이 분석은 만료되었거나 등록에 사용되었습니다.')
    return _public_response(row)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def attach_import(db:Session, seller_id:str, listing):
    """Called from the listing create transaction. Never reuses another seller's source."""
    row = db.scalar(select(ProjectImport).where(ProjectImport.id == listing.import_id).with_for_update())
    if not row or row.user_id != seller_id or row.status != 'STAGED' or row.listing_id or _utc(row.expires_at) <= now():
        raise HTTPException(409, '프로젝트 분석이 만료되었거나 이미 사용되었습니다. 다시 분석해 주세요.')
    total = db.scalar(select(func.coalesce(func.sum(ListingAsset.size_bytes), 0))
                      .select_from(ListingAsset).join(Listing, Listing.id == ListingAsset.listing_id)
                      .where(Listing.seller_id == seller_id)) or 0
    if total + row.size_bytes > 100 * 1024 * 1024:
        raise HTTPException(429, '계정당 소스 파일 최대 용량 100MB를 초과합니다.')
    asset = ListingAsset(listing_id=listing.id, asset_type='SOURCE_ARCHIVE',
                         file_name=row.filename, private_object_key=row.object_key,
                         content_type='application/octet-stream', size_bytes=row.size_bytes,
                         checksum_sha256=row.checksum_sha256, visibility='PRIVATE_SELLER',
                         upload_status='QUARANTINED', malware_scan_status=row.malware_status,
                         uploaded_by=seller_id)
    summary = ListingSourceSummary(listing_id=listing.id, import_id=row.id,
                                   source_type=row.source_type,
                                   analysis=public_analysis(row.analysis))
    db.add(asset); db.add(summary)
    row.listing_id = listing.id
    row.status = 'ATTACHED'
    return row
