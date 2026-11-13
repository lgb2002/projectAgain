# ProjectAgain — 초소형 디지털 자산 거래 플랫폼 v0.13

> **API-first · 외부 에이전트 연동 · Replit 수동 배포**
>
> 본 저장소는 **거래 플랫폼만** 포함합니다. AI 모델 실행, LangChain, 판매글 생성, 협상 추론 등은 **별도 에이전트**의 책임입니다. 플랫폼은 회원·매물·비공개 자료·거래·작업 제안·승인·검수 이력을 API로 제공하며 **OpenAI API를 직접 호출하지 않습니다.**
>
> **중요:** Replit Agent / Max Mode / ChatGPT-Replit 자동 개발·배포 도구를 **사용하지 않습니다.** ZIP을 사람이 직접 업로드하고 Replit 일반 Shell에서 설치·실행합니다. 이번 개발에 Replit Agent와 OpenAI API 유료 호출은 사용하지 않았습니다.
>
> **실제 결제·에스크로·저작재산권 자동 이전·프로젝트의 임의 코드 실행은 제공하지 않습니다.** 거래는 DEMO 전용이며 운영 전 검증이 더 필요합니다.

## v0.12: 협상·인수·개발·지원 통합 작업실 (DEMO)

- **시연 거래 안전성:** 제안 수락·인수 완료·취소가 매물의 실제 `ACTIVE` 상태를 `RESERVED`/`CLOSED`로 바꾸지 않습니다. 서로 다른 구매자의 시연도 독립적으로 진행할 수 있습니다.
- **거래 조건:** 제안 가격, 권리 종류, 포함·제외 자산, 인계 예정 일수, 판매자 지원 기간·건수·범위를 `schema_version=2`로 구조화하고 역제안 이력과 변경 사항을 보여줍니다. 기존 자유 형식 협상은 보존하며 새 지원 약정을 임의 부여하지 않습니다.
- **서명 없는 조건 기록:** 실제 결제·권리 이전 없이 시연 합의 조건 해시를 고정하고, 구매자의 최종 시연 인수 시에만 지원 기간을 시작합니다.
- **개발 로드맵:** 경험 수준과 안내 선호를 프로젝트별로 저장하고, 단계별 준비·체크리스트·막힘 사유와 판매자 지원 요청을 연결합니다. 플랫폼 내부의 AI 모델 호출은 없습니다.
- **지원 센터:** 약정된 기술 문의(권장 0/3/5/10건), 인수 자료 누락·권리 문제의 별도 경로, 대화·기한·사용량·구매자 해결 확정·관리자 검토를 지원합니다. 첨부파일은 현재 비활성화되어 있습니다.
- **데이터 보존:** 새 Alembic `0008_integrated_workspace`가 기존 계정·매물·제안·계약·로드맵을 유지합니다. 과거 시연으로 예약된 매물은 자동 복구하지 않으며 개별 감사 후 관리자가 조치합니다.
- **주의:** 이 환경에서 React 빌드는 npm 의존성 다운로드 제약으로 미검증이며 Replit에서 반드시 정식 빌드해야 합니다. PostgreSQL·Storage·SMTP·동시성 실검증도 출시 전 필요합니다.

자세한 사항: `docs/RELEASE_NOTES_V12.md`, `docs/UPGRADE_V11_TO_V12.md`, `docs/TEST_REPORT_V12.md`, `docs/INTEGRATED_WORKSPACE_API_V12.md`.

## v0.11: 알림 동기화 및 사용자 행동 중심 UI·UX 개편

- 헤더 알림 배지와 알림함의 읽음 상태를 하나로 통합하고, 서버 전체 미읽음 개수를 사용합니다. 이전 알림 페이지네이션을 추가했습니다.
- 헤더 메뉴를 프로젝트 탐색·프로젝트 판매·내 프로젝트로 단순화하고, 알림/외부 에이전트 설정을 계정 설정으로 분리했습니다.
- 매물 상세를 4개 탭, 프로젝트 탐색의 상세 필터를 펼쳐보기, 거래 취소·분쟁·이력을 접기 화면으로 변경했습니다.
- 매물 초안 저장 이후 새로고침 가능한 마무리 화면에서 이미지·시연 정보를 저장하고 검토 요청하도록 연결했습니다.
- 관리자 화면의 검토 대기 큐 및 파일 관리 딥링크를 개선했습니다.
- DB 구조 변경 및 새로운 Secret은 없습니다. 실제 결제·정산·법적 권리 이전은 지원하지 않습니다.
- 백엔드 테스트 77개를 기능별로 나누어 통과. 프론트엔드는 TSX 구문 검사를 통과했지만 이 환경에서 npm 정식 빌드는 미검증입니다.
- 문서: `docs/RELEASE_NOTES_V11.md`, `docs/UPGRADE_V10_TO_V11.md`, `docs/UX_ACCEPTANCE_V11.md`.

