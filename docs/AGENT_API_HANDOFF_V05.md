# ProjectAgain v0.5 — Streamlit 에이전트 연동 인계 명세

## 구조

- ProjectAgain: Replit 별도 FastAPI + React + PostgreSQL 서버. 인증·매물·제안·보고서·승인·감사 기록의 유일한 원본.
- 에이전트: Python 3.12 + Streamlit 단일 실행(`python -m streamlit run app.py`). HTTP 클라이언트는 `requests`; 로컬 FastAPI/Mock 서버를 추가로 실행할 필요 없음.
- 플랫폼은 **LLM을 호출하지 않음**. AI 로직, API Key, 추론·추천·협상안 생성은 별도 에이전트 소유.
- 실제 결제, 권리 양도, 외부 코드 임의 실행 없음. 거래 관련 API는 데모 기록을 생성할 뿐 실거래 완료를 의미하지 않음.

## 주소 통일 — 가장 먼저 수정

정규 설정: `MARKETPLACE_API_URL=https://<ProjectAgain 서비스 실제 도메인>` (뒤에 `/api/v1` **붙이지 않음**).

플랫폼 라우트는 `/api/v1/...`; 에이전트 서비스 코드가 `host + /api/v1 + path` 방식이라면 환경변수에 다시 `/api/v1`을 넣지 말 것. 제공된 `integrations/streamlit_direct_api_example.py`는 이전처럼 `/api/v1`까지 포함해 준 주소도 자동 정규화함.

**Replit Preview URL과 실제 외부에서 접속 가능한 공개 HTTPS URL은 다를 수 있음**. Streamlit 실행 PC에서 `python scripts/smoke_agent_api.py`를 실행하여 `/health`, `/system/capabilities`, `/auth/me` 응답 검증. 주소나 토큰을 문서·로그·채팅에 적지 말 것.

## 사용자별 인증

- Bearer `MARKETPLACE_API_KEY`: 플랫폼에 로그인한 사용자가 `/api/v1/auth/agent-grants`에서 발급한 **불투명 난수 토큰**. 웹 로그인 세션 JWT와 다르며, 최대 24시간, 철회 가능, 사용자·scope 귀속.
- `Authorization: Bearer <token>` 사용. JWT 발급을 Streamlit에서 시도하지 않음.
- `GET /api/v1/auth/me`로 위임된 사용자 및 `scopes` 확인.
- 401 토큰 무효/만료, 403 권한 없음, 404 자원 접근 없음, 409 상태·버전 충돌, 422 형식 오류, 429 제한, 5xx 서버 오류. 응답 본문 `error.message`.
- 판매자와 구매자를 **서로 다른 계정·위임 토큰**으로 구분. 구매자 비공개 협상 한도를 판매자에게 공유하지 않음.

## 읽기/필드 계약

| 요청 | 실제 응답 | 접근 |
|---|---|---|
| `GET /api/v1/listings?include_demo=true&limit=24&cursor=0` | `{items:[...],next_cursor:"24" 또는 null,total_estimate:number}` | 공개 |
| `GET /api/v1/listings/{uuid}?include_demo=true` | Listing 객체 | 공개(활성 DEMO) |
| `GET /api/v1/my/listings` | **Listing[] 배열** (객체 `items`가 아님) | `listing:read` |
| `GET /api/v1/buyer-preferences/me` | 구매 조건 객체 | `buyer_profile:read` |
| `GET /api/v1/offers`, `GET /api/v1/offers/{uuid}` | `{items:[...]}`, Offer 객체; `proposed_by` 포함 | `offer:read`, 당사자 |
| `GET /api/v1/agent/listings/{uuid}/preparation-context` | `{listing:{...},authoritative_fields:[...],...}` | 판매자 `listing:read` |
| `GET /api/v1/agent/listings/{uuid}/inspection-assets` | `{items:[{id,file_name,size_bytes,checksum_sha256,approval_expires_at,...}],next_cursor:null}` | `asset:inspect` + 사전 승인 |
| `GET /api/v1/agent/assets/{asset_uuid}/inspection-content` | `application/octet-stream` 원본 | `asset:inspect` + 사전 승인 |
| `GET /api/v1/listings/{uuid}/inspection-reports` | `{items:[...]}`; 공개 보고서 + 본인 보고서 | `inspection:read` |
| `GET /api/v1/agent-actions/{id}` | Action 객체 | 해당 초안 scope |

- 목록 `next_cursor`는 **문자열 형태의 정수 오프셋**(예: `"24"`) 또는 `null`. 다음 호출의 `cursor` 값은 정수로 전달. 최대 100건/요청. 중간에 매물이 추가되면 오프셋 페이지가 중복·누락될 수 있으므로 `id` 기준 중복 제거하고, 정합성이 중요한 작업은 상세 UUID를 다시 조회.
- `monthly_cost_estimate_krw`, `revenue_krw_claimed`, `handover_days_estimate`, `seller_support_days` 등 미확인 값은 `null`일 수 있음. `known_defects=[]`는 **기재된 결함이 없음**이지 결함이 없다는 검증이 아님.
- 원 단위 금액은 정수(`price_krw`, `offered_price_krw`), 날짜 ISO8601 타임존 포함. 코드/설명으로부터 미확인 매출·권리를 확정하지 않음.

