"""Bounded, read-only source archive analyzer.

Analyzes filenames and standard manifests only: NEVER imports/executes seller code,
never sends source to an LLM, never claims production or IP verification.
"""
import json
import ast
import re
from collections import Counter
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

TEXT_LIMIT = 128 * 1024
SKIP_PARTS = {'node_modules', '.git', 'dist', 'build', 'vendor', '.venv', 'venv', '__pycache__', 'coverage'}
TECH_FILES = {
    'requirements.txt': ('Python',), 'pyproject.toml': ('Python',), 'manage.py': ('Django',),
    'package.json': ('JavaScript',), 'tsconfig.json': ('TypeScript',), 'vite.config.ts': ('Vite',),
    'next.config.js': ('Next.js',), 'next.config.mjs': ('Next.js',), 'next.config.ts': ('Next.js',),
    'go.mod': ('Go',), 'cargo.toml': ('Rust',), 'gemfile': ('Ruby',),
    'pubspec.yaml': ('Flutter',), 'pom.xml': ('Java',), 'build.gradle': ('Java',),
    'dockerfile': ('Docker',), 'compose.yaml': ('Docker',), 'docker-compose.yml': ('Docker',),
}
NPM_TECH = {'react':'React', 'vue':'Vue', 'svelte':'Svelte', 'next':'Next.js', 'nextjs':'Next.js',
            'express':'Express', 'nestjs':'NestJS', '@nestjs/core':'NestJS', 'fastify':'Fastify',
            'typescript':'TypeScript', 'vite':'Vite', 'prisma':'Prisma', '@prisma/client':'Prisma',
            'tailwindcss':'Tailwind CSS', 'electron':'Electron', 'vitest':'Vitest', 'jest':'Jest'}
PY_TECH = {'fastapi':'FastAPI', 'django':'Django', 'flask':'Flask', 'streamlit':'Streamlit',
           'sqlalchemy':'SQLAlchemy', 'psycopg':'PostgreSQL driver', 'pytest':'pytest',
           'pytorch':'PyTorch', 'torch':'PyTorch', 'openai':'OpenAI SDK', 'langchain':'LangChain'}
SERVICE_HINTS = {'stripe':'Stripe', 'supabase':'Supabase', 'firebase':'Firebase',
                 'openai':'OpenAI API', 'redis':'Redis', 'postgres':'PostgreSQL', 's3':'S3',
                 'cloudinary':'Cloudinary', 'twilio':'Twilio'}
FEATURE_HINTS = {'auth':'인증 관련 코드', 'login':'로그인 관련 코드', 'payment':'결제 관련 코드',
                 'billing':'과금 관련 코드', 'admin':'관리자 기능 관련 코드',
                 'dashboard':'대시보드 관련 코드', 'chat':'채팅 관련 코드',
                 'booking':'예약 관련 코드', 'reservation':'예약 관련 코드',
                 'search':'검색 관련 코드', 'notification':'알림 관련 코드',
                 'upload':'업로드 관련 코드', 'api':'API 관련 코드'}
EXTENSION_LANG = {'.py':'Python', '.tsx':'TypeScript', '.ts':'TypeScript', '.jsx':'JavaScript',
                  '.js':'JavaScript', '.vue':'Vue', '.svelte':'Svelte', '.go':'Go', '.rs':'Rust',
                  '.dart':'Dart', '.java':'Java', '.kt':'Kotlin', '.cs':'C#', '.php':'PHP'}


