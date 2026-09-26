# ♿ 턱없네

> **이 가게, 들어갈 수 있을까?**
> 휠체어·유아차·보행 보조기 등 **이동 조건별로** 월계1동 가게의 접근성을 알려주는 지도 웹서비스.

2026 광운대학교 해커톤 · 18조 **방과 후 지도타임** · 카테고리: 배리어프리 및 생활 편의

---

## 📌 프로젝트 소개

월계1동은 노후 건물, 계단, 턱, 고르지 않은 인도가 많고 어르신 비율이 높습니다.
그런데 "이 가게에 휠체어·유아차로 들어갈 수 있는지"에 대한 정보는 어디에도 정리되어 있지 않아, **직접 가봐야 알 수 있습니다(헛걸음).**

턱없네는 가게마다 **입구 턱 높이, 경사로, 출입문 폭, 내부 단차, 장애인 화장실, 엘리베이터**를 구조화해서 기록하고,
사용자가 고른 이동 조건(휠체어 / 유모차 / 보행 보조기 / 목발 / 캐리어)에 맞춰 **이용 가능한 곳만** 보여줍니다 — "각자에게 필요한 지도".

- 초기 데이터: 팀원이 직접 답사해서 시딩
- 이후: 주민 제보(입구 사진 한 장 + 체크 몇 번)로 확장 → 불편을 겪은 당사자가 정보 제공자가 되는 선순환

---

## ✨ 핵심 기능

| ID | 기능 | 설명 | 상태 |
| --- | --- | --- | :--: |
| F1 | 🗺️ 장소 마커 | 카카오맵 위 월계1동 가게·시설 마커 | 예정 |
| F2 | 📐 접근성 정보 | 턱 높이(cm), 경사로, 문 폭(cm)·형태, 내부 단차, 장애인 화장실, 엘리베이터 | 예정 |
| F3 | ♿ 조건별 판정 | 이동 조건을 고르면 판정 규칙에 따라 필터링. 마커는 **가능 / 조건부 / 어려움 / 미확인** 4단계 색 구분 | 예정 |
| F4 | 🏪 장소 상세 | 입구 사진, 접근성 필드값, 마지막 확인일 | 예정 |
| F5 | 📸 간단 제보 | 사진 + 체크박스 + 현재 위치 자동 입력 | 예정 |
| F6 | 🚶 답사 데이터 | 팀 직접 답사로 만든 시드 데이터 | 예정 |

> 기능 코드는 팀 ERD 확정 후 착수합니다. 현재는 개발·배포 인프라 세팅 단계입니다.

---

## 🛠 기술 스택

| 구분 | 기술 |
| --- | --- |
| Backend | Python 3.12, Django 5.2 (LTS), Django REST Framework |
| Frontend | Django Template, HTML/CSS, Vanilla JS (지도 데이터는 DRF JSON API) |
| 지도 | 카카오맵 JavaScript SDK, 카카오 로컬 REST API |
| DB | PostgreSQL 16 (Docker 없이 실행 시 SQLite 폴백) |
| 서버 | Gunicorn, Nginx (리버스 프록시·HTTPS·정적 파일) |
| 인프라 | Docker, Docker Compose, AWS EC2 |
| CI/CD | GitHub Actions (PR마다 테스트, `develop` 머지 시 EC2 자동 배포) |

---

## 🚀 시작하기 (로컬 개발)

### 사전 요구사항

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (실행 중이어야 함)
- Git

### 실행

```bash
git clone https://github.com/2026-KW-HACKATHON/18_after-school-map-time.git
cd 18_after-school-map-time
cp .env.example .env        # 그다음 .env 의 SECRET_KEY 를 채우세요 (아래 명령)
docker compose up --build
```

브라우저에서 `http://localhost:8000` 접속. `http://localhost:8000/health/` 가 `{"status": "ok", "db": true}` 이면 정상입니다.

> DB 마이그레이션은 web 컨테이너가 시작될 때 자동으로 실행됩니다.

### 최초 1회 세팅

