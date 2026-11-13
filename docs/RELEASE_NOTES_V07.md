# ProjectAgain v0.7 — 프로젝트 미리보기 · 인수 가능성 · 문의 · 알림

## 제품 목표

- 판매자는 자신의 디지털 프로젝트를 **이미지·데모 링크·주요 기능**과 함께 소개한다.
- 구매자는 소스/README의 **확인된 구조**와 **추가 확인할 인수 작업**을 구별해 판단한다.
- 구매자와 판매자는 매물별로 **공개 질문 또는 당사자만 볼 수 있는 비공개 질문**을 주고받는다.
- 거래 관련 주요 사건은 **내부 알림**으로 기록되며, 선택적으로 **SMTP 이메일 알림**을 발송한다.

기존 ProjectAgain의 회원·권한·관리자 승인·DEMO 거래·외부 에이전트 API·GitHub App 연결·비공개 소스 보관 구조를 유지한다. **플랫폼 자체의 LLM 호출 없음. 실제 결제·소스코드 실행·권리 검증 없음.**

## 1. 미리보기

- 매물 초안 저장 후 `/sell/{id}/edit` 페이지에서 최대 8장의 PNG/JPEG/WebP 이미지 업로드(원본 최대 4MB/장, 계정 전체 80장).
- 파일을 재인코딩해 WebP로 저장하고 EXIF/메타데이터를 제거하며 해상도를 1920×1440 이내로 축소. SVG/HTML 등 활성 콘텐츠 거부.
- 이미지별 설명, 대표 이미지 선택, 삭제. 판매자가 제출한 HTTPS 시연 URL과 YouTube/Vimeo 영상 주소, 주요 기능 8개까지 저장.
- 페이지에서 직접 URL 내용을 가져오거나 실행하지 않음. 외부 시연 링크와 스크린샷은 **판매자가 제공한 자료이며 실제 작동 보증이 아님**을 표시.
- 이미지 원본 스토리지 키는 API로 노출되지 않음. 서버가 매물 조회 권한 검증 후 WebP를 전달.
- 공개 매물 변경 시 `PENDING_REVIEW`, 검토 중인 매물 재변경 시 `DRAFT`로 조정. 이미지/시연 자료 모두 관리자가 다시 검토해야 공개됨.

## 2. 인수 준비 체크리스트

- 기존 GitHub / ZIP 정적 분석 결과에 8개 항목 추가: README, 배포 설정, 의존성 잠금, 환경변수 안내, 테스트 구성, DB 관련 자료, 라이선스 파일, CI.
- 각 항목은 `FOUND` 또는 `REVIEW` 상태와 해설을 제공. 누락은 곧 프로젝트 결함을 뜻하지 않음.
- 구매자용 보고서에는 재확인할 작업 목록을 공개. 비공개 저장소 주소·소스 파일 경로·비밀값·원문은 공개하지 않음.
- **v0.6의 기존 소스 연결 매물**은 판매자 화면의 `소스 기준 인수 체크리스트 갱신`으로 저장된 원본 ZIP을 무결성 검사 후 재분석할 수 있음. GitHub를 재접속하지 않음. 공개 매물의 재분석은 관리자 재검토 대상.
- 분석은 소스 파일/매니페스트 기반 규칙 검사일 뿐, 코드 실행·테스트 통과·라이선스 적법성·사업성 보증이 아님.

## 3. 문의

- 로그인한 구매자가 공개된 매물에 `PUBLIC` 또는 `PRIVATE` 질문을 남김.
- 공개 질문은 매물 조회 가능자에게 공개; 비공개 질문은 질문 작성자·판매자·관리자에게만 공개.
- 판매자가 매물 상세/내 활동 문의함에서 답변. 구매자는 내 활동 문의함에서 답변을 확인.
- 연락처/외부 링크의 직접 게시를 제한하며 사용자당 일일 문의 12건, 동일 매물의 짧은 시간 반복 문의 제한.
- 관리자에게 문의 숨김 기능 제공(기존 거래·법적 중재를 대체하지 않음).
- 구매자는 자신의 매물에 질문할 수 없음. 추가 구매·판매 제안은 기존 DEMO 거래 화면 이용.

## 4. 알림

