"""Direct Streamlit -> ProjectAgain HTTP client. No separate agent API server.

Set in the agent's private .env (never in the marketplace frontend):
  MARKETPLACE_API_URL=https://<actual-projectagain-origin>
  MARKETPLACE_API_KEY=<short-lived delegated bearer token>

Legacy addresses that end in /api/v1 are accepted and normalized once.
This file is a reference client; adapt it to the agent's existing services layer.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

import requests


def normalize_base_url(value: str) -> str:
    raw = value.strip().rstrip('/')
    if raw.endswith('/api/v1'):
        raw = raw[:-7]
    parts = urlsplit(raw)
    if parts.username or parts.password or parts.query or parts.fragment or not parts.netloc:
        raise ValueError('플랫폼 API 주소는 호스트 주소여야 합니다.')
    if parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('공개 ProjectAgain API는 반드시 HTTPS를 사용해야 합니다.')
    if parts.path not in ('', '/'):
        raise ValueError('API 주소에 경로를 넣지 마세요. /api/v1은 자동 추가됩니다.')
    return raw + '/api/v1'


def payload_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class MarketplaceAPI:
    def __init__(self, url: str | None = None, token: str | None = None):
        self.base = normalize_base_url(url or os.environ['MARKETPLACE_API_URL'])
        self.token = token or os.environ['MARKETPLACE_API_KEY']
        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + self.token,
                                     'Accept': 'application/json'})

    def request(self, method: str, path: str, *, params=None, json_data=None,
                idempotency_key=None, download=False):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('상대 API 경로는 / 로 시작해야 합니다.')
        headers = {}
        if idempotency_key is not None:
            headers['Idempotency-Key'] = idempotency_key
        response = self.session.request(method, self.base + path, params=params,
                                        json=json_data, headers=headers, timeout=(5, 30))
        response.raise_for_status()
        if download:
            return response.content
        return response.json()

    def capabilities(self):
        return self.request('GET', '/system/capabilities')

    def me(self):
        return self.request('GET', '/auth/me')

    def context(self):
        return self.request('GET', '/agent/context')

    def list_listings(self, *, demo=False, limit=24, cursor=None, sort='newest'):
        params={'include_demo':str(bool(demo)).lower(),'limit':limit,'sort':sort}
        if cursor is not None:
            if not str(cursor).isdigit():
                raise ValueError('ProjectAgain v0.5 cursor는 0 이상의 숫자 문자열입니다.')
            params['cursor']=int(cursor)
        data=self.request('GET','/listings',params=params)
        if not isinstance(data.get('items'),list):
            raise ValueError('listing page: items 배열이 없습니다.')
        next_cursor=data.get('next_cursor')
        if next_cursor is not None and not str(next_cursor).isdigit():
            raise ValueError('listing page: cursor 형식 오류')
        return data

    def list_all_listings(self, *, demo=False, limit=100, max_pages=20):
        """Offset cursor; dedupe by immutable listing ID; bounded for safety."""
        found={}; cursor=None
        for _ in range(max_pages):
            result=self.list_listings(demo=demo,limit=limit,cursor=cursor)
            for item in result['items']:
                found[item['id']]=item
            next_cursor=result.get('next_cursor')
            if next_cursor is None or next_cursor == cursor:
                break
            cursor=next_cursor
        return list(found.values())

    def listing(self, listing_id, *, include_demo=False):
        return self.request('GET', f'/listings/{listing_id}',params={'include_demo':str(include_demo).lower()})

    def my_listings(self):
        # Existing v0.4/v0.5 response is an ARRAY, not {'items': ...}.
        return self.request('GET','/my/listings')

    def buyer_preferences(self):
        return self.request('GET','/buyer-preferences/me')

    def offers(self):
        return self.request('GET','/offers')

    def preparation_context(self, listing_id):
        return self.request('GET',f'/agent/listings/{listing_id}/preparation-context')

    def approved_inspection_assets(self, listing_id):
        """The seller-approved private assets ONLY; requires asset:inspect scope."""
        return self.request('GET',f'/agent/listings/{listing_id}/inspection-assets')

    def inspection_content(self, asset_id):
        """Download bytes for offline controlled inspection; NEVER execute uploaded code here."""
        return self.request('GET',f'/agent/assets/{asset_id}/inspection-content',download=True)

    def submit_report(self,listing_id, report,*, stable_request_id):
        """Buyer reports MUST include approved file source_version_sha256."""
        return self.request('POST',f'/listings/{listing_id}/inspection-reports',json_data=report,
                            idempotency_key=stable_request_id)

    def draft_action(self,action_type,resource_id,proposed_payload,*,expires_at=None,stable_request_id):
        if expires_at is None:
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        req={'action_type':action_type,'resource_id':resource_id,
             'proposed_payload':proposed_payload,'payload_sha256':payload_sha256(proposed_payload),
             'expires_at':expires_at}
        return self.request('POST','/agent-actions',json_data=req,idempotency_key=stable_request_id)

    def action(self,action_id):
        return self.request('GET',f'/agent-actions/{action_id}')

    def execute_approved_demo_action(self,action_id,*,stable_request_id=None):
        caps=self.capabilities()
        if caps.get('agent_write_mode')!='demo_only' or caps.get('agent_live_writes'):
            raise RuntimeError('에이전트 DEMO 쓰기가 비활성화되어 있습니다.')
        # Approval is a browser-session-only operation. Cannot be bypassed here.
        return self.request('POST',f'/agent-actions/{action_id}/execute',
                            idempotency_key=stable_request_id or f'execute-{action_id}')
