# Replit에서 ProjectAgain v0.11 → v0.12 안전하게 적용

**ZIP은 전체 소스이며 DB나 비밀키를 포함하지 않습니다.** 운영/시연 데이터베이스를 초기화하면 안 됩니다. Replit Agent 없이 일반 Shell에서 실행합니다.

## 배포 전 필수 백업

1. 현재 v0.11 프로젝트 및 Replit Secrets 값(보안 저장소를 통해 별도 보관)을 확인합니다. 새 ZIP을 기존 환경에 바로 덮어쓰기 전 소스 폴더를 백업합니다.
2. **PostgreSQL 전체 백업**: 관리형 DB 제공자의 Snapshot 기능 사용을 권장합니다. 가능한 환경에서는 아래와 같이 덤프를 만들어 **복구 가능한지 사전 확인**합니다. 비밀번호/DB URL/덤프 파일을 공개 폴더에 업로드하지 마세요.

```bash
# DATABASE_URL은 Replit Secrets에 설정된 기존 PostgreSQL URL을 유지
pg_dump --format=custom --no-owner --no-privileges --file="$HOME/projectagain_before_v12.dump" "$DATABASE_URL"
```

3. App Storage의 비공개 객체·설정과 GitHub App 환경변수도 별도로 백업/검증합니다. **기존 JWT_SECRET / 암호화 키 / DB URL을 변경하지 마세요.**
4. 운영 트래픽/워커를 중지하거나 점검 시간 확보. 백업 성공 여부를 확인한 후 적용합니다.

## 업그레이드

프로젝트 루트를 `projectagain/`이라고 가정합니다. 기존 `.venv`, 데이터베이스, Replit Secrets, 연결된 스토리지는 삭제하지 않습니다.

```bash
cd ~/workspace/projectagain
# 새 ZIP 내 backend/, frontend/, scripts/, docs/ 등 소스를 기존 위치에 복사
# 기존 DB 파일/스토리지/Secrets/실제 프로젝트별 .env 내용은 덮어쓰지 않음

# 기존 마이그레이션 버전을 확인합니다. 보통 0007_development_roadmap이어야 합니다.
cd backend
../.venv/bin/python -m alembic current
cd ..

# Python/Node 의존성 설치, 잠금 파일 기반 React 빌드 후 DB 마이그레이션
bash scripts/setup_replit.sh

# 또는 설치 단계를 나누어 제어할 경우:
# export PIP_CONFIG_FILE=/dev/null PIP_USER=0
# .venv/bin/python -m pip install --no-user -r backend/requirements-dev.txt
# cd frontend && npm ci --no-audit --no-fund && npm run build && cd ..
# cd backend && ../.venv/bin/python -m alembic upgrade head && cd ..

cd backend
../.venv/bin/python -m alembic current
cd ..
bash scripts/run_replit.sh
```

**중요:** `scripts/setup_replit.sh`는 프론트엔드 빌드가 성공한 **다음에만** 마이그레이션을 실행합니다. 해당 명령이 실패하면 이유를 확인하고 재실행할 때 백업 상태를 보존하세요. 필요 환경변수는 기존 v0.11과 동일하며 v0.12에 새로운 필수 Secret이 없습니다. `DATABASE_URL`을 테스트용 SQLite로 임의 변경해 기존 DB를 바꾸지 마세요.

## 적용 후 점검

- `/health`, `/docs`, `/api/v1/system/capabilities` 응답 확인. API 버전 0.12.0.
- `alembic current` 결과가 `0008_integrated_workspace`인지 확인.
- 기존 계정 로그인, 판매 매물 상태, GitHub 연결 정보, 비공개 원본 파일, 이전 거래·계약/로드맵 기록을 백업 전후 비교.
- 별도 DEMO 매물로 구매자 A/B 각각 제안→승인→시연 완료. **매물은 계속 ACTIVE**인지 확인.
- 제안/역제안 타임라인에서 가격·지원·제외 자산 변경 확인. 합의 당시 지원 기간과 건수 고정 여부 확인.
- 인수 완료 전 지원 기한 미시작 → 완료 후 7일/3건 등 약정 반영 → 일반 문의 건수 차감 → 누락 자산·권리 문제 제외 → 판매자 답변 → 구매자 해결 확정 → 관리자 검토 요청까지 테스트.
- 구매자 스킬/안내 수준 저장 후 로드맵 단계 설명 변화·막힘 사유 저장·작업과 문의 연결 확인.
- 외부 Streamlit AI 에이전트에서 기존 토큰/권한/목록·제안 연동 테스트.

## 과거 v0.11 시연 거래에 의해 예약/종료된 매물 처리

v0.12는 새로운 DEMO 수락에서 `RESERVED`나 `CLOSED`를 생성하지 않습니다. 하지만 **과거 거래로 이미 그렇게 바뀐 매물은 자동 복구하지 않습니다.** 적법한 게시 중지/다른 거래 처리를 덮어쓸 수 있기 때문입니다. 해당 매물을 운영자가 검색하고 과거 `transactions`·`deal_events`·감사 로그와 권리 상태를 검증하여 필요한 매물만 별도 게시 복구 절차를 사용하세요. SQL 대량 UPDATE는 사용하지 마세요.

## 롤백

`0008`의 다운그레이드는 고의로 차단했습니다. 새로 생성된 협상·지원 기록을 보호하기 위해서입니다. 장애 발생 시 새 쓰기 트래픽을 중지하고 **승인된 시점의 DB 및 소스 백업을 함께** 복구하세요. 이전 스키마로 단순 Alembic downgrade를 시도하지 마세요.