- 기존 알림 DB와 사용자·이벤트 접근 권한 재사용. 매물 검토 요청/승인·매물 문의/답변·제안·역제안·실사/인계 알림을 통합.
- 사이트 헤더 알림 표시, 내 활동 알림함, 읽음 처리, 모두 읽음 처리.
- 사용자별 이메일 수신 여부 설정. SMTP 미설정이어도 **내부 알림은 정상 제공**.
- 같은 DB 트랜잭션에 기록하는 `notification_emails` 대기열과 별도 작업용 `app.email_worker` 추가.
- SMTP 오류 시 최대 5회 지수 백오프 재시도. 이메일에는 비공개 질문/원문·토큰·첨부파일을 넣지 않음. 이메일은 적어도 한 번 전달될 수 있으므로 장애 순간 중복 전송 가능성 존재.
- **실제 이메일 발송은 SMTP Secrets와 `scripts/run_notification_worker.sh` 또는 예약 작업 `python -m app.email_worker --once`를 설정해야 동작.** 사이트 내부 알림만으로는 외부 이메일이 자동 전달되지 않음.

## DB 마이그레이션

`0005_marketplace_experience` 추가: `listing_showcases`, `listing_media`, `listing_inquiries`, `notification_preferences`, `notification_emails`.

기존 `0001`~`0004` 보존. 기존 DB를 삭제하거나 `create_all`로 운영 DB를 재생성하지 않음. Replit에서 백업 후 `alembic upgrade head` 실행.

## 파일 변경

- 신규: `backend/app/marketplace_models.py`, `backend/app/marketplace_v07.py`, `backend/app/notifications_v07.py`, `backend/app/email_worker.py`
- 신규: `backend/alembic/versions/0005_marketplace_experience.py`, `backend/tests/test_marketplace_v07.py`
- 신규: `frontend/src/MarketplaceExperience.tsx`, `scripts/run_notification_worker.sh`
- 수정: `backend/app/main.py`, `backend/app/stage2.py`, `backend/app/project_analyzer.py`, `backend/alembic/env.py`, `backend/tests/conftest.py`, `backend/requirements.txt`, `frontend/src/main.tsx`, `frontend/src/SourceReport.tsx`, `frontend/src/style.css`, `frontend/src/types.ts`, `.env.example`, `README.md`
- 새 API 계약: `contracts/implemented-openapi-v07.json`.

## 검증 범위와 미검증

- `test_marketplace_v07.py`: 9개 테스트 통과(미리보기, 권한, 이미지 형식, 문의 프라이버시, 알림, 기존 v0.6 소스 재분석).
- `test_project_imports.py`: 7개 통과.
- `test_workflows.py`: 16개 통과.
- `test_inspection_access.py` + `test_integration_v05.py`: 9개 통과.
- `test_phase2.py`: 9개 통과.
- `test_agent_listing_proposals.py`: 9개 통과 (기존 별도 실행).
- SQLite 신규 DB에서 Alembic `0001→0005` 업그레이드 통과. Python 정적 구문 및 TSX 구문 변환 검사 통과.
- 이 작업 환경에서는 npm 패키지 캐시와 접근 제한으로 **React 정식 `npm run build` 검증 미완료**. Replit에서 실제 빌드 및 웹 E2E 확인 필수.
- 실제 SMTP 발송(외부 이메일 수신), 실제 Replit Storage·PostgreSQL 동작, 브라우저별 UI, GitHub OAuth의 실환경 검증도 아직 수행하지 않음.

## 다음 단계

1. Replit에서 기존 프로젝트/DB/App Storage 백업 후 v0.7 소스 반영, `bash scripts/setup_replit.sh`로 프론트 빌드+마이그레이션.
2. 일반 매물 초안 생성 → 이미지/시연 등록 → 관리자 검토 → 구매자 조회.
3. 판매자·구매자 다른 계정으로 공개/비공개 문의 및 알림 검증.
4. SMTP Secrets/별도 이메일 워커 설정 후 실제 이메일 1회 수신과 실패 재시도 확인.
5. GitHub 공개/비공개 저장소 각각 기존 소스를 재분석한 보고서 검증.

상세 절차: `docs/UPGRADE_V06_TO_V07.md`, API: `docs/EXPERIENCE_API_V07.md`.
