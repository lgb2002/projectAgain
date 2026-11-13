# ProjectAgain v0.5 연동 안정화 검증 보고

작성 기준: 2026-11-12, ChatGPT 로컬 작업 공간에서 **v0.4 전체 소스를 복제 후 수정**.

## 수정 내용

- 프론트엔드 본인 매물 조회 결과를 실제 백엔드의 배열 응답으로 변경.
- 이전에 Replit에서 수동 수정했던 `Operations.tsx` 비밀번호 재설정의 TypeScript 타입 오류도 포함해 수정.
- 판매자 승인된 비공개 실사 대상 파일 목록 API 추가(권한·기간·철회 검사).
- 구매자 에이전트의 비공개 실사 결과 제출 허용: 정확한 원본 SHA-256·동의·유효 권한이 요구됨. 구매자 보고서의 판매자 임의 공개 차단.
- 초안 생성·실행·실사 보고서 제출의 중복 요청 방지 추가.
- `AGENT_WRITE_MODE` 안전 차단: 개발 테스트에서만 암묵적 `demo_only`; 일반 개발·운영에서는 기본 `disabled`; 운영에서 명시 `demo_only`면 DEMO만 실행 가능, 비시연 매물에는 차단.
- API Base URL 정규화 예제, 오프셋 페이지 처리, null 필드 계약, 안전한 읽기 전용 HTTP 점검 스크립트 추가.
- 플랫폼의 OpenAI 호출 없음. Replit Agent 호출 없음.

## 실제 실행한 테스트

| 범위 | 통과 | 방법 |
|---|---:|---|
| `test_workflows.py` | 16/16 | 개별 pytest 실행 |
| `test_phase2.py` | 9/9 | 개별 pytest 실행 |
| `test_inspection_access.py` + `test_agent_listing_proposals.py` | 13/13 | 개별 pytest 실행 |
| 신규 `test_integration_v05.py` | 5/5 | 개별 pytest 실행 |
| **합계** | **43/43** | 각 묶음은 정상 종료 |

**주의:** 테스트 전체를 한 번의 pytest 프로세스로 묶어 실행하면 36개 이상 진행 후 장시간 정체되는 문제가 재발함. 따라서 '단일 전체 테스트 명령 성공'으로 보고하지 않음. 실제 위 파일별 통과 기록을 근거로 함.

### 실제 TCP/HTTP 서버 통신 검증

- 로컬 임시 SQLite DB에 테이블을 생성하고 `uvicorn`을 `127.0.0.1:18764`에서 실행.
- `GET /health`, `GET /api/v1/system/capabilities`, `GET /api/v1/listings?...`: 모두 HTTP 200.
- 로컬 서버 OpenAPI `/openapi.json` 응답: 버전 `0.5.0`, 총 66개 경로(메서드 개수 아님). 신규 승인 파일 목록, 에이전트 초안·보고서 API 경로 확인.

## 아직 검증하지 못한 영역

1. **실제 Replit HTTPS URL ↔ Streamlit v0.5 소스**: 플랫폼의 외부 주소·유효 위임 토큰·에이전트 원본 소스가 없어 미검증. 반드시 다른 네트워크에서 `scripts/smoke_agent_api.py` 실행.
2. React 실제 `npm run build`: 본 작업 환경은 npm 캐시가 없고 네트워크 레지스트리 접근이 제한됨. TypeScript 소스 수정은 반영했지만 실제 빌드 미검증. 사용자가 Replit에서 이미 수정·빌드한 v0.4를 기반으로 업데이트 후 재빌드 필요.
3. 실제 Replit PostgreSQL DB·비공개 Storage 통합, CORS/쿠키, SMTP, 악성코드 검사 도구.
4. 실제 위임 토큰을 포함한 인터넷 경유 E2E; OAuth/JWT 검증이 아닌 플랫폼 내부 불투명 토큰을 사용.
5. **부하·경합/장시간 페이지 탐색**: 문자열 오프셋 페이지는 삽입/삭제 시 중복 또는 누락될 수 있어 안정적인 스냅샷을 보장하지 않음.
6. 실제 결제·계약·소유권 이전은 미구현. 에이전트에 실제 거래 쓰기 허용 금지.

## 개발·배포 관련 주의

- 기존 PostgreSQL 데이터베이스 **삭제 및 초기화 금지**. v0.5에서 DB 모델 및 Alembic head 변경 없음.
- 웹서버 설정·기존 Secrets 그대로 유지. 새 기본값 `AGENT_WRITE_MODE=disabled`; DEMO 자동 실행을 시연할 때만 `demo_only`.
- `.env` 파일과 비밀값은 ZIP에 없음. 실제 토큰은 문서/채팅에 복사하지 말 것.
- 파일 내 악성 코드 실행 금지. 자동 검사가 이 버전에서 도입된 것으로 오해하지 말 것.
- Replit Agent/Max Mode/자동 배포 도구 사용 금지. Shell과 파일 업로드로만 수동 반영.
