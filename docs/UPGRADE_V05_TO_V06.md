# ProjectAgain v0.5 → v0.6 업데이트 가이드

기존 PostgreSQL 계정·매물·거래·파일과 외부 AI 에이전트 계약을 보존하며 GitHub/ZIP 자동 매물 등록을 추가합니다. **기존 DB를 삭제하거나 새로 만들지 마세요.** 운영자의 수동 Replit Shell에서 실행합니다.

## 업데이트 전

1. ProjectAgain의 기존 프로젝트 폴더와 PostgreSQL을 백업합니다. 기존 Replit Secrets의 `DATABASE_URL`, `JWT_SECRET`을 **바꾸지 않습니다**.
2. 현재 웹 서버를 중단하고, 새 ZIP의 `backend/`, `frontend/`, `scripts/`, `docs/` 등을 기존 `projectagain` 폴더에 덮어씁니다. ZIP 안의 `projectagain/`을 풀었다면 이 디렉터리가 최종 프로젝트 루트가 되게 합니다.
3. v0.6에서 추가한 세 테이블은 `github_connections`, `project_imports`, `listing_source_summaries`입니다. Alembic head가 `0004_project_imports`로 올라갑니다. 기존 테이블 컬럼을 제거하거나 덮어쓰지 않습니다.

## 적용 명령

```bash
cd ~/workspace/projectagain
bash scripts/setup_replit.sh
# 위 스크립트는 Python 의존성, 프론트 npm 빌드, alembic upgrade head를 처리합니다.
bash scripts/run_replit.sh
```

이미 `.venv`를 관리하고 있다면 의존성을 업데이트한 다음 아래만 개별 실행해도 됩니다.

```bash
cd ~/workspace/projectagain
PIP_CONFIG_FILE=/dev/null PIP_USER=0 .venv/bin/python -m pip install --no-user -r backend/requirements-dev.txt
cd frontend && npm install --no-audit --no-fund && npm run build
cd ../backend && ../.venv/bin/python -m alembic upgrade head
```

**프론트 재빌드는 필수입니다.** 기존 배포의 `frontend/dist`를 재사용하면 새 기능 UI가 표시되지 않습니다. 운영 환경에는 Replit App Storage의 비공개 버킷을 연결해야 ZIP 소스 보관이 가능하며, 운영 관리자 자산 공개 승인은 별도 ClamAV 스캔 성공을 요구합니다.

## GitHub App 설정 (비공개 저장소 사용 시)

1. GitHub의 `Settings → Developer settings → GitHub Apps → New GitHub App`에서 본 서비스용 GitHub App을 만듭니다.
2. Repository permissions: **Contents = Read-only**, Metadata = Read-only(기본). 소스 분석에는 Write/Administration/Issues 권한이 필요하지 않습니다.
3. User authorization callback URL을 `https://실제-사이트/api/v1/github/callback`으로 지정합니다.
4. Setup URL(선택)을 `https://실제-사이트/sell/new?github=installed`로 지정하면 설치 후 판매 등록 화면으로 복귀합니다.
5. GitHub App 설정에서 **Client ID**와 **Client Secret**, URL의 App slug를 확인합니다. App ID가 아니라 *Client ID*를 사용합니다.
6. Replit Secrets에 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_CALLBACK_URL`, `GITHUB_APP_SLUG`, `GITHUB_TOKEN_ENCRYPTION_KEY`를 각각 등록합니다. 마지막 값은 아래 방법으로 생성합니다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

7. `GITHUB_TOKEN_ENCRYPTION_KEY`를 임의로 바꾸면 기존 사용자가 저장한 GitHub 연결 토큰을 읽지 못합니다. 해당 키는 백업·보관하십시오. 앱을 선택 저장소에 설치한 판매자는 연결 후 저장소 목록에서 접근 가능한 저장소만 선택할 수 있습니다.

**앱 등록이 없다면** 공개 `github.com/owner/repo` URL과 ZIP 자동 분석 기능은 사용 가능하지만 비공개 저장소 선택 기능은 활성화되지 않습니다.

## 동작 확인

1. 서버의 `/api/v1/system/capabilities`에서 `github_app_import`, `zip_prelisting_analysis`를 확인합니다.
2. 로그인 → `/sell/new` → 공개 GitHub URL 또는 ZIP 분석 → 분석 결과 확인 → 필수 매물 정보 작성 → 초안 저장.
3. `/dashboard`에서 매물을 확인하고 원본 ZIP이 **비공개 격리 상태**로 연결됐는지 확인합니다.
4. 매물 검토를 요청하고 관리자 승인 후, 매물 상세에서 기술 분석 요약이 보이는지 확인합니다.
5. GitHub 비공개 저장소는 앱 설치 및 인증 후 별도로 테스트합니다. 실제 OAuth 흐름은 GitHub App 설정과 라이브 사이트가 필요하므로 테스트 환경만으로 성공을 보장할 수 없습니다.

## 운영 정리

등록 완료되지 않은 ZIP/GitHub 임시 원본은 **2시간 후 만료**됩니다. DB 상태만 만료 처리해도 스토리지 원본은 자동으로 삭제되지 않으므로, 정리 작업을 주기적으로 실행해야 합니다.

```bash
cd ~/workspace/projectagain
bash scripts/cleanup_staged_imports.sh
```

이 명령은 매물에 연결된 원본은 절대 삭제하지 않고, 만료된 `STAGED` 원본만 삭제합니다. Replit Workflow/예약 실행 환경에 하루 1회 등록하는 것을 권장합니다.

## 주의사항

- 기존 매물 등록 API는 그대로이며 `import_id`만 선택적으로 추가되었습니다.
- 매물에 가져온 원본 소스는 `QUARANTINED` 상태로 시작합니다. 읽기 권한 승인 절차는 기존 v0.5 그대로 유지됩니다.
- 정적 분석은 실제 작동/완성도·권리 소유권·악성코드 부재를 입증하지 않습니다. 업로드 파일을 실행하지 않으며 OpenAI API도 호출하지 않습니다.
- GitHub App 연결은 *사용자 인증*이며, 저장소 접근 권한만으로 판매 권리나 소유권이 확인되지는 않습니다.
