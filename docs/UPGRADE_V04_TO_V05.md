# v0.4 → v0.5 수동 업그레이드 가이드

대상 폴더 예시: `~/workspace/projectagain`. **Replit Agent 사용 금지.**

1. 코드 작업 전에 기존 Replit 프로젝트 파일과 PostgreSQL을 각각 백업. 서버가 실행 중이면 중단.
2. 전체 ZIP 또는 변경 파일만 담은 패치 ZIP을 **ProjectAgain 프로젝트 루트에** 업로드하고 압축 해제. `backend/`, `frontend/`, `scripts/`가 기존 경로에 합쳐져야 함. `~/workspace/projectagain/projectagain`처럼 중첩되지 않게 주의.
3. Replit Secrets에 `AGENT_WRITE_MODE=disabled` 설정(선택; 미설정도 기본 disabled). **기존 `JWT_SECRET`, `DATABASE_URL` 변경하지 말 것.** 플랫폼에는 OpenAI 키 불필요.
4. `cd ~/workspace/projectagain && bash scripts/setup_replit.sh` 실행. Python/Node 설치가 이미 완료되었다면 반복 설치는 필요할 때만 수행해도 됨. **`replit.nix` 새로 생성 금지.**
5. `cd ~/workspace/projectagain/frontend && npm run build` 에서 오류 없이 끝나는지 확인.
6. `cd ~/workspace/projectagain && bash scripts/run_replit.sh` 실행.
7. `/health`, `/api/v1/system/capabilities`, `/docs` 확인.
8. 로컬 또는 Streamlit 실행 PC에서 HTTPS 도메인(정확한 Replit 접속 주소)으로 `scripts/smoke_agent_api.py` 실행. **직접 호출 전까지 외부 HTTPS 연동 성공이라고 주장하지 말 것.**

**기존 Alembic 마이그레이션 head: `0003_inspection_ai_drafts`**. v0.5는 스키마 변경이 없으므로 DB 테이블을 삭제하거나 초기화하지 않아도 됨.

새 파일은 `docs/AGENT_API_HANDOFF_V05.md`와 `integrations/streamlit_direct_api_example.py`를 별도 에이전트 채팅에 전달. 에이전트 앱 자체는 이 플랫폼 ZIP으로 수정되지 않음.

API 사용 규약은 `docs/AGENT_API_HANDOFF_V05.md` 참고.
