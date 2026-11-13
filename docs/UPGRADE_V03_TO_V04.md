# v0.3 → v0.4 무손실 업그레이드 원칙

1. **DB 백업을 먼저 만들고**, 소스 파일만 v0.4 전체 ZIP으로 교체한다. 기존 DB 삭제·새 DB 복사·초기화 금지.
2. Alembic 버전은 `0003_inspection_ai_drafts` 그대로이며 기존 적용된 DB에 새로운 마이그레이션이 필요하지 않다. 새로운 활성 테이블 없음.
3. 과거 `listing_ai_drafts` 레코드는 **임의 삭제하지 않는다.** 해당 테이블과 ORM 정의는 마이그레이션 호환과 과거 데이터 보존 목적으로만 남겨두며 사용자 기능과 API에서는 사용하지 않는다.
4. 이전 `ai-assistant` API 세 경로와 UI는 완전히 제거한다. 사용자는 별도 에이전트에서 생성한 제안을 `agent-actions`로 제출해야 한다.
5. 새로운 `listing:draft`, `listing:execute` scope는 신규 토큰 발급 시만 부여할 수 있다. 기존 발급 토큰의 범위는 변경되지 않는다.
6. 플랫폼 Secrets의 OpenAI 환경변수는 **더는 사용하지 않는다**. 키는 Replit Secrets에서 사용자가 직접 제거하고, 별도 에이전트 환경에만 관리한다.
7. 완성·공개된 매물에 제안 수정안이 반영되면 `PENDING_REVIEW`로 변경된다. 재심사 정책 변경 금지.
8. PostgreSQL 및 App Storage 실제 데이터·권한·동시성 검증은 수동 배포 환경에서 별도 진행한다.
9. Replit Agent/Max Mode 또는 자동 코딩 연동은 호출하지 않는다.
