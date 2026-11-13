# v0.8 거래 관리 API (`/api/v1`)

전제: 로그인한 **사람의 세션 + CSRF**. 에이전트 Bearer 토큰으로 생성/확인/분쟁 관리를 수행할 수 없음.
모든 기능은 **DEMO 거래 전용**, 실제 금액 청구·정산·환불·전자계약 불가.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/transactions/{id}/agreement` | 고정된 조건·확인 시각 조회 |
| POST | `/transactions/{id}/agreement/prepare` | 업그레이드 이전 거래의 조건 기록 준비(최초 1회) |
| POST | `/transactions/{id}/agreement/acknowledge` | 본인 확인 시각·스냅샷 해시 기록 |
| GET | `/transactions/{id}/agreement/document` | UTF-8 텍스트 시연 조건 확인서 다운로드 |
| GET | `/transactions/{id}/deal-events` | 거래 이력 (당사자만) |
| GET | `/transactions/{id}/cancellations` | 취소 요청 이력 |
| POST | `/transactions/{id}/cancellations` | 상대방에게 취소 요청 |
| POST | `/transactions/{id}/cancellations/{request_id}/respond` | 상대방만 동의·거절 |
| GET | `/transactions/{id}/disputes` | 당사자 분쟁 조회 |
| POST | `/transactions/{id}/disputes` | 분쟁 접수 및 거래 일시 중단 |
| POST | `/transactions/{id}/disputes/{dispute_id}/respond` | 상대방의 1회 답변 |
| GET | `/admin/deal-transactions` | 관리자 거래 목록 |
| GET | `/admin/deal-transactions/{id}` | 관리자 거래 조건·취소·분쟁·이력 조회 |
| GET | `/admin/deal-disputes` | 관리자 분쟁 목록 |
| POST | `/admin/deal-disputes/{dispute_id}/decide` | 관리자만 인계 재개 또는 모의 취소 결정 |

## 조건 확인 요청 예제

```json
{
  "snapshot_sha256": "<GET /transactions/{id}/agreement 에서 받은 64자리 해시>",
  "understood_demo_only": true,
  "confirmed_terms": true
}
```

신규 거래는 매수/매도 제안 수락 시 고정 기록이 자동 생성된다. `agreement.status`가 `ACKNOWLEDGED`가 될 때까지 해당 거래의 인계 상태 변경과 원본 자료 공유를 차단한다. 기존에 생성된 자료 다운로드 티켓은 사용 시 다시 파일 접근 권한을 확인한다.

## 취소 요청

`POST /transactions/{id}/cancellations`: `{"reason":"취소 사유 10자 이상"}`

`POST /transactions/{id}/cancellations/{request_id}/respond`: `{"accept":true,"response_note":"취소 결정에 대한 설명 5자 이상"}`

신청자와 동일한 사용자/제3자는 승인할 수 없다. 승인 시 예약 해제·자료 공유 철회. 이미 다운로드된 파일은 회수할 수 없다.

## 분쟁

`POST /transactions/{id}/disputes`:

```json
{
  "reason_code":"MISSING_ASSET",
  "description":"계약상 포함된 소스 파일이 누락되어 있습니다.",
  "evidence_refs":[]
}
```

사유: `MISSING_ASSET`, `MISREPRESENTATION`, `RIGHTS_CONCERN`, `HANDOVER_DELAY`, `OTHER`.
`evidence_refs`는 사용자가 주장하는 참조 문자열로, **증빙이 검증되었다는 의미가 아니다.** 실제 자료를 올리고 검증하려면 기존 파일 업로드·관리자 검토 흐름을 사용한다.

관리자 `POST /admin/deal-disputes/{dispute_id}/decide`:

```json
{"decision":"RESUME_HANDOVER","reason":"조사 결과 및 판단 근거 15자 이상"}
```

또는 `CANCEL_DEMO`. 관리자 본인 또는 당사자가 스스로 분쟁을 결정할 수 없다. 이 결정은 사이트 내 모의 상태 변경이며 법적 분쟁의 강제 해결이나 대금 환불이 아니다.

## 동시성·오류

- 거래 및 계약 기록 변경은 단일 DB 트랜잭션에서 커밋하며 PostgreSQL 트랜잭션 행 잠금 사용.
- 제3자 조회는 원칙적으로 404, 처리 권한 없는 행위는 403, 중복/충돌·잘못된 상태 변경은 409.
- 모든 민감 내용은 인증된 당사자와 관리자로 제한. 거래 이벤트 데이터는 최소한의 상태·식별자만 포함.
- 실결제 API 또는 공개 결제 URL 없음.
