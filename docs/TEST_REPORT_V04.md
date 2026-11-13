# v0.4 API-only 변경 테스트 및 미검증 영역

## 대상

- 판매 도우미 UI/서버 OpenAI 호출 제거.
- 외부 에이전트의 `SUGGEST_LISTING_UPDATE` 초안 → 사용자 승인 → 1회 반영.
- 기존 판매자·매수자 거래 흐름/비공개 파일 공유/검사 접근/인수인계 보안 회귀.

## 정량 검사

- `tests/test_agent_listing_proposals.py`: 9건 모두 통과.
- `tests/test_inspection_access.py` + `tests/test_phase2.py`: 13건 모두 통과.
- `tests/test_workflows.py`: 16건 모두 통과.
- **합계 38개 테스트**, 각각의 독립 테스트 묶음에서 모두 통과. 통합 일괄 실행은 이 컨테이너에서 제한 시간 내 종료하지 못하므로 일괄 완료로 표시하지 않는다.
- 테스트는 외부 DB와 격리된 임시 SQLite에서 실행. Python 컴파일, OpenAPI 생성, TS 구문 검사 별도.

## 특히 확인한 보안 성질

- 플랫폼에서 OpenAI 호출 경로 제거 및 Secret 미사용.
- 에이전트 Bearer 토큰의 `listing:read`/`listing:draft`/`listing:execute` 범위 분리.
- 판매자 위임 토큰만 자기 매물의 수정안 제안 가능. 판매 가격·권리·검증 상태 변경 거부.
- 승인 전 실행 거부, 사용자 거절 후 실행 거부, 승인된 요청 1회 실행, 오래된 매물 버전 충돌 거부.
- 공개 매물 수정 시 관리자 재검토로 전환, 기존 비공개 파일 접근 정책 유지.

## 배포 전 확인 필요

- **React 전체 의존성 설치·`npm run build`·브라우저 시각/E2E 테스트 미완료** (현재 npm 레지스트리 접속 불가).
- 실제 PostgreSQL DB·Replit App Storage·ClamAV·SMTP 연동 미검증.
- 병렬 실거래 경합, 외부 코드 실행 안전성, 실제 결제·에스크로·권리 양도는 구현/검증 대상이 아님.
- 외부 에이전트의 실제 OpenAI 모델 동작, 비용, 장기 작업 및 자동 코딩은 이 플랫폼 테스트 대상이 아님.
