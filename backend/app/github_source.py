"""GitHub App user OAuth and fixed-host, bounded, read-only REST API client.

No user-defined fetch URLs, no shell/git commands, no leaked OAuth credentials.
"""
import os
import re
from base64 import urlsafe_b64encode
from datetime import timedelta, timezone
from hashlib import sha256
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import GithubConnection, now
from .security import JWT_SECRET

HEADERS = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
           'User-Agent': 'ProjectAgain-ReadOnlyImport'}
API_ROOT = 'https://api.github.com'
OAUTH_ROOT = 'https://github.com'
REPO_RE = re.compile(r'^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')
MAX_ARCHIVE = int(os.getenv('ASSET_MAX_BYTES', str(10 * 1024 * 1024)))


def github_configured():
    return all(os.getenv(v) for v in ('GITHUB_CLIENT_ID', 'GITHUB_CLIENT_SECRET', 'GITHUB_CALLBACK_URL')) and (
        os.getenv('APP_ENV') != 'production' or bool(os.getenv('GITHUB_TOKEN_ENCRYPTION_KEY')))


def oauth_settings():
    if not github_configured():
        raise HTTPException(503, 'GitHub 연결 설정이 완료되지 않았습니다. 공개 저장소는 주소로 분석할 수 있습니다.')
    callback = os.environ['GITHUB_CALLBACK_URL']
    parsed = urlparse(callback)
    if parsed.scheme not in ('https', 'http') or parsed.netloc == '' or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(503, 'GitHub 연결 주소 설정이 올바르지 않습니다.')
    if parsed.scheme != 'https' and os.getenv('APP_ENV') == 'production':
        raise HTTPException(503, '운영 GitHub 콜백에는 HTTPS가 필요합니다.')
    if parsed.path != '/api/v1/github/callback':
        raise HTTPException(503, 'GitHub 콜백 경로는 /api/v1/github/callback 이어야 합니다.')
    return callback


def fernet():
    key = os.getenv('GITHUB_TOKEN_ENCRYPTION_KEY') or (JWT_SECRET if os.getenv('APP_ENV') != 'production' else '')
    if not key: raise HTTPException(503, 'GitHub 연결 암호화 키가 설정되지 않았습니다.')
    return Fernet(urlsafe_b64encode(sha256(key.encode()).digest()))


def encrypt(plain):
    return fernet().encrypt(plain.encode()).decode()


def decrypt(cipher):
    try: return fernet().decrypt(cipher.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise HTTPException(503, 'GitHub 연결 정보를 읽지 못했습니다. 계정을 다시 연결하세요.') from exc


def oauth_url(user_id: str) -> str:
    callback = oauth_settings()
    state = jwt.encode({'sub': user_id, 'purpose': 'github-oauth',
                        'exp': now() + timedelta(minutes=10)}, JWT_SECRET, algorithm='HS256')
    return OAUTH_ROOT + '/login/oauth/authorize?' + urlencode({
        'client_id': os.environ['GITHUB_CLIENT_ID'], 'redirect_uri': callback, 'state': state})


def verify_oauth_state(state: str, user_id: str):
    try:
        data = jwt.decode(state, JWT_SECRET, algorithms=['HS256'])
    except jwt.PyJWTError as exc:
        raise HTTPException(403, 'GitHub 인증 요청이 만료되었거나 올바르지 않습니다.') from exc
    if data.get('sub') != user_id or data.get('purpose') != 'github-oauth':
        raise HTTPException(403, '다른 사용자의 GitHub 인증 요청입니다.')


def exchange_code(code: str, *, refresh=False):
    oauth_settings()
    payload = {'client_id': os.environ['GITHUB_CLIENT_ID'],
               'client_secret': os.environ['GITHUB_CLIENT_SECRET']}
    if refresh:
        payload.update({'grant_type': 'refresh_token', 'refresh_token': code})
    else:
        payload.update({'code': code, 'redirect_uri': os.environ['GITHUB_CALLBACK_URL']})
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            r = client.post(OAUTH_ROOT + '/login/oauth/access_token', data=payload,
                            headers={'Accept': 'application/json', 'User-Agent': HEADERS['User-Agent']})
            r.raise_for_status()
            result = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, 'GitHub 인증 서버에 연결할 수 없습니다.') from exc
    if result.get('error') or not result.get('access_token'):
        raise HTTPException(403, 'GitHub 인증이 거절되었거나 만료되었습니다. 다시 연결하세요.')
    return result


def _expiry(seconds):
    try: return now() + timedelta(seconds=max(1, int(seconds)))
    except (ValueError, TypeError): return None


def save_connection(db: Session, user_id: str, result: dict, account: dict):
    row = db.get(GithubConnection, user_id)
    if row is None:
        row = GithubConnection(user_id=user_id, github_user_id=int(account['id']), github_login=account['login'],
                               access_token_ciphertext='', refresh_token_ciphertext=None)
        db.add(row)
    row.github_user_id = int(account['id'])
    row.github_login = str(account['login'])[:120]
    row.access_token_ciphertext = encrypt(result['access_token'])
    row.access_expires_at = _expiry(result.get('expires_in'))
    if result.get('refresh_token'):
        row.refresh_token_ciphertext = encrypt(result['refresh_token'])
        row.refresh_expires_at = _expiry(result.get('refresh_token_expires_in'))
    row.updated_at = now()
    db.commit()
    return row