## v0.9: 인수 후 개발 로드맵

- 매물 상세에 **인수 후 예상 작업**을 단계별로 공개: 파일·권리 확인 → 실행 환경 준비 → 기능·보안 점검 → 재출시 준비.
- 정적 소스 분석과 판매자 고지 내용을 기반으로 난이도·선행 조건·혼자 가능한 작업·도움 권장 작업·전문가 검토 권장 작업을 표시합니다.
- `DEMO_COMPLETED` 거래의 **구매자 본인**은 개인 로드맵을 생성해 진행 상태·메모를 저장하고 작업을 추가하며 `.md` 파일로 내보낼 수 있습니다.
- 선행 작업 제약과 작업 변경 이력을 보존합니다. 원본 분석 변경 시 기존 진행 기록은 유지하고 변경 경고를 표시합니다.
- 신규 DB 마이그레이션: `0007_development_roadmap` (기존 DB 보존, 새 테이블 2개).
- **실제 결제·소유권 이전·코드 실행·법적/보안 인증은 지원하지 않습니다.** 이 로드맵은 실사 보증이나 기간 견적이 아닙니다.
- 문서: `docs/RELEASE_NOTES_V09.md`, `docs/UPGRADE_V08_TO_V09.md`, `docs/DEVELOPMENT_ROADMAP_API_V09.md`, `docs/TEST_REPORT_V09.md`.

## v0.7: 프로젝트 미리보기 · 인수 준비 · 문의 · 알림

- **프로젝트 미리보기:** 매물 초안 등록 후 JPG/PNG/WebP 이미지(최대 8장)·대표 이미지·이미지 설명·HTTPS 시연 URL·YouTube/Vimeo 영상·주요 기능 8개 등록. 판매자가 수정한 공개 매물은 관리자 재검토가 필요합니다.
- **인수 준비 보고서:** GitHub/ZIP 정적 분석에서 README·배포·잠금 파일·환경변수 템플릿·테스트·DB·라이선스·CI를 체크리스트로 표시. 실제 실행 검증이나 라이선스 인증은 수행하지 않습니다. 기존 v0.6 소스도 판매자가 재분석할 수 있습니다.
- **프로젝트 문의:** 구매자 공개/비공개 문의, 판매자 답변, 각자 문의함, 문의 발생/답변 알림. 비공개 문의는 질문자·판매자·관리자에게만 표시.
- **알림센터:** 헤더 알림과 내 활동 알림함, 읽음 처리·이메일 수신 설정. SMTP 알림은 저장형 outbox 및 별도 worker를 사용하며 실제 SMTP Secrets와 워커를 설정하지 않으면 내부 알림만 동작합니다.
- **DB 업그레이드:** `0005_marketplace_experience` (기존 데이터 유지). 업그레이드 전 PostgreSQL/App Storage 백업 필수.
- **문서:** `docs/RELEASE_NOTES_V07.md`, `docs/UPGRADE_V06_TO_V07.md`, `docs/EXPERIENCE_API_V07.md`.
- **검증 상태:** 새 기능·기존 백엔드 주요 테스트 통과. 이 작업 환경에서는 npm 패키지 다운로드 제한으로 React 실제 빌드를 완료하지 못했습니다. Replit에서 빌드와 운영 환경의 실제 이메일 수신 검증이 필요합니다.

## v0.6: GitHub/ZIP 자동 매물 등록

