# 레포 규칙 — Dopamine-Ledger 기준

> 원본: https://github.com/pirogramming/Dopamine-Ledger (develop 브랜치)
> 팀장이 PM·인프라를 맡았던 프로젝트로, **규칙·파일 구성은 이것과 똑같이** 가져간다.
> 원본 파일을 직접 보려면 레포 밖 임시 폴더에 클론해서 읽기만 한다. 앱 코드는 절대 복사하지 않는다.
>
> ```bash
> git clone --depth 1 https://github.com/pirogramming/Dopamine-Ledger.git /tmp/dopamine-ref
> ```
>
> 참고할 파일: `README.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`,
> `.github/workflows/deploy.yml`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, `.env.example`,
> `requirements.txt`, `config/settings.py`(환경변수 읽는 방식만)

---

## 1. 그대로 가져갈 것

### 브랜치 전략

```
main        ← 릴리스 브랜치 (2026-10-09부터 GitHub 기본 브랜치). develop에서 릴리스 PR로만. 머지 시 EC2 자동 배포.
 └ develop  ← 통합 브랜치. feature가 머지되는 곳 (CI만, 배포 없음).
    └ feature/기능명   ← 이슈 단위 개인 작업 브랜치
```

- 이름 규칙: `feature/기능명`, `fix/버그명`, `docs/문서명` (+ 이번 레포에서 추가: `chore/작업명` — 설정·인프라)
- 이슈 하나 = 브랜치 하나 = PR 하나. 항상 최신 `develop`에서 분기.
- `develop`은 항상 실행 가능한 상태 유지 (곧 `main`으로 릴리스되므로). 작업 PR의 base는 `develop`.

### 커밋 컨벤션

`<타입>: <내용>` (한국어). 예: `feat: 장소 상세 API 추가`, `chore: docker-compose.prod.yml 추가`

| 타입 | 용도 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 |
| `style` | 코드 포맷 (기능 변화 없음) |
| `refactor` | 리팩터링 |
| `test` | 테스트 추가/수정 |
| `chore` | 설정·빌드·인프라 등 잡무 |
| `design` | UI·디자인 수정 (원본 레포에서 실제로 쓰던 타입) |

### 이슈

- 제목 형식: `[앱이름] 기능 요약` (예: `[places] 조건별 판정 함수 + 단위 테스트`)
- 1~2일 안에 끝낼 크기로 잘게 쪼갠다.
- 템플릿 5종: `feature.md`(기능 개발), `bug.md`(버그 신고), `design.md`(디자인/UI), `docs.md`(문서), `chore.md`(설정/잡무)
- `config.yml`: `blank_issues_enabled: false` + 디스코드 문의 링크 (링크는 사용자에게 받아서 채운다)
- 라벨: `feature`, `bug`, `design`, `documentation`, `chore`

### PR 템플릿 구성

종류(체크박스: feat / fix / 디자인·UI / docs / chore) → 무엇을·왜(2~3줄) → 관련 이슈(`Closes #`) → 변경 사항 → 테스트 방법 → 스크린샷 → 체크리스트 → 리뷰어에게

체크리스트:
- 로컬에서 실행해봤고 안 깨진다 (`docker compose up`)
- 커밋 컨벤션을 지켰다
- `.env` 등 시크릿이 커밋에 포함되지 않았다
- 리뷰어를 지정했다

### CONTRIBUTING.md 구성

소통(디스코드 실시간, 노션 문서, 짧은 데일리) → 브랜치 전략 → 이슈 관리 → 커밋 컨벤션 → PR(작게, 리뷰 규칙, 리뷰 말투) → 코드 규칙 → 의사결정(막히면 PM이 최종 결정) → 자주 쓰는 명령어

이번 레포 코드 규칙에 추가할 것:
- **판정 로직(조건별 가능/조건부/어려움/미확인)은 단위 테스트 필수** — 원본의 "환산 엔진은 단위 테스트"와 같은 위치
- 파생값(예: 장소의 최종 판정, 신뢰도)은 가능하면 저장하지 않고 계산 — 원본의 "잔액은 ORM 집계로 계산" 원칙
- 커밋 전 `docker compose up`으로 안 깨지는지 확인

### README.md 구성 (원본과 같은 순서·톤, 이모지 섹션 제목 + 표 위주)

📌 프로젝트 소개 → ✨ 핵심 기능(표) → 🛠 기술 스택(표) → 🚀 시작하기(3줄 실행, 최초 1회 세팅, 환경 변수 표, 테스트) → 📁 프로젝트 구조(앱 = 기능 = 담당자 경계) → 🗓 개발 로드맵 → 👥 팀 → **📚 오픈소스 / 출처 (대회 규정상 필수, 원본에 없던 섹션)**