def user_token(db: Session, user_id: str):
    row = db.get(GithubConnection, user_id)
    if not row: raise HTTPException(409, '먼저 GitHub 계정을 연결하세요.')
    if row.access_expires_at:
        expire = row.access_expires_at
        if expire.tzinfo is None: expire = expire.replace(tzinfo=timezone.utc)
        if expire <= now() + timedelta(minutes=2):
            if not row.refresh_token_ciphertext:
                raise HTTPException(409, 'GitHub 연결이 만료되었습니다. 다시 연결하세요.')
            refreshed = exchange_code(decrypt(row.refresh_token_ciphertext), refresh=True)
            save_connection(db, user_id, refreshed, {'id':row.github_user_id, 'login':row.github_login})
            row = db.get(GithubConnection, user_id)
    return decrypt(row.access_token_ciphertext)


def get_api(path: str, token: str | None = None, params: dict | None = None):
    # Only caller-owned, hard-coded paths are passed in; never a full remote URL.
    if not path.startswith('/') or '?' in path or '#' in path or '//' in path:
        raise HTTPException(422, 'GitHub API 경로가 올바르지 않습니다.')
    headers = {**HEADERS}
    if token: headers['Authorization'] = 'Bearer ' + token
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            r = client.get(API_ROOT + path, params=params, headers=headers)
            if r.status_code in (401, 403):
                raise HTTPException(403, 'GitHub 접근 권한 또는 API 요청 제한을 확인하세요. 다시 연결해야 할 수 있습니다.')
            if r.status_code == 404: raise HTTPException(404, 'GitHub 저장소를 찾을 수 없거나 접근 권한이 없습니다.')
            r.raise_for_status()
            return r.json()
    except HTTPException: raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, 'GitHub API 조회에 실패했습니다.') from exc


def parse_repo(value: str):
    raw = value.strip().rstrip('/')
    if raw.startswith('https://'):
        parsed = urlparse(raw)
        if (parsed.scheme != 'https' or parsed.netloc.lower() not in ('github.com','www.github.com')
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise HTTPException(422, 'github.com 저장소 주소만 입력할 수 있습니다.')
        raw = parsed.path.strip('/')
    elif '://' in raw or '/' not in raw:
        raise HTTPException(422, 'GitHub 저장소 주소 또는 owner/repo를 입력하세요.')
    if raw.endswith('.git'): raw = raw[:-4]
    if not REPO_RE.fullmatch(raw) or '..' in raw or raw.split('/')[0].startswith('.'):
        raise HTTPException(422, 'GitHub 저장소 주소 형식이 올바르지 않습니다.')
    return raw


def get_installations(token: str):
    result = get_api('/user/installations', token, {'per_page': 100})
    return [int(i['id']) for i in result.get('installations', [])[:100]]


def repos_for_installation(token: str, installation_id: int):
    items=[]
    for page in range(1, 6):
        data = get_api(f'/user/installations/{installation_id}/repositories', token,
                       {'per_page': 100, 'page': page})
        batch = data.get('repositories', [])
        items.extend(batch)
        if len(batch) < 100: break
    return items


def authorized_repo(token: str, install_id: int, name: str):
    if install_id not in get_installations(token):
        raise HTTPException(403, '이 GitHub 설치에 접근할 권한이 없습니다.')
    for repo in repos_for_installation(token, install_id):
        if repo.get('full_name', '').lower() == name.lower():
            return repo
    raise HTTPException(403, '선택한 저장소에 대한 GitHub 접근 권한이 없습니다.')


def download_archive(full_name: str, sha: str, token: str | None):
    """Bounded stream from exact GitHub API or its codeload redirect; no arbitrary URL fetching."""
    if not REPO_RE.fullmatch(full_name) or not SHA_RE.fullmatch(sha):
        raise HTTPException(422, 'GitHub 저장소 또는 커밋 정보가 올바르지 않습니다.')
    url = API_ROOT + f'/repos/{full_name}/zipball/{sha}'
    headers = {**HEADERS}
    if token: headers['Authorization'] = 'Bearer ' + token

    def read_limited(response):
        chunks=[]; size=0
        for chunk in response.iter_bytes(1024 * 256):
            size += len(chunk)
            if size > MAX_ARCHIVE:
                raise HTTPException(413, 'GitHub 프로젝트가 허용 크기를 초과했습니다. ZIP을 정리해 다시 시도하세요.')
            chunks.append(chunk)
        return b''.join(chunks)

    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=8), follow_redirects=False) as client:
            with client.stream('GET', url, headers=headers) as first:
                if first.status_code in (401,403,404):
                    raise HTTPException(403, 'GitHub 소스 다운로드 권한 또는 요청 제한을 확인하세요.')
                if first.status_code not in (301,302,303,307,308):
                    first.raise_for_status()
                    return read_limited(first)
                location = first.headers.get('location','')
            parsed = urlparse(location)
            if (parsed.scheme != 'https' or parsed.hostname != 'codeload.github.com' or
                    parsed.port or parsed.username or parsed.password or parsed.fragment):
                raise HTTPException(502, '허용되지 않은 GitHub 다운로드 경로입니다.')
            # Never forward Authorization to another host: GitHub codeload links are temporary.
            with client.stream('GET', location, headers={'User-Agent':HEADERS['User-Agent']}) as response:
                response.raise_for_status()
                return read_limited(response)
    except HTTPException: raise
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'GitHub 소스 다운로드 중 오류가 발생했습니다.') from exc
