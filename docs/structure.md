# 📁 파일 구조 · 역할 안내

레포에 있는 파일이 각각 **무슨 역할을 하고, 어떻게 구성되어 있는지** 정리한 문서입니다.
처음 합류했거나 "이 파일 건드려도 되나?" 싶을 때 먼저 읽어주세요.

> 새 파일·폴더를 추가하면 이 문서에도 한 줄 추가해주세요.

---

## 한눈에 보기

```
18_after-school-map-time/
│
├── config/                     ← Django 프로젝트 설정
│   ├── settings.py             ←   모든 설정 (값은 .env에서 읽음)
│   ├── urls.py                 ←   최상위 URL 연결
│   ├── wsgi.py / asgi.py       ←   서버 진입점
│   └── __init__.py
│
├── core/                       ← 인프라용 공통 앱
│   ├── views.py                ←   /health/, 홈 화면
│   ├── urls.py
│   ├── context_processors.py   ←   모든 템플릿에 카카오 JS 키 전달
│   ├── tests.py
│   ├── apps.py
│   └── templates/core/home.html
│
├── templates/                  ← 전역 템플릿
│   ├── base.html               ←   공통 레이아웃 (모든 페이지가 상속)
│   ├── 404.html
│   └── 500.html
│
├── static/                     ← 전역 정적 파일
│   ├── css/common.css          ←   디자인 변수(색·간격)와 공통 컴포넌트
│   ├── js/common.js            ←   api() fetch 헬퍼 (CSRF 자동 처리)
│   └── img/
│
├── nginx/                      ← 배포용 nginx 설정
│   ├── http/default.conf.template   ←   인증서 발급 전·로컬 검증용 (80번만)
│   ├── https/default.conf.template  ←   인증서 발급 후 (80→443 리다이렉트 + 443)
│   └── snippets/app.conf            ←   공통: static/media 서빙, web으로 프록시, 업로드 10MB
│
├── scripts/
│   └── backup_db.sh            ← DB 백업 (cron으로 매일 실행)
│
├── docs/
│   ├── deploy.md               ← 배포 런북 (EC2 → HTTPS → 자동 배포 → 백업)
│   ├── structure.md            ← (이 문서)
│   └── context/                ← 기획·규칙·인프라 설계 (Claude Code와 팀 공용 배경 자료)
│
├── .github/
│   ├── ISSUE_TEMPLATE/         ← 이슈 템플릿 5종 + config.yml
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci.yml              ← PR마다 자동 테스트
│       └── deploy.yml          ← EC2 자동 배포
│
├── .claude/commands/           ← Claude Code 팀 공용 커맨드
│
├── Dockerfile                  ← 이미지 만드는 법
├── docker-compose.yml          ← 개발 환경 (web + db)
├── docker-compose.prod.yml     ← 배포 환경 (nginx + web + db)
├── requirements.txt            ← 파이썬 패키지 목록
├── manage.py                   ← Django 명령 실행기
│
├── .env.example                ← 환경 변수 템플릿 (커밋 O)
├── .env                        ← 실제 값 (커밋 X, 각자 PC에만)
├── .gitignore / .dockerignore  ← Git·Docker가 무시할 파일
├── .gitattributes              ← 줄바꿈(LF) 통일
├── .editorconfig               ← 에디터 들여쓰기·인코딩 통일
│
├── README.md                   ← 프로젝트 소개·실행 방법
├── CONTRIBUTING.md             ← 협업 규칙
└── CLAUDE.md                   ← Claude Code 작업 안내서
```

---

## 1. Django 프로젝트 — `config/`

### `config/settings.py`

프로젝트의 모든 설정. **값은 코드에 직접 쓰지 않고 `.env`에서 읽습니다** (`python-dotenv`).
위에서부터 아래 순서로 구성되어 있습니다.

