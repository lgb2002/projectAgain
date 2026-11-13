# v0.12 API 변경/추가 목록

모든 경로는 `/api/v1` 아래이며 사용자 세션·CSRF 규칙은 v0.11과 동일합니다. 외부 에이전트 전용 스코프에는 새 권한을 자동 부여하지 않습니다.

| 메서드 | 경로 | 접근/설명 |
|---|---|---|
| GET | `/listings/{id}/offer-terms-template` | 로그인한 제3자 구매자. 새 구조화 조건 초안, 매물 버전 |
| GET | `/offer-threads/{id}` | 해당 거래의 구매자/판매자. 협상 이력, 전후 변경 비교, V1/V2 표기 |
| POST | `/offer-threads/{id}/counter` | 거래 상대방. `expected_version`, 새로운 V2 `terms` 등 |
| POST | `/offer-threads/{id}/accept` | 현재 제안의 상대방. `expected_version` 필요 |
| GET | `/transactions/{id}/workspace` | 해당 시연 거래 당사자. 통합 진행 정보 |
| GET | `/transactions/{id}/support-policy` | 해당 시연 거래 당사자. 합의 당시 고정된 지원 기간/잔여 건수 |
| GET/POST | `/transactions/{id}/support-cases` | 당사자 조회; DEMO 인수 완료한 구매자만 신규 요청 |
| GET | `/transactions/{id}/support-cases/{case_id}` | 당사자. 개별 문의·메시지 |
| POST | `/transactions/{id}/support-cases/{case_id}/messages` | 당사자. `body`, `expected_version`, `attachment_refs: []` |
| POST | `/transactions/{id}/support-cases/{case_id}/resolve` | 구매자만. `expected_version` |
| POST | `/transactions/{id}/support-cases/{case_id}/escalate` | 당사자. 관리자로 전달, 본문 필요 |
| POST | `/transactions/{id}/support-cases/{case_id}/coverage` | 판매자. 범위 재검토, 누락·권리 건 일반 지원 재분류 금지 |
| POST | `/transactions/{id}/roadmap/tasks/{task_id}/support-cases` | 완료된 시연 인수의 구매자. 로드맵 작업과 문의 연결 |
| PATCH | `/transactions/{id}/roadmap/buyer-context` | 구매자. 스킬/목표/안내 선호, `expected_version` |
| GET | `/admin/support-cases` | ADMIN. 관리자 검토 대기 목록 |
| GET | `/admin/support-cases/{case_id}` | ADMIN. 검토 대상 내용/메시지 |
| POST | `/admin/support-cases/{case_id}/decision` | ADMIN. REQUEST_INFO 또는 CLOSE_UNRESOLVED + 사유 + 버전 |

### 구조화된 제안 필드

```json
{
  "schema_version": 2,
  "price_krw": 70000,
  "rights_type": "FULL_IP_ASSIGNMENT",
  "included_assets": ["소스코드"],
  "excluded_assets": ["API 키"],
  "handover_days": 7,
  "support": {
    "days": 7,
    "included_case_limit": 3,
    "scope_codes": ["SETUP_GUIDANCE", "EXISTING_FUNCTION_GUIDANCE"],
    "reply_goal_hours": 72,
    "is_reply_goal_guaranteed": false,
    "exceptions_note": "새 기능 개발 제외"
  },
  "buyer_conditions_note": "인수 문서 확인"
}
```

`offers` 전송 시 `offered_price_krw`는 `terms.price_krw`와 일치해야 합니다. `listing_version_at_proposal`은 서버가 기록합니다. 클라이언트는 거래 전 매물 정보가 바뀌면 409 후 최신 내용으로 재제안해야 합니다.

### 데이터 의미

- `schema_version`이 없는 이전 자유 형식 제안과 이미 체결한 약정은 조회·보존. 명시되지 않은 지원을 유추하지 않음.
- `support_policy_snapshots`는 합의 당시 조건 및 해시를 고정. 지원은 시연 인수 후 시작.
- `IN_SCOPE` 기술 문의만 건수 소진. `HANDOVER_REMEDY`(MISSING_ASSET, RIGHTS_CONCERN)은 별도 경로. `OUT_OF_SCOPE`는 추가 협의이며 금액 청구/계약 변경을 자동 수행하지 않음.
- 새 파일 첨부는 아직 불허(`attachment_refs`는 빈 배열만). 추후 보안 검증된 업로드 시스템과 결합 후 별도 설계.
- 지원 `reply_goal_hours`는 참고 목표이지 응답 SLA/환불 약속이 아님.
- 플랫폼은 결제·정산·저작재산권 이전·전자서명을 실행하지 않음.
