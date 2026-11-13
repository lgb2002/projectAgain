# ProjectAgain v0.9 검증 기록

## 백엔드 테스트
총 76개 테스트 수집. 테스트를 서로 다른 실행 그룹으로 나누어 모두 통과.

| 그룹 | 테스트 파일 | 통과 |
|---|---|---:|
| 신규 로드맵 | `test_development_roadmap_v09.py` | 9 |
| 기술 분석·프로젝트 미리보기·거래 계약 | `test_marketplace_v07.py`, `test_project_imports.py`, `test_deal_management_v08.py` | 24 |
| 이전 연동·개인정보·에이전트 | `test_phase2.py`, `test_integration_v05.py`, `test_agent_listing_proposals.py` | 23 |
| 기존 거래 워크플로·실사 | `test_workflows.py`, `test_inspection_access.py` | 20 |
| **합계** | | **76** |

한 번에 모든 테스트를 실행한 경우 일부 기존 테스트 구간이 시간 제한에 걸렸으므로,
이 결과는 **기능별 그룹 테스트** 결과이며 전 모듈을 동일 프로세스에서
완료한 결과를 의미하지 않습니다.

### v0.9에서 직접 확인한 행동
- 공개 예정 로드맵의 매물 공개 범위 (비공개/RESERVED 접근 차단)
- 구매자 외 개인 로드맵 조회·생성 차단, 인계 완료 전 생성 차단
- 인수 완료 후 재생성 호출 시 기존 진행표와 내역 보존
- 선행 작업 미완료 시 후속 작업 진행/완료 차단, 선행 작업 되돌리기 제한
- optimistic concurrency(version)와 잘못된 status 값 거부
- 구매자 개인 작업 추가·선행 관계 검사·교차 사용자 접근 제한
- 매물 변경 시 원본 진행표 보존 및 변경 경고
- 콘텐츠 자산에는 서버 빌드 절차가 강제되지 않음
- AI 에이전트/게임 유형에 맞는 점검 작업 추가

### 마이그레이션
기존 v0.8 마이그레이션까지 올라간 격리 SQLite DB에서 계정+매물을
생성한 뒤 v0.9로 업그레이드하였습니다.
기존 행 보존 및 새로운 2개 테이블(`development_roadmaps`,
`development_roadmap_tasks`) 생성 확인. 운영 PostgreSQL은 별도 실환경 확인 필요.

### 구문 검사
- Python `compileall`: 통과
- React/TypeScript TSX 구문 변환 검사: 통과
- FastAPI OpenAPI 스냅샷 생성: `contracts/implemented-openapi-v09.json`

## 검증되지 않은 영역
- 이 환경의 npm 의존성 설치 오류(`Exit handler never called!`) 때문에
  공식 `npm run build`는 `vite/client` 타입 누락 상태에서 중단되었습니다.
  **정식 React 컴파일 및 브라우저 통합 검증은 Replit에서 필수입니다.**
- 운영 PostgreSQL/Storage, 실제 GitHub OAuth·SMTP 알림, 모바일 실기기 UX.
- 사용자 소스 실행, 재배포 성공, 전문가 인증, 법적 권리 확인, 실결제 또는 소유권 이전.

## 적용 시 권장 점검
1. 구매 전 매물 상세의 예상 로드맵과 작업 근거가 정상 표시되는지 확인.
2. 시연 거래의 인수 완료 전/후 구매자 접근 및 작업 상태 갱신 확인.
3. 2계정으로 판매자/타인 접근 차단 확인.
4. DB에 원본 파일이나 API 키가 로드맵에 기록되지 않았는지 확인.
5. Replit `npm run build` 및 정적 자산 제공 확인.
