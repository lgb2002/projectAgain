# 외부 에이전트 ↔ 플랫폼 API 연동 명세 (v0.4)

## 고정 구조

- **플랫폼**: Replit의 독립 FastAPI + React + PostgreSQL 서비스. AI 모델 호출 없음.
- **에이전트**: 사용자 PC에서 단일 Streamlit 프로세스, 자체 LangChain/OpenAI API 키 관리. 외부 네트워크의 플랫폼 HTTPS API로 직접 요청.
- API base: `MARKETPLACE_API_URL=https://<사용자가_배포한_도메인>/api/v1`.
- 토큰: 플랫폼에서 사람이 직접 발급한 `MARKETPLACE_API_KEY` Bearer. 최대 24시간, 필요 최소 범위 부여, 발급 이후 재조회 불가, 철회 가능.

## 필요한 API와 권한

| 작업 | 메서드·경로 | 스코프/주체 |
|---|---|---|
| 기능 지원 확인 | `GET /system/capabilities` | 공개 |
| 위임 사용자 확인 | `GET /agent/context` | Bearer |
| 공개 매물 검색 | `GET /listings?include_demo=true` | 공개 |
| 본인 매물 목록 | `GET /my/listings` | `listing:read` |
| 본인 매물의 판매 준비 정보 | `GET /agent/listings/{id}/preparation-context` | `listing:read`, 판매자 본인 위임 |
| 구매 희망 조건 | `GET /buyer-preferences/me` | `buyer_profile:read` |
| 비공개 소스코드 실사 | `GET /agent/assets/{asset_id}/inspection-content` | `asset:inspect` + 판매자의 파일별·시간별 승인 |
| 검사 보고서 제출 | `POST /listings/{id}/inspection-reports` | `inspection:write` 및 자원 권한 |
| 제안·역제안·판매자 보완 요청 초안 | `POST /agent-actions` | `offer:draft`/`handover:draft` |
| 매물 설명 수정 제안 | `POST /agent-actions` (`SUGGEST_LISTING_UPDATE`) | `listing:draft` |
| 제출 작업 상태 확인 | `GET /agent-actions/{id}` | 해당 작업 유형의 초안 권한 |
| 사용자 승인 | `POST /agent-actions/{id}/approve` | **브라우저에 로그인한 실제 사용자만** |
| 승인 작업 실행 | `POST /agent-actions/{id}/execute` | 작업 유형별 `*:execute` 또는 매물 수정은 실제 판매자 로그인 |

## 매물 설명 수정 초안 계약

외부 에이전트는 원본 정보를 읽어 제목과 설명의 수정안을 구성하되, **모델 추론·토큰 비용·사용자 동의 관리는 에이전트에서 자체 처리**합니다. 플랫폼이 LLM을 호출하거나 AI 초안을 생성하지 않습니다.

**작업 유형:** `SUGGEST_LISTING_UPDATE`.

초안 `proposed_payload` 형태:

```json
{
  "expected_version": 3,
  "title": "원본 기능이 확인된 일정관리 웹앱",
  "description": "일정 및 완료 체크 기능을 제공하는 웹앱입니다. 외부 서비스 설정이 필요하며, 운영 안정성은 별도 검증 대상입니다."
}
```

- 제목(2~120자) 또는 설명(30~25,000자) 중 하나 이상 필수. 그 외 **가격·권리·매출·검증 결과·매물 공개 상태·기술 정보 추가 불허**.
- `POST /agent-actions` 본문에 `action_type`, `resource_id=listing_id`, `proposed_payload`, `payload_sha256`, `expires_at` 포함.
- `payload_sha256` = JSON `ensure_ascii=False`, `sort_keys=True`, `separators=(',',':')`로 직렬화한 UTF-8 바이트의 SHA-256 소문자 16진수.
- `expires_at`은 미래 시각이며 최대 30일(통상 1시간 권장), 타임존 포함 ISO 8601.
- 생성 즉시 매물 수정되지 않음. 판매자가 플랫폼 UI의 작업 제안 화면에서 검토하여 승인 또는 거절.
- 승인된 작업은 에이전트의 `listing:execute` 또는 **판매자 로그인**으로 `/agent-actions/{id}/execute` 1회 실행. 다중 실행 409.
- 판매자가 그 사이 매물을 편집하면 버전 불일치 409. 새 정보로 다시 초안 생성해야 함.
- 공개 매물의 제목·설명이 바뀌면 자동으로 `PENDING_REVIEW` 상태가 되며 관리자 재승인 필요.
- 기존 플랫폼의 `/listings/{id}/ai-assistant/*`는 더 이상 제공되지 않음.

## 사람 승인과 안전 경계

- 외부 에이전트는 로그인/회원 탈퇴·결제·실권리 이전·계약 체결을 실행하지 않음.
- 비공개 ZIP은 별도 허가를 받은 자산만 열람하고, 사용자의 컴퓨터에서 임의 실행하지 않음.
- 검사 결과는 증거를 포함해야 하며 보안·법률적 인증으로 표시하지 않음.
- 서로 다른 사용자 위임 토큰으로 다른 사용자의 매물/비공개 거래/작업을 조회할 수 없음.
- 사용자에게 공개하는 마켓플레이스 화면에는 AI 모델 호출 버튼이 없음. 플랫폼 Secrets에 OpenAI 키를 설정하지 않음.

## 에이전트 코드 참고

`integrations/streamlit_direct_api_example.py`에 `MarketplaceAPI` Python requests 예시를 제공함. 이 파일은 예시이며 에이전트 환경에만 복사해서 사용하면 됨. 별도의 Agent API 서버 실행 불필요.