### 설정 방식

- `config/` 프로젝트 폴더, 기능별 Django 앱 폴더. **앱 경계 = 기능 경계 = 담당자 경계.**
- 전역 `templates/`, `static/` + 앱별 `templates/<앱>/`, `static/<앱>/`
- `settings.py`는 `python-dotenv`로 `.env`를 읽고, `dj-database-url`로 `DATABASE_URL` 파싱. 비어 있으면 SQLite 폴백.
- `DEBUG = os.getenv("DEBUG", "False") == "True"` (기본값 False)
- `LANGUAGE_CODE = "ko-kr"`, `TIME_ZONE = "Asia/Seoul"`
- `STATIC_ROOT = BASE_DIR / "staticfiles"`, `MEDIA_ROOT = BASE_DIR / "media"`
- `.env.example`은 섹션 주석(`# ── Django ──`)으로 구분하고, 맨 위에 `cp .env.example .env` 안내, SECRET_KEY 생성 명령 주석
- `.gitignore`/`.dockerignore`는 섹션 주석으로 구분, 마이그레이션 파일은 커밋한다(명시적 주석)
- `requirements.txt`는 섹션 주석 + 버전 고정 + 패키지별 용도 주석

### Docker·배포 방식

- `Dockerfile`: `python:3.12-slim`, `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, `gcc`·`libpq-dev` 설치, requirements 먼저 복사(레이어 캐시), CMD는 gunicorn. 줄마다 한국어 주석.
- `docker-compose.yml`(개발): `web`은 `runserver`로 오버라이드 + 코드 볼륨 마운트, `db`는 `postgres:16` + named volume
- `deploy.yml`: `main` push(릴리스 PR 머지) 또는 수동 실행 → Docker Hub 로그인 → 빌드·push → `appleboy/ssh-action`으로 EC2 접속 → `docker compose pull && up -d` → `migrate` → `collectstatic`
- GitHub Secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `EC2_HOST`, `EC2_KEY`
- 워크플로우 상단에 무엇을 하는지 주석 블록

---

## 2. 원본에서 개선할 것

원본은 Nginx·SSL 설정이 레포 밖(EC2 서버에만)에 있었고, 서버용 compose 파일도 레포에 없었다.
이번에는 **재현 가능성 심사(20점)** 때문에 서버 구성까지 전부 레포에 넣는다.

| # | 원본 | 이번 레포 |
|---|---|---|
| 1 | 개발용 `docker-compose.yml` 하나. 서버 구성은 서버에만 존재 | `docker-compose.yml`(개발) + **`docker-compose.prod.yml`(배포: nginx·web·db)** 을 레포에서 관리 |
| 2 | Nginx 설정 레포에 없음 | **`nginx/` 폴더에 설정 파일** (리버스 프록시, static/media 서빙, 업로드 용량, HTTPS) |
| 3 | 서버에 compose 파일을 따로 둠 | 서버는 레포를 `git clone`해 두고 배포 시 `git pull` → 설정 변경도 자동 반영 |
| 4 | db가 `5432` 포트를 외부에 노출 | 배포 구성에서는 **db 포트 노출 금지** (개발에서만 노출) |
| 5 | db가 준비되기 전에 web이 뜰 수 있음 | db `healthcheck` + `depends_on: condition: service_healthy` |
| 6 | 재시작 정책 없음 | 배포 구성 전 서비스 `restart: unless-stopped` (전시 기간 무중단) |
| 7 | `gunicorn` 버전 미고정, 옵션 없음 | 버전 고정 + `--workers`, `--timeout`(AI API 대비) 명시 |
| 8 | 이미지 태그 `latest`만 | `latest` + **커밋 SHA 태그**도 push (롤백용) |
| 9 | 배포 후 이미지 정리 없음 | 배포 스크립트에 `docker image prune -f` (EC2 디스크 부족 예방) |
| 10 | 헬스체크 엔드포인트 없음 | `/health/` (DB 연결 확인 포함) |
| 11 | DB 백업 없음 | `scripts/backup_db.sh` (`pg_dump`, cron 등록 방법은 배포 문서에) |
| 12 | `.gitattributes` 없음 | `*.sh text eol=lf` — Windows에서 체크아웃한 셸 스크립트가 컨테이너에서 깨지는 문제 예방 |
| 13 | HTTPS 관련 Django 설정 일부만 | `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS`, `SESSION/CSRF_COOKIE_SECURE`(DEBUG=False일 때) |
| 14 | README에 오픈소스 출처 섹션 없음 | 대회 규정대로 추가 |
| 15 | PR 승인 2명 | **1명 + CI 통과** (2026-09-26 결정, CLAUDE.md "결정된 사항") |
