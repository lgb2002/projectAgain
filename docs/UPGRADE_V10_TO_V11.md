# ProjectAgain v0.10 → v0.11 업그레이드

## 준비

- 기존 `projectagain` 폴더, PostgreSQL 데이터베이스, Replit App Storage 자료를 각각 백업한다.
- Replit Secrets, GitHub App 설정, SMTP 관련 Secret을 유지한다. 이 버전에 신규 Secret은 없다.
- `.venv`, 운영 DB, 저장 중인 소스 업로드 파일을 제거하지 않는다.

## 설치

1. ZIP 내부 `projectagain/`의 소스 파일들을 기존 `~/workspace/projectagain`에 복사한다. 기존 DB와 Secrets를 덮어쓰지 않는다.
2. Replit Shell에서 아래 실행:

```bash
cd ~/workspace/projectagain
bash scripts/setup_replit.sh
bash scripts/run_replit.sh
```

3. 프론트엔드 빌드 성공 메시지가 나오는지 확인한다. 빌드 실패 시 예전 `dist`가 표시될 수 있으므로 배포 전 반드시 실패 원인을 해결한다.
4. 브라우저 강력 새로고침 후 관리자·판매자·구매자 계정으로 테스트한다.

## DB 및 URL 호환

- 기존 Alembic head `0007_development_roadmap` 유지. 새 테이블/컬럼 없음.
- `GET /api/v1/notifications`는 기존 기본 응답을 유지하면서 전체 미읽음 집계, 페이지네이션(`limit`, `offset`, `has_more`)을 제공한다.
- 신규 화면 URL: `/notifications`, `/settings`, `/sell/:id/complete`.
- 기존 `dashboard?tab=notifications` 등의 URL은 계속 접근 가능.

## 등록·알림에 대한 주의

- 판매 등록 도중의 폼 임시 저장은 해당 브라우저의 `localStorage`에 보관된다(다른 기기 동기화 아님). 공용 기기 사용자는 임시본 정리를 권장한다.
- 신규 등록 시 기본 정보 저장 후 **서버에 초안이 존재**하게 된다. 사진 및 미리보기 정보를 마치지 않아도 매물 초안은 `내 프로젝트`에서 확인할 수 있다.
- 관리자 검토 요청 이후 승인 전까지 프로젝트 탐색에 나타나지 않는다.
- GitHub/ZIP 정적 분석은 실제 작동, 판매 권리 및 악성코드 안전 인증을 보증하지 않는다.

## 수동 검증

`docs/UX_ACCEPTANCE_V11.md`를 사용한다. 실제 배포 URL에서 검증되지 않은 기능을 출시 완료로 간주하지 않는다.