- 판매 등록에서 **GitHub 공개 저장소 URL / 연결된 GitHub App의 비공개 저장소 / ZIP 파일 / 직접 작성**을 선택할 수 있습니다.
- Python AST(실행하지 않음), 표준 manifest·폴더·README를 이용해 기술 스택/기능 단서를 추출하고 설명 초안을 작성합니다. 실제 동작·판매 권리·매출은 자동 검증하지 않습니다.
- 원본은 사용자 전용 임시 비공개 저장소에 고정된 소스 버전으로 보관하고, 매물 생성 시 단 한 번 `QUARANTINED` 소스로 연결합니다. 구매자에게는 개인정보나 원본 경로가 없는 정적 분석 요약만 공개됩니다.
- GitHub App은 Contents 읽기 전용 권한으로 구성하고, 토큰은 서버에서 암호화합니다. 운영용 GitHub Secrets 설정이 없으면 공개 GitHub URL 및 ZIP 등록만 이용할 수 있습니다.
- PostgreSQL Alembic head: `0004_project_imports`. **기존 v0.5 데이터베이스를 반드시 보존한 채 마이그레이션하세요.**
- 설치·환경설정·새 API·검증 결과: `docs/UPGRADE_V05_TO_V06.md`, `docs/PROJECT_IMPORT_API_V06.md`, `docs/TEST_REPORT_V06.md`.

## v0.4까지의 변경 이력

1. 플랫폼 자체의 **OpenAI 판매 도우미 UI/호출 라우트/백엔드 실행 로직/Secrets 설정 삭제**. API 키는 플랫폼에 필요하지 않습니다.
2. 기존 거래소 사용자 화면과 기능(회원, 매물, 검색, 찜, 제안, 협상, 비공개 첨부, 인수인계, 관리자)을 유지합니다.
3. 외부 에이전트 전용 `GET /api/v1/agent/listings/{listing_id}/preparation-context` 추가. 해당 판매자가 위임한 에이전트만 매물의 사실 정보를 확인합니다.
4. 공통 `agent-actions` 승인 흐름에 **`SUGGEST_LISTING_UPDATE`** 추가. 에이전트는 `expected_version` + `title`/`description`만 제안하며, 판매자가 반드시 검토·승인해야 합니다. 판매자 또는 위임받은 에이전트가 승인된 제안을 1회 반영할 수 있습니다. 가격·권리·매출·검증 상태 변경은 불가능합니다.
5. 공개 매물의 제목/설명이 변경되면 `PENDING_REVIEW`로 돌아가 관리자 재검토를 거칩니다. 사용자가 수정한 최신 버전과 충돌하면 이전 제안은 409로 거절됩니다.
6. 새로운 연동 스코프 `listing:draft`, `listing:execute`를 추가했습니다. 기존 API 스코프 및 토큰은 그대로 사용 가능하며, 별도 권한이 추가되지는 않습니다.
7. **이전 v0.3의 `listing_ai_drafts` 테이블은 데이터 보존을 위해 남겨둡니다.** 앱에서 조회·생성하지 않으며 이전 기록을 삭제하지 않습니다. 마이그레이션 이력(0003)은 그대로 유지합니다.
8. 기존 계약 경로 `/api/v1/listings/.../ai-assistant/*`는 제거되어 404를 반환합니다. 이 경로가 필요한 호출자는 새 `agent-actions` 흐름으로 전환해야 합니다.

## v0.5 에이전트 연동 안정화

- `Operations.tsx` 본인 매물 조회의 응답 형식(`[]`) 오류 수정 및 TypeScript 비밀번호 재설정 반환형 오류 수정.
- 판매자가 명시적으로 승인한 원본 목록을 조회하는 `GET /api/v1/agent/listings/{id}/inspection-assets` 추가. `asset:inspect`와 파일별·사용자별 만료/철회 검증 필요.
- 구매자 위임 에이전트는 승인된 파일의 SHA-256을 포함할 때 해당 매물의 **비공개** 실사 보고서를 제출 가능. 타인의 비공개 보고서 조회 불가.
- `POST /api/v1/agent-actions`, `POST /api/v1/agent-actions/{id}/execute`, `POST /api/v1/listings/{id}/inspection-reports`의 `Idempotency-Key` 재시도 지원.
- `AGENT_WRITE_MODE=disabled`(운영 기본값): 에이전트는 읽기·초안 제출만 가능. `demo_only`: **DEMO 매물에 한해** 사람이 승인한 작업을 위임 토큰으로 실행. 실제 거래 매물의 에이전트 실행은 지원하지 않음. `live`를 설정하더라도 무조건 차단(fail closed).
- URL 계약: `MARKETPLACE_API_URL=https://실제-도메인`(권장, `/api/v1` 중복 불가), Streamlit 예제는 이전 `/api/v1` 포함 주소도 한 번 정규화.
- 조회 테스트: `python scripts/smoke_agent_api.py`. 단, 실제 HTTPS 검사는 사용자 Replit URL과 위임 토큰이 필요한 별도 단계임.
- v0.5에서는 **DB 스키마 변경 없음**. 기존 Alembic head는 `0003_inspection_ai_drafts`이며 업그레이드 시 DB를 삭제하지 말 것.

