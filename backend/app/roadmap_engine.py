"""Deterministic, conservative post-handover development planning.

Never executes seller code, consults an LLM, estimates schedules, or validates rights.
Uses only seller-disclosed public listing fields and already-sanitized source summaries.
"""
import hashlib
import json

PHASES = [
    {'key': 'TAKEOVER', 'label': '1. 인수 자료 확인', 'description': '인계 대상과 권리·접근 권한을 먼저 확인합니다.'},
    {'key': 'SETUP', 'label': '2. 개발 환경 준비', 'description': '새 소유자의 환경에서 프로젝트를 실행할 준비를 합니다.'},
    {'key': 'VERIFY', 'label': '3. 기능과 위험 점검', 'description': '실행 결과와 핵심 동작을 검증하고 누락을 정리합니다.'},
    {'key': 'RELAUNCH', 'label': '4. 재출시 준비', 'description': '외부 공개에 필요한 보안·운영 조건을 점검합니다.'},
]
DISCLAIMER = ('정적 파일 탐지 및 판매자 진술에 따른 작업 제안입니다. 실제 코드 실행·권리 검증·'
              '보안 인증·인수 완료·개발 기간 산정이 아닙니다. 전문가 필요 여부는 일반적인 권고입니다.')


def source_fingerprint(listing, analysis):
    payload = {
        'listing_id': listing.id, 'listing_version': listing.version,
        'category': listing.category, 'tech_stack': listing.tech_stack,
        'included_assets': listing.included_assets, 'excluded_assets': listing.excluded_assets,
        'known_defects': listing.known_defects, 'required_services': listing.required_services,
        'sale_rights_type': listing.sale_rights_type, 'analysis': analysis,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


def create_template(listing, analysis=None):
    analysis = analysis if isinstance(analysis, dict) else {}
    checks = {x.get('key'): x for x in analysis.get('takeover_checks', [])
              if isinstance(x, dict) and isinstance(x.get('key'), str)}
    features = analysis.get('possible_features') or []
    services = analysis.get('possible_services') or []
    warnings = analysis.get('warnings') or []
    tasks = []

    def add(key, phase, title, detail, *, difficulty='MEDIUM', assistance='GUIDED',
            priority='HIGH', prerequisites=(), steps=(), success=(), evidence='GENERAL_GUIDANCE'):
        tasks.append({
            'key': key, 'phase': phase, 'title': title, 'detail': detail,
            'difficulty': difficulty, 'assistance': assistance, 'priority': priority,
            'prerequisites': list(prerequisites), 'steps': list(steps), 'success_criteria': list(success),
            'evidence': evidence, 'position': len(tasks) + 1, 'source_kind': 'GENERATED',
        })

    add('ASSET_INVENTORY', 'TAKEOVER', '인수 대상 파일과 자산 목록 확인',
        '판매자와 약속한 포함·제외 자산을 비교하고, 받은 파일이 모두 열리는지 확인합니다.',
        difficulty='EASY', assistance='SELF',
        steps=('매물의 포함·제외 자산 목록을 나란히 놓습니다.', '받은 파일·문서·도메인 등 항목을 체크합니다.',
               '누락 또는 접근 불가 항목은 판매자에게 문의합니다.'),
        success=('약속된 항목별 수령 여부를 기록했습니다.', '미수령 자산과 책임자를 정리했습니다.'),
        evidence='SELLER_DECLARATION')
    add('RIGHTS_REVIEW', 'TAKEOVER', '양도 범위와 제3자 라이선스 확인',
        '소스 수령만으로 저작재산권이 이전되지는 않습니다. 계약·오픈소스·이미지·콘텐츠 사용 권한을 별도로 확인합니다.',
        difficulty='HARD', assistance='EXPERT', prerequisites=('ASSET_INVENTORY',),
        steps=('계약에 기록된 권리 유형과 실제 인수 자산을 대조합니다.',
               '오픈소스와 타사 코드·이미지·데이터의 라이선스를 점검합니다.',
               '불확실한 권리는 권리자 또는 전문가에게 확인합니다.'),
        success=('미확인 권리 항목이 기록돼 있습니다.', '외부 공개 전 권리 확인 절차를 결정했습니다.'),
        evidence='SELLER_DECLARATION')
    # A content/template asset is not necessarily executable software. Do not ask
    # a non-code buyer to install packages or deploy an API when no such product exists.
    if listing.category == 'content_asset':
        add('EDITABLE_FILES', 'SETUP', '편집 가능한 원본과 파일 형식 확인',
            '이미지·문서·템플릿 등 전달된 파일이 수정 가능한 원본인지 확인합니다.',
            difficulty='EASY', assistance='SELF', prerequisites=('ASSET_INVENTORY',),
            steps=('원본 파일과 결과물 파일을 구분합니다.',
                   '사용할 편집 프로그램에서 파일을 열어봅니다.'),
            success=('모든 주요 파일의 열람·편집 가능 여부를 기록했습니다.'), evidence='SELLER_DECLARATION')
        add('CONTENT_QUALITY', 'VERIFY', '콘텐츠의 완성도와 사용성 점검',
            '깨진 링크, 폰트·이미지 누락, 오탈자, 템플릿 편집성을 확인합니다.',
            difficulty='MEDIUM', assistance='SELF', prerequisites=('EDITABLE_FILES',),
            steps=('샘플 콘텐츠를 실제로 편집하거나 출력합니다.',
                   '누락된 참조 파일이나 깨진 링크를 점검합니다.'),
            success=('샘플을 정상적으로 편집하거나 출력했습니다.'), evidence='GENERAL_GUIDANCE')
        add('CONTENT_RIGHTS', 'VERIFY', '제3자 콘텐츠 재사용 조건 점검',
            '외부 이미지·폰트·음원 등 상용 이용 범위를 확인합니다.',
            difficulty='HARD', assistance='EXPERT', prerequisites=('RIGHTS_REVIEW','CONTENT_QUALITY'),
            steps=('제3자 자료와 라이선스 증빙을 목록화합니다.',
                   '용도·배포·재판매 가능 여부를 전문가 또는 권리자에게 확인합니다.'),
            success=('불확실한 권리 문제의 확인 절차가 있습니다.'), evidence='GENERAL_GUIDANCE')
        add('CONTENT_PACKAGE', 'RELAUNCH', '새 배포용 패키지와 안내서 제작',
            '이용자에게 전달할 파일 구성, 버전, 사용 방법과 문의 채널을 정합니다.',
            difficulty='MEDIUM', assistance='SELF', prerequisites=('CONTENT_RIGHTS',),
            steps=('배포용 파일과 원본 보관 파일을 분리합니다.',
                   '사용법·필수 프로그램·제약 사항을 적습니다.'),
            success=('배포용 파일 묶음과 사용 가이드가 준비됐습니다.'), evidence='GENERAL_GUIDANCE')
        return {'analysis_basis': 'PUBLIC_STATIC_SUMMARY' if analysis else 'SELLER_DECLARATION_ONLY',
                'source_fingerprint': source_fingerprint(listing, analysis),
                'phase_definitions': PHASES, 'tasks': tasks, 'disclaimer': DISCLAIMER,
                'notice': '단계별 예상 작업 목록이며 완료·운영 가능성·양도 권리의 보증이 아닙니다.'}

    add('ACCESS_SECURITY', 'TAKEOVER', '계정 접근과 비밀키 교체 계획',
        '전달 받은 계정·API 키·토큰은 안전하게 교체하고, 판매자의 기존 권한은 계약 범위에 따라 정리합니다.',
        difficulty='MEDIUM', assistance='GUIDED', prerequisites=('ASSET_INVENTORY',),
        steps=('필요한 외부 계정·API 목록을 만듭니다.', '비밀번호·토큰·API 키를 새 값으로 발급하고 안전하게 보관합니다.',
               '기존 접근 권한과 개인정보 포함 여부를 점검합니다.'),
        success=('새 소유자가 사용하는 권한을 정리했습니다.', '기존 비밀값의 교체·폐기 여부를 확인했습니다.'))

    if checks.get('PROJECT_GUIDE', {}).get('status') != 'FOUND':
        add('PROJECT_DOCUMENTATION', 'TAKEOVER', '프로젝트 사용·설치 가이드 확보',
            'README 문서가 탐지되지 않았습니다. 판매자에게 실행 절차를 확인하고 별도의 안내서를 작성합니다.',
            difficulty='EASY', assistance='SELF', prerequisites=('ASSET_INVENTORY',),
            steps=('프로젝트의 목적과 주요 화면을 기록합니다.', '설치 명령·설정 항목·실행 방법을 정리합니다.'),
            success=('새로운 작업자가 따라 할 수 있는 기본 안내서가 있습니다.'), evidence='STATIC_NOT_FOUND')

    external = bool(listing.required_services or services)
    if external:
        add('SERVICE_REVIEW', 'SETUP', '외부 서비스 연결과 운영 비용 확인',
            '판매자가 고지했거나 의존성에서 탐지된 외부 서비스의 계정·요금·이전 가능성을 점검합니다.',
            difficulty='MEDIUM', assistance='GUIDED', prerequisites=('ACCESS_SECURITY',),
            steps=('사용 중인 서비스를 실제로 확인합니다.', '이전이 가능한 계정과 새로 개설해야 할 계정을 구분합니다.',
                   '과금·개인정보·API 사용량 한도를 확인합니다.'),
            success=('서비스별 담당자와 접근 방법을 정리했습니다.', '예상 운영 비용의 근거를 확인했습니다.'),
            evidence='SELLER_OR_STATIC_SIGNAL')

    env_found = checks.get('ENVIRONMENT', {}).get('status') == 'FOUND'
    add('ENVIRONMENT_SETUP', 'SETUP', '환경변수와 개발 도구 준비',
        ('환경 설정 템플릿이 탐지됐습니다. 실제 값은 공유하지 말고 새 환경에서 직접 설정합니다.' if env_found
         else '환경변수 템플릿이 탐지되지 않았습니다. 판매자에게 필요한 설정 이름부터 확인합니다.'),
        difficulty='MEDIUM', assistance='GUIDED', prerequisites=('ACCESS_SECURITY',),
        steps=('언어·런타임·DB 등 필요한 개발 도구를 확인합니다.', '비밀키를 코드 밖의 환경변수로 설정합니다.',
               '설정된 값을 노출하지 않고 연결 여부만 검사합니다.'),
        success=('설치와 설정 방법을 재현 가능하게 기록했습니다.'),
        evidence='STATIC_FOUND' if env_found else 'STATIC_NOT_FOUND')
    locked = checks.get('DEPENDENCY_LOCK', {}).get('status') == 'FOUND'
    add('DEPENDENCY_SETUP', 'SETUP', '의존성 설치·버전 재현',
        ('의존성 잠금 파일이 탐지됐지만 설치 성공을 확인한 것은 아닙니다.' if locked else
         '의존성 잠금 파일이 탐지되지 않았습니다. 호환 가능한 버전을 검토한 뒤 고정하세요.'),
        difficulty='MEDIUM', assistance='GUIDED', prerequisites=('ENVIRONMENT_SETUP',),
        steps=('패키지 설치 설명을 확인합니다.', '격리된 개발 환경에서 잠금 버전대로 설치합니다.',
               '실패 원인과 설치 버전을 기록합니다.'),
        success=('새 환경에서 의존성 설치 결과를 확인했습니다.'),
        evidence='STATIC_FOUND' if locked else 'STATIC_NOT_FOUND')

    db_signal = bool(checks.get('DATA', {}).get('status') == 'FOUND' or
                     any(s in ('PostgreSQL', 'Firebase', 'Supabase') for s in services) or
                     any(token in str(v).lower() for v in (listing.required_services or []) + (listing.tech_stack or [])
                         for token in ('postgres', 'mysql', 'mongodb', 'sqlite', 'supabase', 'firebase')))
    if db_signal:
        add('DATABASE_SETUP', 'SETUP', '데이터베이스 초기화·이전 검증',
            'DB 사용 단서가 있습니다. 데이터 백업, 스키마 및 개인정보 처리 방법을 판매자에게 확인합니다.',
            difficulty='HARD', assistance='EXPERT', prerequisites=('ENVIRONMENT_SETUP',),
            steps=('빈 테스트 DB를 별도로 생성합니다.', '스키마와 마이그레이션을 검토합니다.',
                   '개인정보가 없는 테스트 데이터로 복구 과정을 확인합니다.'),
            success=('검증용 DB에 스키마를 적용했습니다.', '백업·복구 담당자를 정했습니다.'),
            evidence='STATIC_SIGNAL')

    run_deps = ['DEPENDENCY_SETUP'] + (['DATABASE_SETUP'] if db_signal else [])
    add('LOCAL_RUN', 'SETUP', '로컬에서 프로젝트 실행 확인',
        '실행 성공 여부는 정적 분석으로 알 수 없습니다. 격리된 환경에서 직접 확인해야 합니다.',
        difficulty='MEDIUM', assistance='GUIDED', prerequisites=run_deps,
        steps=('프로젝트 시작 명령을 확인합니다.', '개발용 데이터와 최소 권한으로 실행합니다.',
               '오류·스크린샷·미작동 항목을 기록합니다.'),
        success=('실행 성공 또는 재현 가능한 실패 로그를 확보했습니다.'),
        evidence='NOT_RUNTIME_VERIFIED')
    add('FEATURE_CHECK', 'VERIFY', '핵심 기능을 사용자 관점에서 검증',
        ('정적 분석에서 기능 관련 파일 단서가 탐지됐습니다. 실제 구현·동작 여부를 직접 확인합니다.' if features else
         '주요 기능이 코드만으로 확인되지 않았습니다. 판매자 설명과 화면을 기준으로 시험 항목을 작성합니다.'),
        difficulty='MEDIUM', assistance='GUIDED', prerequisites=('LOCAL_RUN',),
        steps=('로그인·생성·수정·삭제 등 핵심 사용자 경로를 정리합니다.',
               '각 기능을 직접 수행하고 정상·실패 조건을 기록합니다.',
               '판매자에게 알려진 결함과 결과를 비교합니다.'),
        success=('기능별 확인 결과와 재현 단계를 기록했습니다.'),
        evidence='STATIC_SIGNAL' if features else 'SELLER_DECLARATION')

    if listing.category == 'ai_agent':
        add('AGENT_EVALUATION', 'VERIFY', '에이전트의 실제 응답·행동 검증',
            '에이전트가 접근하는 외부 데이터, 실행 권한, 사용자 승인 및 실패 상황을 점검합니다.',
            difficulty='HARD', assistance='EXPERT', prerequisites=('FEATURE_CHECK',),
            steps=('정상 요청과 잘못된 요청의 결과를 기록합니다.',
                   '외부 도구·API 호출의 권한과 중단 조건을 점검합니다.',
                   '사용량 제한과 오류 복구 방식을 확인합니다.'),
            success=('대표 시나리오 결과와 위험 대응 항목을 기록했습니다.'), evidence='GENERAL_GUIDANCE')
    if listing.category == 'game':
        add('GAME_PLAYTEST', 'VERIFY', '게임 플레이와 리소스 일관성 점검',
            '시작·종료·저장·반복 플레이 중 오류를 확인하고 필수 리소스의 포함 여부를 확인합니다.',
            difficulty='MEDIUM', assistance='GUIDED', prerequisites=('FEATURE_CHECK',),
            steps=('최소 1회 플레이 경로를 직접 검증합니다.',
                   '사운드·이미지·저장 데이터 누락을 확인합니다.'),
            success=('플레이 재현 결과와 발견된 문제를 기록했습니다.'), evidence='GENERAL_GUIDANCE')
    if listing.category == 'mobile_app':
        add('APP_DISTRIBUTION', 'VERIFY', '모바일 배포·서명 체계 확인',
            '앱 패키지 서명, 스토어 배포 계정, 플랫폼 정책과 빌드 설정은 별도로 확인해야 합니다.',
            difficulty='HARD', assistance='EXPERT', prerequisites=('FEATURE_CHECK',),
            steps=('앱 패키지 서명 권한과 빌드 기기를 확인합니다.',
                   '배포 대상 스토어의 정책과 개인정보 요구사항을 확인합니다.'),
            success=('스토어 배포 계정과 서명 인계 절차를 정리했습니다.'), evidence='GENERAL_GUIDANCE')
    if listing.category in ('saas','revenue_site'):
        add('BILLING_CLAIMS', 'VERIFY', '과금·운영 지표와 이전 가능성 점검',
            '결제 코드나 판매자 매출 진술은 실거래·매출 검증이 아닙니다. 외부 계정과 법적 이전 요건을 확인합니다.',
            difficulty='HARD', assistance='EXPERT', prerequisites=('FEATURE_CHECK',),
            steps=('결제·구독·환불 경로가 실제 필요한지 확인합니다.',
                   '매출·고객 데이터의 원본 증빙과 이전 가능성을 확인합니다.'),
            success=('과금·지표·데이터 인계 가능성을 별도로 검토했습니다.'), evidence='GENERAL_GUIDANCE')

    if listing.known_defects:
        add('DEFECT_BACKLOG', 'VERIFY', '판매자가 고지한 결함부터 정리·수정',
            '매물에 알려진 문제점이 표시돼 있습니다. 문제를 재현하고 영향도가 높은 항목부터 수정합니다.',
            difficulty='HARD', assistance='EXPERT', prerequisites=('FEATURE_CHECK',),
            steps=('매물의 알려진 결함을 별도 이슈 목록으로 옮깁니다.',
                   '재현 가능성과 영향도를 구분합니다.', '수정 후 이전에 정상 작동하던 기능도 검사합니다.'),
            success=('고지된 결함별 상태와 수정·검증 결과가 있습니다.'), evidence='SELLER_DECLARATION')

    tests_found = checks.get('TESTS', {}).get('status') == 'FOUND'
    add('TEST_REGRESSION', 'VERIFY', '핵심 시나리오 테스트와 회귀 검사',
        ('테스트 파일은 탐지됐지만 성공 여부는 검증되지 않았습니다.' if tests_found else
         '테스트 파일이 탐지되지 않았습니다. 최소한의 반복 검사부터 추가하세요.'),
        difficulty='HARD', assistance='EXPERT', prerequisites=('FEATURE_CHECK',),
        steps=('핵심 화면과 API에서 반드시 작동해야 할 동작을 목록화합니다.',
               '가능한 범위에서 테스트를 자동화합니다.',
               '결함 수정 뒤 테스트를 다시 수행하고 결과를 기록합니다.'),
        success=('기본 검증 목록과 실행 결과가 있습니다.'),
        evidence='STATIC_FOUND' if tests_found else 'STATIC_NOT_FOUND')
    add('SECURITY_AUDIT', 'VERIFY', '외부 공개 전 보안·개인정보 점검',
        '코드 ZIP 정적 검사는 운영 보안을 보장하지 않습니다. 권한·의존성·비밀값·개인정보를 별도로 점검합니다.',
        difficulty='HARD', assistance='EXPERT', prerequisites=('FEATURE_CHECK', 'ACCESS_SECURITY'),
        steps=('저장소나 공개 화면에 비밀키·개인정보가 노출되지 않았는지 확인합니다.',
               '접근 권한·업로드·인증 등 주요 공격 표면을 점검합니다.',
               '취약한 의존성과 수정·배포 계획을 기록합니다.'),
        success=('중대한 위험의 조치 여부를 기록했습니다.'),
        evidence='GENERAL_GUIDANCE')
    if warnings:
        add('ARCHIVE_INTEGRITY', 'VERIFY', '소스 아카이브 누락 가능성 확인',
            '정적 검사에서 추가 확인이 필요한 파일 구조 단서가 발견됐습니다. 저장소의 서브모듈·대용량 파일 등을 확인하세요.',
            difficulty='MEDIUM', assistance='GUIDED', prerequisites=('ASSET_INVENTORY',),
            steps=('원본 저장소와 인수 ZIP의 파일 수를 비교합니다.',
                   '서브모듈·대용량 파일·외부 자산 여부를 판매자에게 확인합니다.'),
            success=('누락된 필수 소스가 있는지 확인했습니다.'), evidence='STATIC_SIGNAL')

    deploy_found = checks.get('DEPLOY', {}).get('status') == 'FOUND'
    release_reqs = ['TEST_REGRESSION', 'SECURITY_AUDIT', 'RIGHTS_REVIEW']
    add('DEPLOY_STAGING', 'RELAUNCH', '시험 환경에서 배포·복구 확인',
        ('배포 설정 파일은 탐지됐지만 실제 배포된 적이 있는지는 확인하지 않았습니다.' if deploy_found else
         '배포 설정이 탐지되지 않아 호스팅과 실행 구성을 새로 정해야 할 수 있습니다.'),
        difficulty='HARD', assistance='EXPERT', prerequisites=release_reqs,
        steps=('개인정보 없는 시험 환경에 배포합니다.', '도메인·HTTPS·저장소·DB 설정을 확인합니다.',
               '실패 시 되돌리는 방법과 백업 복구를 테스트합니다.'),
        success=('시험 배포 및 복구 절차를 기록했습니다.'),
        evidence='STATIC_FOUND' if deploy_found else 'STATIC_NOT_FOUND')
    add('LAUNCH_REVIEW', 'RELAUNCH', '공개 전 최종 점검과 운영 계획',
        '운영비·법적 요건·고객 지원·모니터링은 프로젝트별로 별도 검토가 필요합니다.',
        difficulty='MEDIUM', assistance='GUIDED', prerequisites=('DEPLOY_STAGING',),
        steps=('최소 모니터링과 오류 알림 방법을 정합니다.', '예상 요금과 서비스 약관·개인정보 의무를 확인합니다.',
               '공개 여부와 책임자를 최종 결정합니다.'),
        success=('재출시 준비 체크리스트를 검토했습니다.'), evidence='GENERAL_GUIDANCE')

    return {
        'analysis_basis': 'PUBLIC_STATIC_SUMMARY' if analysis else 'SELLER_DECLARATION_ONLY',
        'source_fingerprint': source_fingerprint(listing, analysis),
        'phase_definitions': PHASES, 'tasks': tasks, 'disclaimer': DISCLAIMER,
        'notice': '단계별 예상 작업 목록이며 완료·운영 가능성·양도 권리의 보증이 아닙니다.',
    }
