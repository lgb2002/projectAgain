# ProjectAgain v0.12 → v0.13 Replit 수동 업그레이드

## 사전 확인

1. **Replit Secrets·기존 PostgreSQL DB·Replit App Storage 백업**. ZIP에 `.env`나 실제 DB가 포함되지 않았으므로 백업을 생략하면 안 됩니다.
2. 서비스 중단/점검 시간을 잡고, v0.12 소스와 비공개 파일을 별도 보관합니다.
3. 기존 `DATABASE_URL`, `JWT_SECRET`, `GITHUB_TOKEN_ENCRYPTION_KEY`, 스토리지 관련 Secrets를 유지합니다. 절대 `create_all`, `drop_all`, `seed_demo`로 실DB를 초기화하지 마세요.
4. ZIP의 **`projectagain/` 폴더 내부 내용**을 기존 프로젝트 루트에 업데이트합니다. 개발용 ZIP에 있는 `node_modules`, `.venv`, DB를 사용하지 마세요.

## 명령어 (Replit Shell, `~/workspace/projectagain` 폴더)

```bash
cd ~/workspace/projectagain
bash scripts/setup_replit.sh
```

설치·프론트 빌드·마이그레이션을 자동 실행합니다. 수동 검증 또는 부분 재실행은:

```bash
cd ~/workspace/projectagain/backend
../.venv/bin/python -m alembic current
# 기대: 0009_privacy_readiness (head)
../.venv/bin/python -m alembic upgrade head
cd ~/workspace/projectagain
bash scripts/check_project_v013.sh
```

프론트 정식 빌드만 재확인하려면:

```bash
cd ~/workspace/projectagain/frontend
npm ci --no-audit --no-fund
npm run build
```

웹 서버 (Shell 1 또는 Replit Run):

```bash
cd ~/workspace/projectagain
bash scripts/run_replit.sh
```

이메일 + 개인정보 파일 삭제 워커 (Shell 2, **운영 환경에서 지속 실행 필요**):

```bash
cd ~/workspace/projectagain
bash scripts/run_notification_worker.sh
```

워커를 실행하지 않는 동안 삭제 큐가 쌓인다면 별도 Shell에서 일회성 재시도:

```bash
cd ~/workspace/projectagain
bash scripts/cleanup_privacy_objects.sh
```

개인정보 삭제 큐는 계정 비활성화 트랜잭션 이후 처리되어야 하므로 미정리 작업이 남지 않는지 정기적으로 확인하세요. Replit Deployments의 **웹 프로세스는 Shell 프로세스와 별개**입니다. 배포 시 웹 실행 명령과 별도로 지속 워커(또는 주기적 작업)를 운영해야 합니다.

## 수동 인수 검증

- 회원가입/로그인/재로그인, CSRF, 관리자 계정 탈퇴 차단
- 수동 등록 매물(원본 없음)의 인수 준비 보고서 확인
- ZIP 업로드 후 분석 → 매물 등록 → 보고서의 소스 근거 확인
- GitHub App 연결 시 정확한 SHA 기반 CI 결과, 미조회 상태에서도 등록 실패하지 않음
- 외부 AI 에이전트 공개 실사 기록 노출 여부와 비공개 내용 차단
- 비밀번호 오류 시 탈퇴 불가 / 탈퇴 후 원래 이메일 로그인 불가 / 비공개 저장소 파일 접근 불가
- 이메일 워커/삭제 워커 실행 → 객체 파일이 실제 삭제됐는지 Replit App Storage에서 확인
- 기존 협상·시연 인수·로드맵·사후 지원 및 DEMO 매물 상태 불변 확인

## 운영 한계

실제 PostgreSQL·Replit App Storage·GitHub App·SMTP·React 정식 빌드·브라우저 종단간 검증은 별도로 수행해야 합니다. 개발자 테스트에서의 SQLite 동작만으로 운영 배포 준비 완료로 판단하지 마세요.