## 비공개 실사와 보고서

1. 판매자가 ZIP을 업로드(격리 상태)하고, 관리자에게 파일 검토 승인받음(운영에서는 바이러스 검사 CLEAN 필수).
2. 판매자가 검사 대상 **사용자 ID / 파일 ID / 검사 목적 / 만료 시간**을 지정하여 승인.
3. 해당 사용자로 발급된 `asset:inspect` 위임 토큰으로 `GET /agent/listings/{id}/inspection-assets` 호출. **승인된 파일만 목록에 나타남.**
4. 각 파일에 대해 `/agent/assets/{asset_id}/inspection-content`를 내려받고 응답 데이터 SHA-256이 목록의 해시와 동일한지 에이전트가 다시 확인.
5. 파일은 별도의 안전한 격리 환경에서만 검사. 개인 PC/플랫폼 서버에서 업로드 소스코드를 무단 실행하지 않음.
6. 구매자 측 위임 에이전트는 `inspection:write` 토큰과 **해당 판매자 승인 파일의 정확한 `source_version_sha256`**을 넣어 `POST /listings/{id}/inspection-reports` 제출 가능. 초기 보고서는 `is_public=false`이며 플랫폼의 인증/법률 판단이 아님. 허가가 만료/철회되면 추가 제출 금지.
7. 비공개 보고서는 판매자·관리자·**제출한 구매자 본인**만 열람할 수 있음. 다른 구매자는 공개된 보고서만 읽음.

## 승인 및 멱등성

- `POST /agent-actions`: `action_type`, `resource_id`, `proposed_payload`, `payload_sha256`(공백 없이 키 정렬 JSON UTF-8 SHA-256), `expires_at`(ISO8601).
- 초안 작성은 데이터를 직접 변경하지 않고 사람 승인 대기 상태를 생성.
- 승인·거절 API (`POST /agent-actions/{id}/approve|reject`)는 **웹에 로그인한 사람의 세션+CSRF로만** 요청 가능. 에이전트 토큰은 승인 불가.
- 실행 (`POST /agent-actions/{id}/execute`)은 승인 및 해시·상태·버전 재검증을 거침. 환경변수 `AGENT_WRITE_MODE=disabled`가 기본값으로, 에이전트가 실제 실행 불가. 개발 테스트에서 `demo_only`로 명시 변경하면 **DEMO 매물/DEMO 거래만** 실행 가능. 실제 매물에 대한 에이전트 쓰기는 구현되지 않았음.
- `Idempotency-Key`: 8~128자 문자열. 동일 사용자·라우트·키·요청 본문으로 재전송 시 동일 응답. 같은 키로 본문 변경 시 409. 적용: `POST /agent-actions`, `POST /agent-actions/{id}/execute`, `POST /listings/{id}/inspection-reports`; 이전 offer 생성/역제안/수락에도 적용. 네트워크 재시도 시 **같은 키를 재사용**할 것.
- 승인된 작업이라도 요청 전 보고서 버전·판매 상태가 바뀌었으면 409가 날 수 있으므로 새 조회 후 초안을 다시 작성해야 함.
- 실제 계약/결제는 지원하지 않으며 사람 승인도 DEMO 거래 상태 기록의 승인임.

## Replit 배포·환경 검사

- React 빌드: `cd frontend && npm install && npm run build`.
- 플랫폼 루트에서 `bash scripts/setup_replit.sh` 후 `bash scripts/run_replit.sh`; Replit Agent 사용 금지.
- 서버 내부 `curl http://127.0.0.1:5000/health`; 외부 PC에서 HTTPS URL `/health`와 `/api/v1/system/capabilities` 확인.
- 테스트 환경: `APP_ENV=development`, `AGENT_WRITE_MODE=disabled` 권장. 시연 쓰기를 할 때만 `demo_only`를 명시하고 DEMO 매물로 작업.
- `https://.../docs`, `https://.../openapi.json`으로 실제 구현 API 확인. 설정된 DB/Storage는 별도 확인.
- 읽기 전용 자동 확인 스크립트 `scripts/smoke_agent_api.py` 제공. 토큰은 출력하지 않음.

## 수정 담당 구분

플랫폼 v0.5에서 수정: 프론트 배열 응답, 파일 목록, 구매자 실사 제출, 멱등성, 에이전트 쓰기 가드 및 기능 탐지 응답.
에이전트 v0.5에서 수정 필요: URL 정규화, 페이지네이션 커서/UUID, `null` 필드 방어, `include_demo=true`(시연 시), `Idempotency-Key`, 파일 목록 및 원본 해시 검증, 실데이터 쓰기 차단 준수. **에이전트 코드는 본 ZIP에서 수정하지 않았음.**