```bash
# SECRET_KEY 생성 → 출력값을 .env 의 SECRET_KEY= 뒤에 붙여넣기
python -c "import secrets; print(secrets.token_urlsafe(50))"

# 관리자 계정 생성 (http://localhost:8000/admin/ 접속용)
docker compose exec web python manage.py createsuperuser
```

### 환경 변수

`.env.example`을 복사해서 `.env`를 만들고 값을 채웁니다. **`.env`는 절대 커밋하지 않습니다** (`.gitignore`에 포함).

| 변수 | 설명 | 예시 |
| --- | --- | --- |
| `SECRET_KEY` | Django 시크릿 키. **비어 있으면 서버가 뜨지 않음** | (위 명령으로 생성) |
| `DEBUG` | 디버그 모드 | `True` (개발) / `False` (배포) |
| `ALLOWED_HOSTS` | 접속 허용 호스트 (콤마 구분) | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | (배포) https 포함 도메인 (콤마 구분) | `https://<도메인>` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Postgres 컨테이너 초기값. 배포는 강한 비밀번호 | `teokeopne` |
| `DATABASE_URL` | DB 접속 정보 (비우면 SQLite) | `postgres://teokeopne:teokeopne@db:5432/teokeopne` |
| `KAKAO_JAVASCRIPT_KEY` | 카카오맵 JS 키 (브라우저 노출 → 카카오 개발자센터에 허용 도메인 등록 필수) | (발급값) |
| `KAKAO_REST_API_KEY` | 카카오 REST 키 (**서버 전용**) | (발급값) |
| `AI_VISION_API_KEY` | AI 사진 판별 API 키 (서비스 미정) | |
| `DOMAIN` | 배포 도메인 (배포 서버에서만, `https://` 없이) | `teokeopne.duckdns.org` |
| `NGINX_CONF` | nginx 설정 선택: 인증서 발급 전 `http` → 발급 후 `https` | `http` |
| `IMAGE_TAG` | 배포 이미지 태그. 롤백할 때만 이전 커밋 SHA로 변경 | `latest` |

### 테스트 실행

```bash
docker compose exec web python manage.py test
```

### 종료

```bash
docker compose down        # 컨테이너 종료 (DB 데이터는 유지)
docker compose down -v     # DB 데이터까지 삭제
```

### 배포 구성 로컬 검증 (선택)

nginx까지 포함한 배포 구성(`DEBUG=False`)을 도메인 없이 내 PC에서 띄워볼 수 있습니다.

```bash
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

`http://localhost/health/` (8000번이 아닌 80번, nginx 경유) 확인 후 `docker compose -f docker-compose.prod.yml down`.

### 서버 배포

AWS EC2 생성부터 HTTPS·자동 배포·백업까지 **[docs/deploy.md](docs/deploy.md)** 런북을 따라 하면 됩니다.

<details>
<summary>Docker 없이 실행하기 (선택)</summary>

`.env`의 `DATABASE_URL`을 비워두면 SQLite로 동작합니다.

