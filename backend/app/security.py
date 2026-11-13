import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, ServiceGrant, now

APP_ENV = os.getenv('APP_ENV', 'development')
JWT_SECRET = os.getenv('JWT_SECRET', '')
if APP_ENV == 'production' and len(JWT_SECRET) < 40:
    raise RuntimeError('Production requires an explicitly configured random JWT_SECRET of at least 40 characters')
if not JWT_SECRET:
    # Never embed a well-known signing key, even in a public development preview.
    # Sessions will be invalidated when this process restarts. Configure Replit Secrets.
    JWT_SECRET = secrets.token_urlsafe(48)
COOKIE_SECURE = APP_ENV == 'production'
COOKIE_NAME = 'market_session'


def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 600_000
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f'pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(hashed).decode()}'


def verify_password(password, stored):
    try:
        name, n, salt, digest = stored.split('$')
        if name != 'pbkdf2_sha256': return False
        result = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), base64.urlsafe_b64decode(salt), int(n))
        return hmac.compare_digest(base64.urlsafe_b64encode(result).decode(), digest)
    except (ValueError, TypeError):
        return False


def token_for(user):
    csrf = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    encoded = jwt.encode({'sub': user.id, 'csrf': csrf, 'exp': expires, 'kind': 'session', 'av': user.auth_version}, JWT_SECRET, algorithm='HS256')
    return encoded, csrf, expires


def auth_context(request: Request, db: Session = Depends(get_db)):
    raw = request.headers.get('authorization', '')
    if raw.startswith('Bearer '):
        token = raw[7:]
        grant = db.scalar(select(ServiceGrant).where(ServiceGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        if not grant or grant.revoked_at or grant.expires_at.replace(tzinfo=timezone.utc) <= now():
            raise HTTPException(401, '유효하지 않은 에이전트 토큰입니다.')
        user = db.get(User, grant.principal_user_id)
        if not user or not user.is_active:
            raise HTTPException(401, '사용자가 비활성화되었습니다.')
        return {'user': user, 'kind': 'agent', 'scopes': grant.scopes}
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, '로그인이 필요합니다.')
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except jwt.PyJWTError:
        raise HTTPException(401, '로그인 세션이 만료되었습니다.')
    if claims.get('kind') != 'session':
        raise HTTPException(401, '올바르지 않은 세션입니다.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        csrf = request.headers.get('x-csrf-token', '')
        if not csrf or not hmac.compare_digest(csrf, claims['csrf']):
            raise HTTPException(403, 'CSRF 검증에 실패했습니다.')
    user = db.get(User, claims['sub'])
    if not user or not user.is_active or claims.get('av', -1) != user.auth_version:
        raise HTTPException(401, '로그인이 필요합니다.')
    return {'user': user, 'kind': 'session', 'scopes': [], 'csrf': claims['csrf']}


def human(ctx=Depends(auth_context)):
    if ctx['kind'] != 'session':
        raise HTTPException(403, '본인의 로그인 세션에서 승인해야 합니다.')
    return ctx


def allowed(ctx, scope):
    if ctx['kind'] == 'agent' and scope not in ctx['scopes']:
        raise HTTPException(403, f'에이전트에 {scope} 범위가 없습니다.')


def only_human(ctx):
    if ctx['kind'] != 'session':
        raise HTTPException(403, '에이전트가 직접 실행할 수 없습니다.')