| 구역 | 내용 |
| --- | --- |
| 기본 | `DEBUG`(값이 `"True"`일 때만 켜짐), `SECRET_KEY`(**비어 있으면 서버가 안 뜸**), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` |
| 앱 | `INSTALLED_APPS` — Django 기본 앱 + DRF + 우리 앱(`core`). **새 앱은 여기 추가** |
| 미들웨어·템플릿 | 전역 `templates/` + 앱별 `templates/<앱>/` 둘 다 찾음. `kakao_keys` context processor 등록 |
| DB | `DATABASE_URL`이 있으면 PostgreSQL, 없으면 SQLite (`dj-database-url`로 파싱) |
| 언어·시간 | `ko-kr`, `Asia/Seoul` |
| 정적·업로드 파일 | `static/` → `staticfiles/`(collectstatic 결과), 업로드는 `media/`. 업로드 한도 10MB(폰 사진, nginx와 맞춤) |
| 배포 보안 | `DEBUG=False`일 때만: HTTPS 판단 헤더, 쿠키 Secure. HSTS는 의도적으로 보류(주석에 이유) |
| 로깅 | 콘솔 출력 → `docker compose logs web`으로 확인 |
| DRF | 세션 인증 (같은 도메인의 템플릿 페이지에서 fetch로 호출) |
| 외부 API 키 | `KAKAO_JAVASCRIPT_KEY`(브라우저용), `KAKAO_REST_API_KEY`(서버 전용), `AI_VISION_API_KEY` |

### `config/urls.py`

최상위 URL 목록. `admin/`과 `core`의 URL을 연결합니다. 새 앱을 만들면 `path("places/", include("places.urls"))`처럼 여기에 추가합니다.
`DEBUG=True`일 때만 업로드 파일(`/media/`)을 Django가 직접 서빙합니다 (배포에서는 nginx가 담당).

### `config/wsgi.py`, `config/asgi.py`

서버가 Django를 실행할 때 들어오는 입구. gunicorn은 `config.wsgi:application`을 실행합니다. 수정할 일 거의 없음.

### `manage.py`

`python manage.py migrate`, `runserver`, `test`, `startapp` 등 Django 명령을 실행하는 스크립트. 수정하지 않습니다.

---

## 2. 공통 앱 — `core/`

인프라 단계에서 두는 유일한 앱. 기능(도메인) 코드는 넣지 않습니다.

| 파일 | 역할 |
| --- | --- |
| `views.py` | `health` — DB에 `SELECT 1`을 해보고 정상이면 200 `{"status": "ok", "db": true}`, 실패면 503. 배포 후 확인·모니터링용<br>`home` — 홈 화면 |
| `urls.py` | `/` → home, `/health/` → health. `app_name = "core"`라서 템플릿에서 `{% url 'core:home' %}`로 참조 |
| `context_processors.py` | 모든 템플릿에 `KAKAO_JAVASCRIPT_KEY`를 넘겨줌 → 지도 페이지에서 SDK 로드할 때 사용. **REST 키는 절대 넘기지 않음** |
| `tests.py` | 헬스체크 정상(200)·DB 장애(503), 홈 화면 테스트 |
| `apps.py` | 앱 등록 정보 |
| `templates/core/home.html` | 홈 화면 (`base.html` 상속) |

---

## 3. 템플릿·정적 파일 — `templates/`, `static/`

| 파일 | 역할 · 구성 |
| --- | --- |
| `templates/base.html` | 모든 페이지의 뼈대. 상단 바(로고 + `nav` 블록), Django 메시지, 본문. 각 페이지는 `{% extends "base.html" %}` 후 아래 블록을 채움:<br>`title` · `extra_css` · `nav` · `main_class` · `content` · `extra_js` |
| `templates/404.html` | 없는 페이지 (`DEBUG=False`일 때만 보임) |
| `templates/500.html` | 서버 오류. 오류 상황에서도 뜰 수 있게 `base.html`·`url` 태그 없이 단독 HTML |
| `static/css/common.css` | 맨 위 `:root`의 **디자인 변수**(`--color-primary` 등)만 바꾸면 전체 색이 바뀜. 레이아웃·버튼·입력창·메시지 공통 스타일 |
| `static/js/common.js` | `api(url, {method, body})` — 우리 API 호출 헬퍼. POST 등에는 CSRF 토큰을 자동으로 붙이고, 실패하면 서버의 `detail` 메시지로 에러를 던짐 |
| `static/img/` | 공통 이미지 (아이콘·로고 등) |

> 앱 전용 템플릿·정적 파일은 앱 폴더 안에 둡니다: `places/templates/places/...`, `places/static/places/...`

---

## 4. 실행 환경 — Docker

### `Dockerfile` — 이미지 만드는 법

| 단계 | 내용 |
| --- | --- |
| 베이스 | `python:3.12-slim` |
| 환경변수 | 로그 즉시 출력, `.pyc` 안 만듦, pip 캐시 안 남김 |
| 의존성 설치 | `requirements.txt`만 먼저 복사해서 설치 → 패키지가 안 바뀌면 캐시 재사용(재빌드 빠름) |
| 코드 복사 | `.dockerignore`에 적힌 파일 제외하고 전체 복사 |
| 실행 | `gunicorn --workers 3 --timeout 60` (타임아웃 60초는 느린 AI API 대비) |

### `docker-compose.yml` — 개발 환경

| 서비스 | 내용 |
| --- | --- |
| `web` | Dockerfile로 빌드. 실행 명령을 `migrate && runserver`로 덮어씀. 내 PC 코드를 `/app`에 마운트해서 **수정 즉시 반영**. 포트 8000 |
| `db` | `postgres:16`. 데이터는 `postgres_data` 볼륨에 저장(컨테이너 지워도 유지). `healthcheck`로 준비 완료를 알리고, `web`은 그 뒤에 시작. 포트 5432(개발에서만 노출) |

### `docker-compose.prod.yml` — 배포 환경

개발용과 **프로젝트 이름이 달라서(`teokeopne-prod`)** 같은 PC에서 둘 다 띄워도 컨테이너·볼륨이 섞이지 않습니다.

| 서비스 | 내용 |
| --- | --- |
| `nginx` | 80·443 포트를 여는 유일한 서비스. `NGINX_CONF`(http/https)에 따라 `nginx/http` 또는 `nginx/https` 템플릿을 사용하고, 템플릿의 `${DOMAIN}`을 `.env` 값으로 치환. static·media 볼륨과 서버의 인증서(`/etc/letsencrypt`)를 읽기 전용으로 연결 |
| `web` | Docker Hub 이미지 `cjs1004ounds/teokeopne:${IMAGE_TAG}` (기본 `latest`). `.env` 값과 상관없이 **항상 `DEBUG=False`**. 포트를 외부에 열지 않음 |
| `db` | `postgres:16`. **포트 노출 없음**. `POSTGRES_PASSWORD`가 비어 있으면 시작 자체를 거부 |
| 공통 | 전 서비스 `restart: unless-stopped` → 서버 재부팅·에러 시 자동 복구 |

볼륨: `postgres_data`(DB), `static_volume`(collectstatic 결과, web이 쓰고 nginx가 읽음), `media_volume`(제보 사진, **백업 대상**)

---

## 4-1. nginx 설정 — `nginx/`

| 파일 | 역할 |
| --- | --- |
| `http/default.conf.template` | 80번만 사용. 인증서 발급용 경로(`/.well-known/acme-challenge/`) 응답 + 서비스. 인증서 발급 전 서버, 로컬 검증에서 사용 |
| `https/default.conf.template` | 80번은 인증서 갱신 경로만 응답하고 나머지는 https로 301 리다이렉트. 443번에서 TLS 1.2/1.3로 서비스. 인증서 경로에 `${DOMAIN}` 사용 |
| `snippets/app.conf` | 두 설정이 공통으로 `include`: 업로드 10MB(`client_max_body_size`), `/static/`(캐시 7일)·`/media/` 직접 서빙, 나머지는 `web:8000`으로 프록시(원래 Host·IP·https 여부 헤더 전달, 타임아웃 60초) |

gzip 압축은 두 템플릿 맨 위에서 켭니다 (CSS·JS·JSON).

### `requirements.txt`

섹션별(코어 / 설정 / DB·서버 / API / 외부 API / 이미지)로 나눠 **버전 고정 + 용도 주석**. 패키지를 추가하면 여기와 README "오픈소스 / 출처"를 같이 갱신합니다.

---

## 5. 환경 변수 — `.env.example`, `.env`

| 파일 | 커밋 | 역할 |
| --- | :--: | --- |
| `.env.example` | O | 어떤 변수가 필요한지 보여주는 **템플릿**. 값은 비워 두거나 개발용 기본값만 |
| `.env` | **X** | 실제 값(시크릿 키, API 키). 각자 `cp .env.example .env`로 만들어서 채움 |

구역: `Django` / `Database` / `카카오맵` / `AI 사진 판별` / `배포`(`DOMAIN`, `NGINX_CONF`, `IMAGE_TAG`). 변수별 설명은 README 환경 변수 표 참고.

---

## 6. Git·에디터 설정

| 파일 | 역할 |
| --- | --- |
| `.gitignore` | Git이 추적하지 않을 파일: `.env`, `*.pem`, `__pycache__`, `db.sqlite3`, `media/`, `staticfiles/`, `backups/`, `.claude/`(단 `.claude/commands/`는 공유) 등. **마이그레이션은 커밋함** |
| `.dockerignore` | Docker 이미지에 넣지 않을 파일: `.env`(시크릿이 이미지에 박히지 않게), 문서, Git 폴더, nginx·scripts(서버에서 레포로 직접 사용) 등 |
| `.gitattributes` | 줄바꿈을 LF로 통일. Windows에서 CRLF로 커밋된 `.sh`가 서버에서 `bad interpreter`로 깨지는 문제 예방 |
| `.editorconfig` | UTF-8, LF, 들여쓰기(파이썬 4칸, HTML·CSS·JS·YAML 2칸) 통일 |

---

## 7. GitHub — `.github/`

| 파일 | 역할 |
| --- | --- |
| `ISSUE_TEMPLATE/feature.md` | 기능 개발 이슈 (제목 `[앱이름] 기능 요약`, 라벨 `feature`) |
| `ISSUE_TEMPLATE/bug.md` | 버그 신고 (재현 방법, 기대/실제 동작, 에러 로그) |
| `ISSUE_TEMPLATE/design.md` | 디자인·UI 작업 |
| `ISSUE_TEMPLATE/docs.md` | 문서 작업 |
| `ISSUE_TEMPLATE/chore.md` | 설정·인프라 작업 |
| `ISSUE_TEMPLATE/config.yml` | 빈 이슈 금지(템플릿 강제). 디스코드 문의 링크 자리(TODO) |
| `pull_request_template.md` | PR 작성 양식: 종류 → 무엇을/왜 → 관련 이슈 → 변경 사항 → 테스트 방법 → 스크린샷 → 체크리스트 → 리뷰어에게 |
| `workflows/ci.yml` | `develop`·`main`으로 가는 PR·push마다 실행: 패키지 설치 → `manage.py check` → 마이그레이션 누락 검사 → 테스트. 실패하면 머지 금지 |
| `workflows/deploy.yml` | 이미지 빌드 → Docker Hub push(`latest` + 커밋 SHA) → EC2 SSH 접속 → `git pull` → 이미지 pull → 재시작 → migrate → collectstatic → 이미지 정리 → `https://<도메인>/health/` 확인. `develop`에 머지되면 자동 실행(수동 실행도 가능). 필요한 Secrets는 파일 상단 주석 참고 |

