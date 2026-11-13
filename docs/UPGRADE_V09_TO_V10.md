# v0.9 → v0.10 업그레이드

## 변경 특성

기존 v0.9 DB 스키마와 API 계약을 유지하는 **프론트엔드 중심 업데이트**입니다. 데이터 초기화, 사용자 재가입, 관리자 계정 재설정이 필요하지 않습니다. 기존 GitHub App·SMTP·Storage Secrets도 유지합니다.

## Replit 배포

1. 기존 Replit 프로젝트의 소스와 PostgreSQL을 백업합니다. `.env`, Secrets, Storage, 기존 DB는 덮어쓰거나 삭제하지 않습니다.
2. 이 ZIP의 `projectagain/` 내용을 현재 프로젝트 디렉터리에 복사합니다. 기존 개발 파일 중 프로젝트에서 제거된 파일을 강제로 삭제하지 마세요.
3. 프로젝트 루트에서 다음을 실행합니다.

```bash
cd ~/workspace/projectagain
bash scripts/setup_replit.sh
bash scripts/run_replit.sh
```

`setup_replit.sh`는 기존처럼 패키지 설치, `npm run build` 및 `alembic upgrade head`를 수행합니다. 이번 버전은 Alembic revision이 변경되지 않았으므로 DB 구조는 그대로입니다.

4. 브라우저 캐시로 오래된 화면이 표시되면 강력 새로고침 후 확인하세요.
5. `docs/UX_ACCEPTANCE_V10.md`에 따라 PC·모바일에서 실제 시나리오를 검증합니다.

## 중요

- 작업 도중 브라우저 로컬 임시본이 있을 수 있으므로, 매물을 등록·수정한 다음 원본이 정상 반영됐는지 확인하세요.
- GitHub/ZIP 분석 후 새로고침하면 입력 내용은 남지만 서버의 임시 가져오기 ID는 복구하지 않습니다. 같은 소스를 다시 가져오거나 '원본 없이 진행'을 명시적으로 선택해야 합니다.
- 다른 브라우저·기기에서 작성하던 내용은 동기화되지 않습니다. 공용 PC에서는 저장 후 '임시본 지우기'를 활용하세요.
- 운영 화면의 파일 관리는 `내 활동 → 내 매물 → 비공개 자료`, 외부 AI 연결 관리는 헤더의 `연결 설정` 또는 `/operations?tab=agent`에서 접근합니다.
