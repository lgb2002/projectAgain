# ProjectAgain – 단일 Vercel 프로젝트 (화면 미리보기 v0.15)

기존 ProjectAgain v0.14의 React 19 + TypeScript + Vite 화면 코드를 **저장소 루트로 옮긴 단일 프로젝트**입니다.
이번 버전은 백엔드, 데이터베이스, 별도 API Vercel 프로젝트 없이 사이트 **화면만 표시**합니다.

## Vercel 연결

1. ZIP 안의 **내용물**(`src/`, `package.json`, `vercel.json` 등)을 기존 Git 저장소의 `workspace/projectagain/` **루트**에 복사합니다. `.git/`은 절대로 삭제하지 마세요.
2. 기존 체크아웃에 `frontend/`와 `backend/`가 남아 있어도 본 화면 배포에는 사용하지 않습니다. 기존 백엔드 원본은 별도로 백업하고 삭제하지 마세요.
3. GitHub에 커밋/푸시하고 Vercel의 **단일 프로젝트**로 Import하세요.
4. Vercel 설정: **Application Preset: Vite / Root Directory: `./`(저장소 루트) / Build Command: `npm run build` / Output Directory: `dist` / Install Command: `npm ci`**.
5. 기존 Vercel 프로젝트가 `frontend` 또는 `backend`를 Root Directory로 사용 중이면 Project Settings → Build and Deployment → Root Directory에서 **루트로 변경**하거나 새 Vercel 프로젝트로 Import하세요.
6. **환경변수와 DB 연결은 필요 없습니다.** 비밀키, JWT, GitHub Client Secret 등은 이번 Vercel 프로젝트에 입력하지 마세요.
7. `vercel.json`은 `/about`, `/explore`, `/login` 같은 React Router 주소를 직접 열거나 새로고침해도 화면이 나오도록 처리합니다.

### 중요

- 별도 서버 또는 FastAPI 앱이 동작하지 않습니다.
- 조회 화면은 실제 매물 없이 빈 상태로 표시되며, 로그인·가입·파일 업로드·거래·개인정보 삭제 등은 **동작하지 않습니다**.
- 프론트엔드 내부의 서버 요청은 정적 미리보기 모드에서 차단하여 임의의 API 응답/오류가 첫 화면을 깨뜨리지 않게 했습니다.
- UI 원본의 페이지 및 디자인은 유지했습니다. 현재는 **실서비스 운영용이 아닙니다**.
- 기존 백엔드 원본과 v0.14 ZIP을 보관해 두면, 나중에 단일 Vercel 프로젝트 내 API 구조를 추가하는 후속 개발에 사용할 수 있습니다.

## VS Code 실행

프로젝트 루트에서 PowerShell 또는 터미널:

```bash
npm ci
npm run dev
```

접속: `http://localhost:5173`

배포용 빌드 확인:

```bash
npm run build
npm run preview
```

## 보안

- 프론트엔드 전용 ZIP에 `.env` 실키, 데이터베이스 자격증명, 원본 백엔드는 넣지 않았습니다.
- GitHub에 올리기 전 `git diff --cached --name-only`로 저장소의 **기존** 파일도 점검하세요.
- `VITE_`로 시작하는 값은 공개 웹 번들에 포함될 수 있으므로 비밀키를 넣지 마세요.
- 기존 `frontend/`가 로컬에 남아 있어도 Vercel은 저장소 루트의 `src/`를 빌드하며 `.vercelignore`가 레거시 폴더를 업로드에서 제외합니다.

## 이번 버전 구성

- `src/`: 원본 프론트엔드 컴포넌트/페이지, 미리보기 API 차단
- `index.html`, `package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`: 루트에서 빌드
- `vercel.json`: Vite 설정, SPA 주소 새로고침 처리
- `.gitignore`, `.vercelignore`: 개발 환경 및 레거시 배포 자산 제외


## Vercel dependency fix

The lockfile references the public npm registry instead of the private Replit package firewall. Install using `npm ci` and deploy with the Vite preset, root directory `./`, build `npm run build`, output `dist`. No backend or secrets are required for the UI-only preview.
