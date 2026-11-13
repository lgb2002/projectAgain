# ProjectAgain v0.6 — GitHub/ZIP 매물 등록 API 계약

기본 URL은 기존과 동일한 `/api/v1`. 인간 사용자의 **httpOnly 세션 쿠키**로만 분석/가져오기를 수행하며, 쓰기 요청 시 기존 `X-CSRF-Token` 헤더가 필요합니다. 외부 AI 에이전트 Bearer grant로 소스를 가져오거나 Github 계정을 연결할 수 없습니다.

## 엔드포인트

| 요청 | 엔드포인트 | 동작 |
|---|---|---|
| GET | `/github/status` | App 설정 여부·연결 여부·GitHub 사용자 표시·App 설치 URL |
| POST | `/github/connect` | GitHub App OAuth 동의용 `authorize_url` 발급 |
| GET | `/github/callback` | GitHub OAuth `code` 교환·연결 저장·판매 화면 복귀 |
| GET | `/github/repositories` | 인증된 사용자가 접근 가능한 앱 설치 저장소 목록 |
| DELETE | `/github/connection` | 토큰 로컬 삭제, 연결 해제 |
| POST | `/listing-imports/github` | 지정 저장소 최신 기본 브랜치 커밋을 ZIP으로 가져와 검사·분석 |
| POST | `/listing-imports/zip` | multipart `file` ZIP 업로드 후 검사·분석 |
| GET | `/listing-imports/{id}` | 작성자만 분석 결과 재조회(2시간 이내, 미사용) |
| POST | `/listings` | 기존 매물 생성 + 선택적 `import_id` 첨부 |
| GET | `/listings/{id}/source-summary` | 비공개 원본을 제외한 공개 안전 요약. 비공개 매물은 판매자·관리자만 |

### GitHub 소스 분석 요청

```json
{"repository":"https://github.com/owner/repo", "installation_id":null}
```

공개 저장소는 `installation_id` 없이 호출합니다. 비공개 저장소는 GitHub App 사용자 OAuth를 완료하고 `GET /github/repositories`의 반환값에서 **해당 저장소의 installation_id**를 지정합니다. 서버에서 매 요청마다 접근 가능한 설치·저장소 목록을 재확인합니다. 임의 URL로 네트워크 접근하지 않습니다.

### 분석 응답 (일부)

```json
{
  "id":"<import-uuid>",
  "source_type":"GITHUB",
  "source_label":"owner/repo",
  "source_private":true,
  "revision":"12자리-커밋-접두사",
  "asset_review_status":"QUARANTINED",
  "analysis":{
    "analysis_version":"static-v1",
    "level":"STATIC_EVIDENCE_ONLY",
    "file_count":42,
    "tech_stack":["FastAPI","Python"],
    "possible_features":["로그인 관련 코드"],
    "possible_services":["PostgreSQL"],
    "signals":{"readme":true,"tests":false,"deployment_config":true},
    "warnings":["TESTS"],
    "description_suggestion":"판매자가 검토할 설명 초안",
    "included_assets_suggestion":["소스코드 ZIP (비공개 보관·관리자 검토 대상)"],
    "code_executed":false,
    "llm_used":false
  }
}
```

응답의 `source_label`은 **로그인한 소스 소유자에게만** 반환합니다. GitHub 원본 주소, 저장소 이름, 코드 원문, 비밀키, 원본 저장소 경로는 공개 요약 API에 포함하지 않습니다. `source_private=false`에서도 원본 자동 공개는 하지 않습니다.

### 매물 생성 연결

```json
{
  "import_id":"<import-uuid>",
  "title":"판매자가 최종 확인한 이름",
  "description":"판매자가 최종 확인한 설명 (30자 이상)",
  "category":"web_app",
  "lifecycle_status":"IN_DEVELOPMENT",
  "sale_rights_type":"ASSET_TRANSFER_ONLY",
  "inventory_mode":"ONE_TIME",
  "price_krw":100000,
  "included_assets":["소스코드"],
  "rights_attested":true,
  "is_demo":true
}
```

`import_id`는 선택적입니다. 생성 서버는 다음을 하나의 DB 거래에서 확인합니다: 올바른 판매자 / 최초 사용 / 미만료 / 총 보관 용량. 검증 통과 시 매물은 `DRAFT`, 원본은 기존 `listing_assets` 테이블에 `QUARANTINED`, 기술 요약은 `listing_source_summaries`에 보관합니다. 중복 연결은 `409`입니다. 가격·권리·매출·검증 상태를 자동 확정하지 않습니다.

## 보안·비용 제한

- 파일 기본 최대 10MB(`ASSET_MAX_BYTES`), 압축 해제 총 최대 100MB, 최대 4,000개 ZIP 항목, 비정상 압축/경로 탈출/암호화/Symlink/민감 파일 이름 차단.
- 사용자별 임시 분석 동시 최대 3개, 임시 소스 2시간 만료. 계정당 소스 보관 총 100MB (기존 최종 첨부와 합산).
- 외부 주소는 GitHub API의 고정 호스트와 검증한 `codeload.github.com`만 허용, 소스 다운로드 스트리밍 크기 제한.
- 특정 GitHub 커밋을 고정해 다운로드; 실제 저장소 최신 코드가 이후 달라져도 등록된 원본이 자동 변경되지 않습니다.
- Git LFS 및 Git submodule 파일은 누락될 수 있어 가능한 경우 표시합니다. Git 커밋 전체 이력도 ZIP에 포함되지 않습니다.
- 의존성/경로와 Python AST를 **실행 없이** 검사하고 README 첫 설명을 판매자에게 제안합니다. README의 실제 구현 주장도 검증하지 않습니다.
- 로그인한 소유자만 원본을 업로드하거나 가져옵니다. 공개 분석에는 민감한 원본 정보가 제외되고 파일별 실사 접근은 기존 판매자 승인·관리자 검토·악성코드 검사 정책을 따릅니다.
- 운영에서 GitHub user OAuth 토큰을 암호화해 DB에 저장합니다. Replit Secrets의 암호화 키와 Client Secret을 소스에 넣지 않습니다.

## 외부 AI 에이전트와의 호환성

`docs/AGENT_API_HANDOFF_V05.md`의 기존 계약과 권한은 변경하지 않습니다. 외부 에이전트는 `GET /listings/{id}/source-summary`에서 공개 범위의 정적 분석 사실을 읽을 수 있습니다. 원본 분석은 기존 판매자 동의 후 비공개 파일 접근/실사 계약을 사용해야 합니다. 플랫폼은 LLM이나 원격 모델을 호출하지 않습니다.