자세한 API·권한·연동 안내: `docs/AGENT_API_HANDOFF_V05.md`.

## 역할 구분

| 거래 플랫폼 | 외부 에이전트 |
|---|---|
| 거래 데이터·권한·증빙·승인·API | OpenAI 모델·추론·문서 작성·추천·협상안 생성 |
| 매물 등록 및 사람 승인 | API 조회·수정안 제안·검수 보고서 제출 |
| 비공개 ZIP 저장·제한된 제공 | 판매자 허가 후 안전한 별도 검사 환경에서 분석 |
| 거래/제안 상태 변경 기록 | 허용된 토큰으로 승인된 작업만 실행 |

**에이전트 개발 환경:** Python 3.12 + Streamlit + LangChain. Streamlit은 `python -m streamlit run app.py` 하나로 실행하고 `requests`로 본 플랫폼의 HTTPS REST API를 직접 호출합니다. 추가 중계 서버를 이 플랫폼에 배포할 필요가 없습니다.

## 구현된 플랫폼

- **React + TypeScript**: 한국어 반응형 매물 목록/필터/상세, 회원가입·로그인, 프로젝트 등록·수정, 구매 희망 조건, 찜, 제안/역제안/DEMO 거래, 거래 업무실, 관리자.
- **FastAPI**: 역할 기반 권한/CSRF/범위 제한 Bearer token, 매물과 거래 상태, 중복 제출 방지, 승인 워크플로, 감사 기록, 알림.
- **PostgreSQL + Alembic**: 배포용 데이터베이스와 `0001 → 0002 → 0003` 마이그레이션 유지. 기존 DB가 있으면 백업 후 `upgrade head`만 수행합니다.
- **파일 관리**: ZIP 등 비공개 저장·정적 구조 검사·관리자 검토·판매자 승인형 실사 권한·시연 구매자 한시 공유. 운영용 악성코드 검사는 별도 장비/설정 필요.
- **외부 에이전트 API**: 본인 매물 조회, 구매 조건 조회, 제안/역제안, 검사 보고서, 인수인계 요청, 매물 설명 수정 제안, 사용자 승인/실행.

## Replit Agent 없이 수동 설치

1. 이 ZIP의 내용(`backend`, `frontend`, `scripts`, `.replit`)을 **일반 Replit 파일 업로드 및 Shell**로 프로젝트 루트에 복사합니다. **작업 전 데이터베이스 백업** 필수. ZIP에는 실제 DB·비밀키가 포함되지 않습니다.
2. Replit Secrets에 `JWT_SECRET`(충분히 긴 무작위 키), `DATABASE_URL`(PostgreSQL)을 설정합니다. 신규 관리자가 필요하면 `ADMIN_EMAIL`, `ADMIN_PASSWORD`를 임시 설정하고 안내된 CLI로 생성합니다.
3. App Storage에서 **비공개 버킷을 직접 연결**하고 `PRIVATE_STORAGE_BACKEND=replit`을 설정합니다. 운영 환경에서는 ClamAV 등 악성코드 검사 없이 파일을 승인할 수 없습니다.
4. 일반 Replit Shell에서 `bash scripts/setup_replit.sh` 실행(가상환경 생성, 의존 패키지 설치, React 빌드, Alembic 마이그레이션).
5. 필요한 경우 `cd backend && ../.venv/bin/python -m app.cli` 로 관리자 생성 후, 루트에서 `bash scripts/run_replit.sh`로 실행합니다. 기본 포트 5000.
6. 접속 후 `/health`, `/docs`, `/api/v1/system/capabilities`와 회원/매물/DEMO 제안 과정을 확인합니다.
7. 별도 에이전트에서 발급받은 **제한 권한** Bearer 토큰으로 REST API를 호출합니다. 문서 `docs/AGENT_API_HANDOFF_V05.md`를 에이전트 개발 채팅에 전달할 수 있습니다.