---

## 7-1. 운영 스크립트 — `scripts/`

| 파일 | 역할 |
| --- | --- |
| `backup_db.sh` | db 컨테이너에서 `pg_dump` → `backups/날짜_시간.sql.gz`. `KEEP_DAYS`(기본 7)보다 오래된 백업 삭제. 비어 있는 백업이면 실패 처리. 서버 cron으로 매일 실행 (`docs/deploy.md` 6단계) |

---

## 8. 문서

| 파일 | 역할 |
| --- | --- |
| `README.md` | 프로젝트 소개, 실행 방법, 환경 변수, 로드맵, 팀, 오픈소스 출처 |
| `docs/deploy.md` | 배포 런북: EC2 생성 → 서버 설정 → 도메인 → 인증서·HTTPS → Secrets·자동 배포 → 백업·점검 → 문제 해결·롤백 |
| `CONTRIBUTING.md` | 협업 규칙: 소통, 브랜치, 이슈, 커밋 컨벤션, PR, 코드 규칙, 의사결정 |
| `CLAUDE.md` | Claude Code가 이 레포에서 작업할 때 가장 먼저 읽는 안내서 (절대 규칙, 결정/미정 사항) |
| `docs/context/project.md` | 대회 개요·일정·심사 기준·서비스 기획 |
| `docs/context/conventions.md` | 레포 규칙 (Dopamine-Ledger 기준 + 개선점) |
| `docs/context/infra.md` | 인프라 설계 (nginx·HTTPS·EC2·CI/CD) |
| `docs/context/setup-tasks.md` | 기본 세팅 작업 목록 (T0~T7) |
| `.claude/commands/infra-setup.md` | Claude Code에서 `/infra-setup`으로 세팅 작업을 실행하는 커맨드 |
