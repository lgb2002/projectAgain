# API 계약 상태 — v0.9 기준

현재 FastAPI 구현 계약은 `contracts/implemented-openapi-v09.json`이며,
`contracts/design-openapi-v1.yaml`은 장기 설계 참고 자료입니다.

새로운 로드맵 API는 `docs/DEVELOPMENT_ROADMAP_API_V09.md` 참고.
매물 상세의 미리보기는 공개 범위에 한정되며 개인 진행표는 **시연 인계가 완료된 구매자만** 접근합니다.

외부 AI 에이전트와 플랫폼 역할 분리, 플랫폼 자체 LLM 비사용, 인간 승인 정책은 유지합니다.
기존 API와 v0.8 거래 관리 계약은 호환성을 위해 보존했습니다.

실제 결제·대금보호·소유권 이전은 여전히 지원하지 않습니다.