**플랫폼에는 `OPENAI_API_KEY`, `OPENAI_MODEL` 등의 설정이 필요하지 않습니다.** 기존 Secrets에 등록된 OpenAI 키는 이 코드에서 사용하지 않으며 사용자가 Replit Secrets에서 직접 제거할 수 있습니다.

## 테스트와 보안상 제한

- 백엔드 테스트: `cd backend && python -m pytest -q` (사용자의 실 DB와 강제로 분리된 임시 SQLite). Python 구문 검사 및 API 명세 생성.
- 기존 v0.3 코드를 바탕으로 수정했으며 기존 데이터 삭제·스키마 변경이 없는 **코드 중심 업그레이드**입니다.
- **미검증:** 실제 React `npm run build`/브라우저 통합, Replit PostgreSQL·Storage·SMTP·ClamAV, 동시 거래·부하 및 상용 결제/법무 검토.
- **금지:** 서버에서 사용자 업로드 ZIP을 직접 실행하지 말 것. 플랫폼이 자동 실사 PASS나 매출 검증 완료를 주장하지 않도록 함.

**추가 문서:** `docs/AGENT_API_HANDOFF_V04.md`, `docs/TEST_REPORT_V04.md`, `docs/UPGRADE_V03_TO_V04.md`, `contracts/implemented-openapi-v04.json`.

## v0.5 검증 및 업그레이드 문서

- `docs/INTEGRATION_TEST_REPORT_V05.md` — 실제 통과/미검증 영역.
- `docs/UPGRADE_V04_TO_V05.md` — 기존 Replit DB를 유지하는 수동 적용법.
- `docs/AGENT_API_HANDOFF_V05.md` — 에이전트 개발 채팅 공유용 API 계약.
- `contracts/implemented-openapi-v05.json` — 실제 FastAPI 생성 스냅샷. v0.4 버전은 과거 기록.


## v0.8 거래 관리 (시연 전용)

고정 조건 기록·양측 확인·시연용 조건서 다운로드·쌍방 취소 합의·분쟁 처리·관리자 거래 이력 조회가 추가됐습니다. 실제 결제, 정산, 전자서명 또는 권리 이전은 구현하지 않았습니다. `docs/RELEASE_NOTES_V08.md`, `docs/UPGRADE_V07_TO_V08.md`, `docs/DEAL_API_V08.md` 참고.

## ProjectAgain v0.10 — UX 정비

매물 등록 자동 임시저장·복구 및 단계 검증, 탐색 검색 최적화, 매물 핵심 정보 요약, 거래 진행 안내, 대화상자·접근성·디자인 시스템을 개선했습니다. 기존 API·DB 구조는 v0.9와 동일하며 실제 결제는 여전히 지원하지 않습니다. 설치 지침은 `docs/UPGRADE_V09_TO_V10.md`, 수정 내용은 `docs/RELEASE_NOTES_V10.md`, 브라우저 검증 항목은 `docs/UX_ACCEPTANCE_V10.md`를 참조하세요.

## v0.13 개인정보 관리 및 인수 보고서

- `/settings`에서 본인 비밀번호를 다시 입력해 회원 탈퇴 및 데이터 삭제 요청 가능 (관리자 제외).
- 모든 매물은 `/api/v1/listings/{id}/takeover-report`에서 **소스 미제출 시에도** 인수 준비 보고서를 제공.
- GitHub Actions의 커밋 SHA 고정 CI 실행 결과는 증거로만 관측; 업로드 소스 직접 실행 없음.
- 개인정보 파일 저장소 삭제는 `bash scripts/run_notification_worker.sh` 운영 시 함께 처리; 긴급 재시도 `bash scripts/cleanup_privacy_objects.sh`.
- Replit 수동 업그레이드는 `docs/UPGRADE_V12_TO_V13.md`, 검증은 `docs/TEST_REPORT_V13.md` 참조.
