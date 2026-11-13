"""Deterministic no-execution project-readiness audit for ZIP uploads.

This is not an AI assessment, executable sandbox, malware certification, or
legal opinion. A signed external Streamlit agent may submit its OWN reports via
/inspection-reports. The server must never execute uploaded source code.
"""
import json
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

MAX_TEXT_READ = 128 * 1024


def inspect_zip(content: bytes):
    with ZipFile(BytesIO(content)) as z:
        files=[n.replace('\\','/') for n in z.namelist() if not n.endswith('/')]
        short=[str(PurePosixPath(n)).lower() for n in files]
        basenames={str(PurePosixPath(n)).split('/')[-1].lower() for n in files}
        findings=[]
        def note(key, severity, message, evidence):
            findings.append({'code':key,'severity':severity,'message':message,'evidence':evidence})
        def check(names,key,if_present,if_missing):
            matches=[n for n in files if str(PurePosixPath(n)).split('/')[-1].lower() in names]
            note(key,'INFO' if matches else 'WARN',if_present if matches else if_missing,matches[:8])
        check({'readme.md','readme.txt','readme'},'README','설치/설명 문서가 있습니다.','설치/설명 README 파일이 없습니다.')
        check({'requirements.txt','pyproject.toml','package.json','go.mod','cargo.toml'},'DEPENDENCIES',
              '의존성 정의 파일이 있습니다.','의존성 선언 파일을 발견하지 못했습니다.')
        check({'dockerfile','docker-compose.yml','compose.yaml','vercel.json','procfile','.replit'},'DEPLOYMENT',
              '배포 관련 설정을 발견했습니다.','명시적 배포/실행 설정을 발견하지 못했습니다.')
        check({'license','license.md','license.txt','copying'},'LICENSE',
              '프로젝트 라이선스 파일이 있습니다(양도권 증명은 아님).','프로젝트 LICENSE 정보가 없습니다(판매 권리 확인 필요).')
        check({'test_main.py','pytest.ini','vitest.config.ts','jest.config.js','test.py'},'TESTS',
              '테스트 관련 파일을 발견했습니다.','일반적인 테스트 설정 파일을 발견하지 못했습니다.')
        if 'package.json' in basenames:
            entry=next((n for n in files if n.rsplit('/',1)[-1].lower()=='package.json'),None)
            if entry and z.getinfo(entry).file_size <= MAX_TEXT_READ:
                try:
                    package=json.loads(z.read(entry))
                    scripts=list(package.get('scripts',{}).keys())
                    note('NPM_SCRIPTS','INFO','package.json에 선언된 실행 스크립트 이름입니다.',scripts[:25])
                except (ValueError,UnicodeError,TypeError):note('PACKAGE_JSON','WARN','package.json 파싱에 실패했습니다.',[entry])
        note('STATIC_ONLY','IMPORTANT','코드를 실행하거나 실제 서비스 이전을 검증하지 않았습니다.',[])
        important=sum(f['severity']=='WARN' for f in findings)
        return {'verdict':'PARTIAL' if important else 'UNVERIFIED',
                'findings':findings,'files_count':len(files),'code_executed':False,
                'level':'DETERMINISTIC_FILE_CHECK_ONLY','malware_scan':'SEPARATE_PROCESS'}
