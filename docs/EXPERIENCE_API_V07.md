# ProjectAgain v0.7 — 신규 REST API 계약

기본 경로: `/api/v1`. `POST/PATCH/PUT/DELETE`는 로그인 세션 및 기존 CSRF 헤더 검증을 요구합니다. 새로운 엔드포인트는 외부 에이전트 토큰만으로 사용자 자산·문의/알림을 수정할 수 없습니다. 프론트엔드는 `api.ts`의 공통 호출기를 사용합니다.

| 방식 | 경로 | 권한·동작 |
|---|---|---|
| GET | `/listings/{id}/showcase?include_demo=true` | 공개 매물 또는 소유자/관리자, 이미지·링크·특징 조회 |
| PUT | `/listings/{id}/showcase` | 판매자, 시연 URL·영상 URL·특징 저장 및 공개 재검토 |
| POST | `/listings/{id}/media` | 판매자, multipart `file`, 재인코딩 및 비공개 저장 |
| GET | `/listings/{id}/media/{media_id}/image?demo=true` | 매물 조회 권한 검사 후 WebP 스트림 |
| PATCH | `/listings/{id}/media/{media_id}` | 판매자, 이미지 설명 및 대표 지정 |
| DELETE | `/listings/{id}/media/{media_id}` | 판매자, 이미지 삭제 |
| POST | `/listings/{id}/source-summary/reanalyze` | 판매자, 기존 보관된 원본 ZIP 무결성 확인 후 정적 재분석 |
| GET | `/listings/{id}/inquiries?include_demo=true` | 공개 문의·접속자 본인의 비공개 문의 |
| POST | `/listings/{id}/inquiries` | 구매자, `question`(10~1500자), `visibility` (`PUBLIC`/`PRIVATE`) |
| GET | `/inquiries/inbox` | 구매자·판매자 본인 관련 문의 목록 |
| POST | `/inquiries/{id}/answer` | 판매자 본인, `answer`(2~2000자) |
| POST | `/admin/inquiries/{id}/hide` | 관리자, 문의 공개 숨김 |
| GET | `/notifications/preferences` | 본인 이메일 알림 설정과 SMTP 서버 설정 여부 |
| PUT | `/notifications/preferences` | 본인 이메일 알림 수신 여부 수정 |
| POST | `/notifications/read-all` | 본인 알림 일괄 읽음 |

기존 `/notifications`, `/notifications/{id}/read`도 유지합니다. 기존 `/listings`, `/my/listings`, `/favorites`, `/admin/listings` 응답에는 선택 필드 `cover_image_url`이 추가됩니다. 기존 클라이언트와 호환되도록 기존 필드는 유지합니다.

## 미리보기 자료

**예시** `PUT /listings/UUID/showcase`:

```json
{"demo_url":"https://demo.example.com","video_url":"https://youtu.be/example","highlights":["로그인 지원","프로젝트 통계 화면"]}
```

YouTube/Vimeo 이외의 영상 도메인은 허용하지 않습니다. 시연 URL은 임의의 공개 HTTPS 도메인이 가능하지만 **백엔드가 URL로 요청하지 않습니다**. 유저 정보나 사설 IP 링크를 허용하지 않습니다.

**예시** `PATCH /listings/UUID/media/UUID`:

```json
{"caption":"프로젝트 대시보드","set_cover":true}
```

## 인수 준비 정적 분석

새 공개 분석 응답(`GET /listings/{id}/source-summary`의 `analysis`)에는 다음 필드가 추가됩니다.

- `analysis_version: static-v2`
- `takeover_checks: [{key, label, status: FOUND|REVIEW, detail}]`
- `takeover_next_steps: string[]`
- `takeover_review_count: number`
- `takeover_scope: string`

이 필드는 **정적 파일 분석 근거**일 뿐, 서비스 작동·완료·지식재산권 이전·판매 가격의 진위 인증이 아닙니다. 소스코드 텍스트/저장소 비공개 이름·키·경로는 반환하지 않습니다.

## 문의 프라이버시

- `PUBLIC`: 해당 매물 열람자에게 질문·답변 공개.
- `PRIVATE`: 질문 작성자, 매물 판매자, 관리자에게만 노출.
- 직접 이메일/전화번호/외부 URL을 게시하는 행위 제한.
- 문의/답변을 남겨도 구매 제안이나 거래가 발생하는 것은 아님.

## SMTP 알림

`notification_emails`는 사용자에게 외부 API로 노출되지 않는 내부 대기열입니다. 사용자에게는 알림 목록과 수신 설정만 공개합니다. 발송 작업은 `app.email_worker` 프로세스가 처리하고 SMTP 실패는 재시도합니다. 비공개 문의 원문이나 코드/개인 토큰을 메일에 포함하지 않습니다.

실제 자동 생성 API 스냅샷: `contracts/implemented-openapi-v07.json`.
