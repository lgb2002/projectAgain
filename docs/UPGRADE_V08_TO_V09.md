# ProjectAgain v0.8 → v0.9 업데이트

1. **기존 배포 백업**: 기존 프로젝트 디렉터리와 운영 PostgreSQL을 각각 백업합니다.
2. v0.9 ZIP의 `projectagain/` 하위 소스 파일을 기존 `~/workspace/projectagain/`에
   덮어씁니다. 기존 Secrets나 DB는 삭제하지 않습니다. 임의의 `drop_all`/테이블 초기화를 수행하지 마세요.
3. Replit Shell:

```bash
cd ~/workspace/projectagain
bash scripts/setup_replit.sh
bash scripts/run_replit.sh
```

4. 필요시 마이그레이션 상태 확인:

```bash
cd ~/workspace/projectagain/backend
../.venv/bin/python -m alembic current
../.venv/bin/python -m alembic heads
```

두 명령의 revision이 모두 `0007_development_roadmap`이어야 합니다.

5. 실제 사이트에서 화면 확인:
   - 공개 매물의 상세에서 `인수 후 개발 로드맵` 예상 항목 조회
   - 미완료 시연 거래의 구매자는 저장용 로드맵을 생성할 수 없음
   - 인수 체크리스트 완료 후 `DEMO_COMPLETED`로 전환
   - 완료한 거래에 구매자로 접속해 개인 로드맵 생성·진행/메모 저장
   - 선행 작업이 완료되지 않은 작업 진행 시 409
   - 개인 작업 추가 후 저장·내보내기
   - 판매자/다른 사용자로 같은 개인 로드맵 접근 시 404

새로운 Replit Secret은 필요하지 않습니다.
**프론트엔드 정식 빌드와 Replit PostgreSQL 실환경 테스트는 별도로 진행해야 합니다.**
현재 플랫폼은 실제 구매·저작권 이전·결제를 지원하지 않습니다.