def analyze_archive(blob: bytes, source_label: str = '업로드한 프로젝트') -> dict:
    from .static_inspector import inspect_zip
    structural = inspect_zip(blob)
    with ZipFile(BytesIO(blob)) as archive:
        files = [x for x in archive.infolist() if not x.is_dir()]
        paths = [PurePosixPath(x.filename.replace('\\', '/')) for x in files]
        filtered = [p for p in paths if not (set(s.lower() for s in p.parts) & SKIP_PARTS)]
        names = {p.name.lower() for p in filtered}
        declared_routes = 0
        python_source_files = 0
        def safe_read(path, limit=TEXT_LIMIT):
            try:
                item = archive.getinfo(str(path))
                if item.file_size > limit: return ''
                return archive.read(item).decode('utf-8')
            except (ValueError, RuntimeError, UnicodeError, KeyError): return ''

        def readme_intro():
            for p in filtered:
                if p.name.lower() not in ('readme.md','readme','readme.txt'): continue
                raw = safe_read(p)
                if not raw: continue
                lines = []
                in_code = False
                for line in raw.splitlines()[:120]:
                    t=line.strip()
                    if t.startswith(('```','~~~')): in_code = not in_code; continue
                    if in_code or not t or t.startswith(('![','<','[!','|','---','===')): continue
                    t = re.sub(r'^#{1,6}\s*', '', t)
                    t = re.sub(r'!?(\[([^]\n]+)\]\([^)]*\))', r'\2', t)
                    t = re.sub(r'https?://[^\s)]+', '', t)
                    t = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '', t)
                    t = re.sub(r'[*_`~#]', '', t).strip()
                    if len(t) >= 30 and not re.search(r'\b(api[_-]?key|password|secret|token)\s*[:=]', t, re.I):
                        lines.append(t[:250])
                    if len(' '.join(lines))>500: break
                return ' '.join(lines)[:700]
            return ''
        tech, services, features = set(), set(), set()
        lang_counter = Counter()
        for p in filtered:
            path_str = '/'.join(p.parts).lower()
            lang = EXTENSION_LANG.get(p.suffix.lower())
            if lang: lang_counter[lang] += 1
            tech.update(TECH_FILES.get(p.name.lower(), ()))
            for key, label in FEATURE_HINTS.items():
                # Signal only if a path segment or filename token matches.
                if re.search(r'(?<![a-z])' + re.escape(key) + r'(?![a-z])', path_str):
                    features.add(label)
        for path in filtered:
            if path.suffix.lower() != '.py' or python_source_files >= 120: continue
            python_source_files += 1
            code = safe_read(path, 64*1024)
            if not code: continue
            try:
                parsed = ast.parse(code)  # Python AST only; seller code is never executed.
                for node in ast.walk(parsed):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                                if decorator.func.attr in ('get','post','put','patch','delete','api_route','route','websocket'):
                                    declared_routes += 1
            except (SyntaxError, ValueError, MemoryError): pass
        for lang, qty in lang_counter.most_common(4):
            if qty >= 2: tech.add(lang)
        for entry in filtered:
            base = entry.name.lower()
            if base not in ('package.json', 'requirements.txt', 'pyproject.toml'):
                continue
            item = archive.getinfo(str(entry))
            if item.file_size > TEXT_LIMIT: continue
            try: data = archive.read(item).decode('utf-8')
            except (UnicodeError, ValueError, RuntimeError): continue
            if base == 'package.json':
                try:
                    manifest = json.loads(data)
                    deps = {**manifest.get('dependencies', {}), **manifest.get('devDependencies', {})}
                    if isinstance(deps, dict):
                        for name in deps:
                            if name.lower() in NPM_TECH: tech.add(NPM_TECH[name.lower()])
                except (TypeError, ValueError, AttributeError): pass
            else:
                for word, label in PY_TECH.items():
                    if re.search(r'(?<![\w-])' + re.escape(word) + r'(?![\w-])', data, re.I):
                        tech.add(label)
            for word, label in SERVICE_HINTS.items():
                if re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', data.lower()):
                    services.add(label)
        warning_codes = [x['code'] for x in structural['findings'] if x['severity'] == 'WARN']
        if '.gitmodules' in names: warning_codes.append('GIT_SUBMODULES_MAY_BE_MISSING')
        for path in filtered:
            if path.name.lower() == '.gitattributes' and 'filter=lfs' in safe_read(path, 32*1024):
                warning_codes.append('GIT_LFS_CONTENT_MAY_BE_MISSING')
                break
        has_tests = bool({'pytest.ini', 'vitest.config.ts', 'jest.config.js', 'test_main.py'} & names) or any('tests' in p.parts or 'test' in p.parts or p.name.lower().startswith('test_') or '.test.' in p.name.lower() or '.spec.' in p.name.lower() for p in filtered)
        has_readme = bool({'readme', 'readme.md', 'readme.txt'} & names)
        has_deploy = bool({'dockerfile', 'vercel.json', 'procfile', '.replit', 'compose.yaml', 'docker-compose.yml'} & names)
        # Actionable takeover report, grounded ONLY in manifest/file presence.
        # Missing evidence does not prove broken code. Never infer actual runtime health.
        has_lock = bool({'package-lock.json','pnpm-lock.yaml','yarn.lock','poetry.lock','uv.lock','pipfile.lock',
                         'cargo.lock','gemfile.lock'} & names)
        has_env_example = bool({'.env.example','.env.sample','.env.template','example.env'} & names)
        has_db_schema = bool({'schema.prisma','alembic.ini','schema.sql','drizzle.config.ts'} & names) or any(
            'migrations' in p.parts or 'alembic' in p.parts for p in filtered)
        has_license = bool({'license','license.md','license.txt','copying'} & names)
        has_ci = any('.github' in p.parts and 'workflows' in p.parts for p in paths)
        checks = [
            {'key':'PROJECT_GUIDE','label':'프로젝트 설명 문서','status':'FOUND' if has_readme else 'REVIEW',
             'detail':'README 파일이 있습니다. 내용의 정확성은 별도 확인이 필요합니다.' if has_readme else 'README가 탐지되지 않아 사용 목적과 실행 방법을 판매자에게 확인하세요.'},
            {'key':'DEPLOY','label':'실행·배포 설정','status':'FOUND' if has_deploy else 'REVIEW',
             'detail':'배포 관련 설정 파일이 탐지됐으나 실제 배포 성공 여부는 검사하지 않았습니다.' if has_deploy else '배포 설정을 찾지 못했습니다. 실행 명령과 호스팅 구성을 확인하세요.'},
            {'key':'DEPENDENCY_LOCK','label':'의존성 고정','status':'FOUND' if has_lock else 'REVIEW',
             'detail':'잠금 파일이 있습니다. 설치 성공 여부는 확인하지 않았습니다.' if has_lock else '버전 고정 파일이 탐지되지 않아 의존성 재현 가능성을 확인하세요.'},
            {'key':'ENVIRONMENT','label':'환경 설정 안내','status':'FOUND' if has_env_example else 'REVIEW',
             'detail':'환경 설정 템플릿이 탐지됐습니다. 실제 비밀값은 인수 대상에서 제외해야 합니다.' if has_env_example else '환경변수 템플릿이 없어 필요한 키 이름과 외부 계정을 확인하세요.'},
            {'key':'TESTS','label':'테스트 구성','status':'FOUND' if has_tests else 'REVIEW',
             'detail':'테스트 관련 파일이 탐지됐으나 실제 테스트는 실행하지 않았습니다.' if has_tests else '테스트 코드를 찾지 못했습니다. 구매 전에 핵심 시나리오를 검증하세요.'},
            {'key':'DATA','label':'데이터베이스 이전','status':'FOUND' if has_db_schema else 'REVIEW',
             'detail':'DB 스키마/마이그레이션 단서를 찾았습니다. 데이터 이전 절차는 별도 확인이 필요합니다.' if has_db_schema else 'DB 사용 여부와 초기화·이전 방법을 판매자에게 확인하세요.'},
            {'key':'LICENSE','label':'라이선스 문서','status':'FOUND' if has_license else 'REVIEW',
             'detail':'라이선스 파일이 있습니다. 판매 권리를 검증한 것은 아닙니다.' if has_license else '라이선스 문서가 탐지되지 않았습니다. 판매 권리와 제3자 라이선스를 확인하세요.'},
            {'key':'CI','label':'자동 검증 워크플로','status':'FOUND' if has_ci else 'REVIEW',
             'detail':'CI 설정이 있지만 실행 이력은 확인하지 않았습니다.' if has_ci else '자동화된 빌드·테스트 설정이 탐지되지 않았습니다.'},
        ]
        next_steps = [c['detail'] for c in checks if c['status']=='REVIEW'][:6]
        if not next_steps:next_steps=['실제 환경에서 빌드·시작·핵심 기능을 검증하고, 판매 권리 및 외부 계정 이전 가능성을 확인하세요.']
        lang = [name for name, _ in lang_counter.most_common(3)]
        tech_list = sorted(tech)[:30]
        intro = readme_intro()
        summary_text = (f'{source_label[:90]}의 정적 파일 분석 결과입니다. '
                        f'추정 기술: {", ".join(tech_list[:8]) or "확인 필요"}. '
                        + (f'README 작성자 설명(사실 확인 전): {intro} ' if intro else '')
                        + '실제 기능 동작, 배포 상태, 판매 권리는 확인되지 않았습니다.')
        return {
            'analysis_version': 'static-v2', 'level': 'STATIC_EVIDENCE_ONLY',
            'code_executed': False, 'llm_used': False, 'file_count': len(files),
            'languages': lang, 'tech_stack': tech_list,
            'python_route_declarations': declared_routes,
            'possible_features': sorted(features)[:15],
            'possible_services': sorted(services)[:15],
            'signals': {'readme': has_readme, 'tests': has_tests, 'deployment_config': has_deploy},
            'warnings': warning_codes,
            'takeover_checks': checks, 'takeover_next_steps': next_steps,
            'takeover_review_count': sum(c['status']=='REVIEW' for c in checks),
            'takeover_scope': '파일·선언 정보 기반 체크리스트. 코드 실행·사업성·권리·운영 검증 아님',
            'readiness': '추가 검증 필요' if warning_codes else '정적 파일 조건 확인 (실행 검증 아님)',
            'description_suggestion': summary_text[:2500],
            'included_assets_suggestion': ['소스코드 ZIP (비공개 보관·관리자 검토 대상)'],
            'excluded_assets_suggestion': ['비밀키·개인정보·외부 서비스 계정 (이전 대상 여부 별도 확인)'],
            'disclaimer': '파일명과 선언 파일만 분석했습니다. 구현·운영·저작권·보안 인증이 아닙니다.',
        }


def public_analysis(analysis: dict) -> dict:
    """Whitelist only non-sensitive fields: no repository URL, raw README, secrets, or source paths."""
    keys = ('analysis_version', 'level', 'code_executed', 'llm_used', 'file_count',
            'languages', 'tech_stack', 'possible_features', 'possible_services',
            'signals', 'warnings', 'readiness', 'disclaimer', 'python_route_declarations',
            'takeover_checks', 'takeover_next_steps', 'takeover_review_count', 'takeover_scope', 'ci_evidence')
    return {key: analysis[key] for key in keys if key in analysis}