```bash
python -m venv venv
source venv/Scripts/activate   # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

</details>

---

## 📁 프로젝트 구조

```
18_after-school-map-time/
├── config/                 # Django 프로젝트 설정 (settings.py, urls.py, wsgi/asgi)
├── core/                   # 헬스체크(/health/), 홈, 공통 context processor
├── templates/              # 전역 템플릿 — base.html(공통 레이아웃), 404, 500
├── static/                 # 전역 정적 파일 — 공통 CSS(디자인 변수)·JS(api() fetch 헬퍼)
├── nginx/                  # 배포용 nginx 설정 — http(인증서 발급 전)·https·공통 스니펫
├── scripts/                # 운영 스크립트 — backup_db.sh(DB 백업)
├── docs/                   # 문서 — deploy.md(배포 런북), structure.md(파일별 역할), context/(기획·인프라 설계)
├── .github/                # 이슈·PR 템플릿, CI·자동 배포 워크플로우
├── .claude/commands/       # Claude Code 팀 공용 커맨드
├── Dockerfile              # 배포용 이미지 (gunicorn)
├── docker-compose.yml      # 개발용: web(runserver) + db(PostgreSQL)
├── docker-compose.prod.yml # 배포용: nginx + web(gunicorn) + db
├── requirements.txt        # 파이썬 패키지 (버전 고정)
├── .env.example            # 환경 변수 템플릿
├── manage.py
├── CLAUDE.md               # Claude Code 작업 안내서
├── CONTRIBUTING.md         # 협업 규칙
└── README.md
```

> **앱(폴더) 경계 = 기능 경계 = 담당자 경계.** 도메인 앱(장소·제보 등)은 팀 ERD 확정 후 추가합니다.
> 파일 하나하나의 역할과 구성은 **[docs/structure.md](docs/structure.md)** 에 정리되어 있습니다.

---

## 🗓 개발 로드맵

| 시기 | 목표 | 상태 |
| --- | --- | :--: |
| 9/26 | 레포 규칙 · Docker 개발 환경 · CI | ✅ |
| 9/26 | 배포 구성 (nginx · HTTPS 설정 · 자동 배포 워크플로우 · 백업 · 런북) | ✅ |
| 9/28(월) | 중간발표·멘토링 (기획 중심) | ⏳ |
| ~ 10/7 | EC2 · 도메인 · 인증서 실제 적용, ERD 확정 | ⏳ |
| 10/8(목) ~ 10/9(금) | **본선 무박 2일** — Must 기능(F1~F6) 구현, 10/9 최종발표 | ⏳ |
| 10/11(일) ~ 10/13(화) | 전시 + 주민투표 (서비스 무중단 운영) | ⏳ |

---

## 👥 팀

| 이름 | 역할 |
| --- | --- |
| 강성훈 (팀장) | PM · BE · 서버 인프라 (DB, 배포) |
| 신지현 | 발표 자료 · 와이어프레임 · UI/UX 디자인 |
| 박현웅 | BE · FE |
| 윤재석 | BE · FE |

협업 규칙(브랜치 전략, 커밋 컨벤션, PR 규칙)은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

---

## 📚 오픈소스 / 출처

대회 규정에 따라 사용한 오픈소스와 외부 서비스를 명시합니다.

| 이름 | 용도 | 라이선스 / 약관 |
| --- | --- | --- |
| [Django](https://www.djangoproject.com/) | 웹 프레임워크 | BSD-3-Clause |
| [Django REST Framework](https://www.django-rest-framework.org/) | JSON API | BSD-3-Clause |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | `.env` 로드 | BSD-3-Clause |
| [dj-database-url](https://github.com/jazzband/dj-database-url) | DB URL 파싱 | BSD-3-Clause |
| [psycopg2](https://www.psycopg.org/) | PostgreSQL 드라이버 | LGPL-3.0 |
| [Gunicorn](https://gunicorn.org/) | WSGI 서버 | MIT |
| [Pillow](https://python-pillow.org/) | 이미지 처리 | MIT-CMU |
| [Requests](https://requests.readthedocs.io/) | 외부 API 호출 | Apache-2.0 |
| [PostgreSQL](https://www.postgresql.org/) | 데이터베이스 | PostgreSQL License |
| [Nginx](https://nginx.org/) | 리버스 프록시 (배포) | BSD-2-Clause |
| [Pretendard](https://github.com/orioncactus/pretendard) | 웹폰트 | SIL OFL 1.1 |
| [카카오맵 API](https://apis.map.kakao.com/) | 지도 · 장소 정보 | [카카오 API 이용약관](https://developers.kakao.com/terms/latest/ko/site-policies) |

- 레포 규칙·Docker·CI 구성 방식은 팀장이 PM·인프라를 맡았던 [pirogramming/Dopamine-Ledger](https://github.com/pirogramming/Dopamine-Ledger)의 협업 규칙을 참고했습니다. (앱 코드는 사용하지 않음)
- 개발 과정에서 AI 도구(Claude Code)를 활용했으며, 결과물은 팀원 전원이 검토·이해한 뒤 반영합니다.
