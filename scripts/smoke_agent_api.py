"""Read-only HTTPS integration probe. Safe to run from VS Code or Replit Shell.

Never logs credentials or performs writes.
Usage: MARKETPLACE_API_URL=... MARKETPLACE_API_KEY=... python scripts/smoke_agent_api.py
"""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def normalized_origin(raw):
    val=raw.strip().rstrip('/')
    if val.endswith('/api/v1'):
        val=val[:-7]
    p=urlsplit(val)
    if p.scheme!='https' and not (p.scheme=='http' and p.hostname in ('127.0.0.1','localhost')):
        raise ValueError('HTTPS 도메인 또는 localhost 주소를 지정하세요.')
    if not p.hostname or p.path or p.username or p.password or p.query or p.fragment:
        raise ValueError('MARKETPLACE_API_URL에는 경로·계정·쿼리를 넣지 마세요.')
    return val


def main():
    host=normalized_origin(os.environ['MARKETPLACE_API_URL'])
    secret=os.environ.get('MARKETPLACE_API_KEY','')
    def fetch(path,authed=False):
        h={'Accept':'application/json'}
        if authed and secret:h['Authorization']='Bearer '+secret
        r=Request(host+path,headers=h)
        try:
            with urlopen(r,timeout=15) as resp:
                raw=resp.read(100_000)
                return resp.status,json.loads(raw)
        except HTTPError as exc:
            return exc.code,{}
    checks=[('health','/health',False),
            ('capabilities','/api/v1/system/capabilities',False),
            ('listings','/api/v1/listings?'+urlencode({'include_demo':'true','limit':2,'cursor':0}),False)]
    if secret:checks.extend([('me','/api/v1/auth/me',True),('agent context','/api/v1/agent/context',True)])
    failures=[]
    for name,path,authed in checks:
        try:
            code,data=fetch(path,authed)
            ok=code==200
            if name=='listings' and ok:
                ok=isinstance(data.get('items'),list) and (data.get('next_cursor') is None or str(data['next_cursor']).isdigit())
            if name=='capabilities' and ok:
                ok=data.get('api_base_path')=='/api/v1' and data.get('agent_live_writes') is False
            print(f'[{"PASS" if ok else "FAIL"}] {name}: HTTP {code}')
            if not ok:failures.append(name)
        except (URLError,ValueError,TimeoutError) as exc:
            print(f'[FAIL] {name}: {type(exc).__name__} (URL, 네트워크, 배포 상태를 확인하세요)')
            failures.append(name)
    if not secret:print('[INFO] MARKETPLACE_API_KEY 미설정: 인증 테스트는 생략됨')
    if failures:
        print('[SUMMARY] 통합 확인 미완료:',', '.join(failures));return 1
    print('[SUMMARY] 읽기 전용 API 호출 통과; 쓰기·파일 이전은 별도 승인 테스트 필요')
    return 0


if __name__=='__main__':sys.exit(main())
