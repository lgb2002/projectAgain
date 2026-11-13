# ProjectAgain v0.6 → v0.7 수동 업그레이드

**실제 결제·권리 이전은 이번 릴리스에 포함되지 않습니다.** 기존 로그인 계정/관리자 비밀번호/매물/거래 기록을 삭제하지 마세요.

## 적용 전

- Replit PostgreSQL 전체 백업(스냅샷/덤프) 및 App Storage 백업을 별도로 확보합니다.
- 기존 `projectagain` 폴더와 `frontend/dist`, `.venv`, 사용자 설정파일을 백업합니다. 기존 `.env` 및 Secrets 원문을 새 ZIP으로 덮지 않습니다.
- v0.7 ZIP에는 **실제 DB, 비밀키, 저장된 이미지, 빌드된 프론트가 포함되지 않습니다.** 
- GitHub App 설정·기존 연동 Secrets는 그대로 유지합니다.

## 배포

1. Replit 파일 업로드로 v0.7 ZIP을 업로드합니다.
2. 기존 `~/workspace/projectagain` 디렉터리를 삭제하지 말고 ZIP의 `projectagain/` 파일들을 같은 경로에 덮어씁니다. 단, DB·Secrets·업로드 파일을 덮거나 삭제하지 않도록 백업을 먼저 확인하세요.
3. Replit Shell에서:

```bash
cd ~/workspace/projectagain
bash scripts/setup_replit.sh
bash scripts/run_replit.sh
```

`setup_replit.sh`는 Python 의존성(이미지 처리 라이브러리 Pillow 포함)을 설치하고 React 빌드를 새로 만들며 Alembic `0005`까지 적용합니다. 시스템 Python에 직접 pip를 실행하지 않고 프로젝트 `.venv`를 사용합니다.

**주의:** npm 레지스트리 접속 실패, Pillow 패키지 방화벽 오류, DB 연결 오류가 나면 해당 오류를 해결하기 전까지 배포를 완료하지 마세요. 백업된 이전 빌드로 돌리는 경우에도 DB 마이그레이션은 비파괴적이지만, 사전에 백업을 확보해야 합니다.

## 확인 절차

1. `/health`: `status=ok` 확인.
2. `/api/v1/system/capabilities`: `showcase_media`, `takeover_readiness_checklist`, `listing_inquiries`, `email_outbox` 가 `true`인지 확인.
3. 판매자 로그인 → `판매 등록`에서 GitHub URL/ZIP/직접 입력 → 매물 **초안 저장**. 자동으로 미리보기 편집 화면으로 이동합니다.
4. JPG/PNG/WebP 이미지 1장 업로드, 2장째 대표 지정, HTTPS 시연 주소 및 YouTube/Vimeo URL·주요 기능 저장.
5. 매물 `DRAFT`이면 내 활동에서 `검토 요청`, 관리자가 `공개 승인`. 구매자 브라우저에서 매물 이미지·기능·분석 정보 확인.
6. 구매자 계정에서 공개 질문과 비공개 질문 각각 등록. 제3자 계정에 비공개 질문이 노출되지 않는지 확인.
7. 판매자 문의함에서 답변 → 구매자 내 활동 알림함에서 알림·읽음 처리 확인.
8. 기존 v0.6 GitHub/ZIP 매물은 판매자로 상세 화면의 **소스 기준 인수 체크리스트 갱신**을 클릭해 v0.7 정적 분석으로 업데이트할 수 있습니다. 갱신 후 관리자 재검토가 필요할 수 있습니다.
9. API·화면의 실제 운영 검증이 끝난 후에만 사용자에게 새 기능을 공개하세요.

## 이메일 발송 설정 (선택)

Replit Secrets에 다음을 설정합니다. 값은 모두 Replit에 직접 입력하고 외부에 공유하거나 코드에 기록하지 마세요.

```text
SMTP_HOST=<인증된 SMTP 서버 호스트>
SMTP_PORT=587
SMTP_USERNAME=<메일 서비스의 발송 계정>
SMTP_PASSWORD=<발송 계정 또는 앱 전용 비밀번호>
SMTP_FROM=<검증된 발신 주소>
SMTP_USE_STARTTLS=1
PUBLIC_BASE_URL=https://<실제 ProjectAgain 배포 도메인>
```

사이트 `내 활동 → 알림`의 이메일 수신 설정을 켜고, **별도의 Replit Workflow/Reserved VM/worker 프로세스**에서 다음 중 하나를 운영해야 실제 메일이 발송됩니다.

```bash
cd ~/workspace/projectagain
bash scripts/run_notification_worker.sh
```

또는 예약 작업에서 정기적으로 다음을 실행합니다.

```bash
cd ~/workspace/projectagain/backend
../.venv/bin/python -m app.email_worker --once
```

운영 환경에서는 반드시 동일한 `DATABASE_URL`과 SMTP Secrets에 접근해야 합니다. 워커가 실행되지 않으면 이메일은 DB의 `PENDING` 대기열에 머무르지만 내부 알림은 제공됩니다. SMTP 실패 시 2·4·8·16·32분 간격으로 재시도하며 최대 5회까지 시도합니다. 이메일은 중복 전송 가능성을 완전히 배제할 수 없습니다.

SMTP를 설정하지 않은 상태에서 이메일 인증을 테스트할 경우에도 기존 규칙이 적용됩니다. 일반 매물 공개를 위해 필요한 이메일 인증을 우회하지 마세요.

## 데이터 유지 / 권한

- `0005`는 **새 테이블만 생성**합니다. 기존 유저·매물·거래 테이블의 데이터는 변경하지 않습니다.
- 미리보기 원본은 `PRIVATE_STORAGE_BACKEND`로 관리됩니다. 운영 환경에서는 Replit App Storage 사용.
- 업로드한 이미지는 안전한 WebP로 변환되지만 완전한 악성코드 탐지 또는 권리 검증을 대체하지 않습니다.
- 원본 소스코드는 이전과 같이 격리·비공개이며 매물 이미지와 혼용하지 않습니다.
- 판매자가 공개 매물의 미리보기/소스 분석을 수정하면 매물 공개가 중단되고 관리자 검토로 돌아갈 수 있습니다.

## 테스트

```bash
cd ~/workspace/projectagain/backend
../.venv/bin/python -m pytest -q tests/test_marketplace_v07.py tests/test_project_imports.py
```

테스트 파일은 기존 실제 DB 연결을 강제로 격리한 임시 SQLite를 사용합니다. **운영 PostgreSQL을 직접 초기화하거나 테스트 fixture로 변경하지 마세요.**

문제가 생기면 실제 오류 로그(비밀번호·Secret·토큰 원문 제외), 현재 화면 및 어떤 단계에서 실패했는지 공유해 확인할 수 있습니다.
