# ProjectAgain v0.12 — 테스트 기록

작업 환경: Python 3.13 / pytest 9 / FastAPI TestClient / 임시 SQLite / TypeScript 구문 파서. 테스트는 사용자 운영 DB에서 절대 실행하지 않는 `backend/tests/conftest.py` 분리 DB를 사용.

## 실제 검증 결과

| 항목 | 결과 |
|---|---|
| v0.12 통합 기능 5건 + v0.8 거래 관리 8건 + v0.9 로드맵 9건 | **22 PASS** |
| v0.7 매물·알림·Phase2 테스트 | **19 PASS** |
| 에이전트 매물 제안, 실사 권한, v0.5 연동, 소스 가져오기 | **25 PASS** |
| 기존 일반 거래/인증/안전성 16건 | **16 PASS** (이메일 인증 테스트는 분리 실행) |
| 합계 | **82개 테스트 통과**, 기능별 분할 실행 |
| Python 구문 검사 | **PASS** (`python -m compileall -q app`) |
| React TS/TSX 구문 파싱 | **PASS**, 정식 타입 체크/번들 빌드 아님 |
| v0.11 이전 DB → v0.12 마이그레이션 | **PASS** (독립 SQLite 0007 → 0008; 사용자 2, 매물 1, 제안 1, 거래 1 유지, 이전 제안 스레드 연결) |
| 처음부터 신규 DB 설치 | **PASS** (SQLite 0001 → 0008) |

실행 명령 예시:

```bash
cd backend
python -m pytest -q tests/test_integrated_workspace_v012.py tests/test_deal_management_v08.py tests/test_development_roadmap_v09.py
python -m pytest -q tests/test_marketplace_v07.py tests/test_notification_unread_v11.py tests/test_phase2.py
python -m pytest -q tests/test_agent_listing_proposals.py tests/test_inspection_access.py tests/test_integration_v05.py tests/test_project_imports.py
python -m pytest -q tests/test_workflows.py
python -m compileall -q app
```

**주의:** 전체 82개를 단일 `pytest -q` 명령으로 묶는 시도는 이 실행 환경에서 시간 제한에 걸렸습니다. 각 파일/기능 그룹을 나눠 실행한 경우 위 항목이 통과했습니다. 하나의 테스트 세션과 실제 PostgreSQL에서 동일하게 동작한다고 보장하지 않습니다.

## 미검증 항목 / 배포 전 필수

- **프론트엔드 정식 `npm run build`: 미검증.** 이 실행 환경에서 Node 패키지 저장소 접근이 불가능하고 `node_modules/vite/client` 등 의존성이 설치되지 않아 TS2688 오류. React TSX 소스 구문 검사는 통과했지만 타입 검증·번들 생성·실제 브라우저 렌더링은 별도 확인해야 함.
- **PostgreSQL 운영 마이그레이션:** v0.11 SQLite에서 업그레이드 검증했으나 실제 Replit PostgreSQL 및 장기 운영 데이터는 미검증.
- **동시성/잠금:** PostgreSQL의 동시 판매 수락, 문의 한도 동시 신청, 낙관적 버전 충돌, 다중 작업자·중복 알림은 부하 테스트 전.
- **외부 연동:** GitHub App 권한·비공개 저장소, Replit Storage, SMTP 실전송, 배포된 Streamlit 에이전트 HTTPS, 악성코드 검사 엔진 연결 미검증.
- **UI/운영:** 모바일·접근성, UI 전체 클릭 동선, 실제 SMTP 신규 사용자 이메일 인증, 과거 RESERVED/CLOSED 매물 감사/복구, 백업 복구, 관리 정책 및 개인정보 준수 확인 필요.
- **기능 제한:** 지원 첨부파일 비활성화; 실제 결제/에스크로/계약·권리 이전 없음.
