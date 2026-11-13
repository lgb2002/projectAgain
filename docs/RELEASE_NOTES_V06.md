# ProjectAgain v0.6 — 릴리스 인수인계

## 변경 목적

매물 등록을 GitHub 저장소 및 소스 ZIP 분석 중심으로 개선하되, 기존 판매자·관리자·거래·외부 AI 에이전트의 권한 모델과 시연 거래 정책을 유지한다.

## 작업 파일

- **신규 백엔드**: `app/github_source.py`(OAuth/고정호스트 API/암호화), `app/project_imports.py`(분석 임시 보관·비공개 소스 연결), `app/project_analyzer.py`(실행 없는 정적 분석), `app/import_cleanup.py`(만료 소스 삭제).
- **DB**: `models.py`에 GithubConnection·ProjectImport·ListingSourceSummary 추가, `alembic/versions/0004_project_imports.py` 신규.
- **API**: `main.py`, `schemas.py` 변경. `/listings` 입력의 `import_id`는 선택적이고 나머지는 v0.5 호환. `/listings/{id}/source-summary` 신규.
- **프론트**: `ImportPanel.tsx`, `SourceReport.tsx` 신규, `main.tsx`·`api.ts`·`style.css` 수정.
- **운영**: `scripts/cleanup_staged_imports.sh`, `.env.example` 설명 추가, `backend/requirements.txt`에 `cryptography` 추가.
- **계약**: `contracts/implemented-openapi-v06.json` 신규. 기존 `implemented-openapi-v05.json`은 비교 기록.

## 주요 보안 설계

인증된 판매자가 공개 저장소 또는 연결된 GitHub App 저장소를 선택. 서버는 원본을 가져와 엄격한 ZIP 검사 후 비공개로만 보관한다. 소스는 절대 실행하지 않고 외부 AI로 전송하지 않는다. 매물 등록에 사용할 때 판매자와 일회성 사용 여부를 확인하고 기존 격리 자료로 등록한다. 관리자 검토 및 판매자 동의가 없는 소스 공유를 금지한다. 공개 기술 요약에 사설 저장소명·소스 파일 경로·원문·암호화 토큰은 포함하지 않는다.

## 제약 및 미완료 확인

GitHub App은 서비스 운영자가 생성하고 Replit Secrets에 설정해야 완전히 연결할 수 있다. 실제 GitHub OAuth·비공개 저장소 연동, 실제 React 빌드, 운영 PostgreSQL·App Storage는 사용자의 Replit 환경에서 최종 통합 검증이 필요하다. 이번 릴리스는 심층 AI 기능 추론·실제 소스 실행·자동 권리 검증·상용 결제를 제공하지 않는다.

## 배포 우선순위

1. `docs/UPGRADE_V05_TO_V06.md` 읽고 DB·프로젝트 백업
2. 전체 소스 복사 후 의존성 설치, **프론트 재빌드**, Alembic 0004 적용
3. 일반 ZIP 및 공개 GitHub URL 등록 검증
4. GitHub App 생성·설정 후 비공개 저장소 연결 검증
5. 스토리지 정리 Workflow와 운영 모니터링 설정

실제 테스트 범위는 `docs/TEST_REPORT_V06.md`에 별도 기록. 실검증 전 기능이 완전히 검증되었다고 표시하지 않는다.
