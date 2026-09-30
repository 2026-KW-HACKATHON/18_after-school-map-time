# ♿ 턱없네

> **턱없네는 가게를 평가하지 않습니다. 들어가는 방법을 알려주고, 문턱을 없앨 수 있게 연결합니다.**
> 휠체어·유아차·보행 보조기 등 **이동 조건별로** 월계1동 가게에 들어가는 방법을 알려주는 접근성 지도 웹서비스.

🌐 **서비스:** https://teokeopne.duckdns.org

2026 광운대학교 해커톤 · 18조 **방과 후 지도타임** · 카테고리: 배리어프리 및 생활 편의

---

## 📌 프로젝트 소개

월계1동은 노후 건물, 계단, 턱, 고르지 않은 인도가 많고 어르신 비율이 높습니다.
그런데 "이 가게에 휠체어·유아차로 들어갈 수 있는지"에 대한 정보는 어디에도 정리되어 있지 않아, **직접 가봐야 알 수 있습니다(헛걸음).**

턱없네는 가게마다 **입구 턱 높이, 경사로, 출입문 폭, 내부 단차, 장애인 화장실, 엘리베이터**를 구조화해서 기록하고,
사용자가 고른 이동 조건(휠체어 / 유모차 / 보행 보조기 / 목발 / 캐리어)에 맞춰 **이용 가능한 곳만** 보여줍니다 — "각자에게 필요한 지도".

- 초기 데이터: 팀원이 직접 답사해서 시딩
- 이후: 주민 제보(입구 사진 한 장 + 체크 몇 번)로 확장 → 불편을 겪은 당사자가 정보 제공자가 되는 선순환

### 네 이해관계자가 모두 얻는 구조

| 이해관계자 | 우려 | 턱없네가 주는 것 |
| --- | --- | --- |
| 이동약자 | 헛걸음, 정보 부재 | 내 조건으로 들어갈 수 있는 곳만 보이는 지도 |
| 가게 사장님 | "들어가기 어려운 가게"로 찍혀 손님이 줄까 봐 | 직접 보완 정보를 올릴 권리(도움 제공·이동식 경사로·다른 출입구), 잠재 손님 수요 데이터, 무료 경사로 지원사업 연결 |
| 건물주 | 건물 구조 때문에 평판이 나빠질까 봐 | 가게 책임과 건물 책임을 나눠 표시, 개선 시 건물 안 가게 전체가 좋아지는 효과를 수치로 제시 |
| 노원구청 | 경사로 지원사업 대상 발굴이 어려움 | 수요가 있는 가게·개선 의지가 있는 가게 데이터 |

### 설계 원칙

- **평가하지 않고 사실만** — 점수·순위·별점 없음. 수치와 사진만. "어려움"도 빨간색이 아닌 회색
- **막힌 정보보다 방법 먼저** — 다른 출입구, 도움 요청 방법, 이동식 경사로를 먼저 보여줌
- **사장님 응답권** — 모든 가게 상세에 사장님 코멘트 영역
- **나쁜 쪽 정보는 검증 후 반영** — 판정이 내려가는 제보는 확인 전까지 기존 판정 유지
- **돈으로 판정·노출을 바꿀 수 없음** — 가게 과금·유료 노출·공개 랭킹 없음

> 자세한 기획은 [docs/context/owner-and-expansion.md](docs/context/owner-and-expansion.md) (기획 v2) 참고.

---

## ✨ 핵심 기능

| ID | 기능 | 설명 | 상태 |
| --- | --- | --- | :--: |
| F1 | 🗺️ 장소 마커 | 카카오맵 위 월계1동 가게·시설 마커 | ✅ |
| F2 | 📐 접근성 정보 | 턱 높이(cm), 경사로, 문 폭(cm)·형태, 내부 단차, 장애인 화장실, 엘리베이터 | ✅ |
| F3 | ♿ 조건별 안내 | 이동 조건을 고르면 판정 규칙에 따라 **들어갈 수 있어요 / 도움 받으면 들어갈 수 있어요 / 혼자 들어가기 어려워요 / 아직 정보가 없어요** 4단계로 표시 (색 + 모양, 어려운 곳은 기본 숨김) | ✅ |
| F4 | 🏪 장소 상세 | 입구 사진, 접근성 필드값, 마지막 확인일 | ✅ |
| F5 | 📸 간단 제보 | 사진 + 체크박스 + 현재 위치 자동 입력 | 예정 |
| F6 | 🚶 답사 데이터 | 팀 직접 답사로 만든 시드 데이터 — 답사 양식 CSV를 한 번에 가져오기 ([답사 가이드](docs/survey-guide.md)) | 🔧 도구 완료 · 답사 중 |
| M-8 | 🏢 건물·가게 분리 | 건물 공용 입구와 가게 입구를 나눠 표시, 출입구별로 판정 (대체 출입구 포함) | ✅ |
| M-9 | 📏 판정 규칙 데이터화 | 판정 기준을 코드가 아닌 데이터로 관리, 규칙 버전·근거(법령/준용/팀 기준) 기록 | ✅ |
| M-10 | 🛡️ 제보 검증 | 판정이 내려가는 제보는 다른 사용자 확인·관리자 승인 후 반영 | 예정 |
| M-11 | 🗾 지역 확장 구조 | 모든 데이터를 지역(Region) 단위로 관리 → 노원구·서울로 확장 가능 | ✅ |

> ✅ = 1차 구현 완료. 판정 기준 수치는 초안(`judgments/data/rules_v2.json`, 2층 이상 엘리베이터 판정 포함)이며 판정 기준표 확정 후 교체합니다.

**사장님·건물주 기능 (Should, ✅):** 사장님 인증(6자리 코드 + QR 안내 쪽지, 상단 "내 가게" 메뉴), 도움 제공·이동식 경사로 선언(사진 확인 후 반영), 정정 요청, 입구 사진 교체 요청, "가고 싶어요" + 사장님 대시보드(조건별 조회 수·경사로 가이드), 경사로 설치 지원사업 안내, 공개 API·GeoJSON 내보내기

**개선 연결·분쟁 방지 (✅):** "가고 싶어요" 누른 가게가 좋아지면 알림, 사장님 정보와 주민 제보가 다르면 "방문 전 전화 확인" 안내, 운영자용 **지역 집계**(판정 분포·경사로 지원사업 검토 목록 CSV — 구청 협력용, 비공개)

**어르신·전시 대비 (✅):** 모든 화면 상단 **큰 글씨** 버튼(선택 기억), 전시·주민투표용 QR 포스터(운영자 화면에서 인쇄)

**건물주 기능 (Could, ✅):** 건물주 인증, 건물 공용 정보 정정 요청, 건물 입구 **개선 시뮬레이션**(판정 엔진으로 재계산)과 로그인 없이 보는 공유 페이지

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
| `KAKAO_REST_API_KEY` | 카카오 REST 키 (**서버 전용**, 카카오 로그인 client_id로도 사용) | (발급값) |
| `KAKAO_CLIENT_SECRET` | 카카오 로그인 Client Secret (보안 설정에서 '사용함'일 때만) | |
| `AI_VISION_API_KEY` | AI 사진 판별 API 키 (서비스 미정) | |
| `DOMAIN` | 배포 도메인 (배포 서버에서만, `https://` 없이) | `teokeopne.duckdns.org` |
| `NGINX_CONF` | nginx 설정 선택: 인증서 발급 전 `http` → 발급 후 `https` | `http` |
| `IMAGE_TAG` | 배포 이미지 태그. 롤백할 때만 이전 커밋 SHA로 변경 | `latest` |

### 테스트 실행

```bash
docker compose exec web python manage.py test
```

장소 선택 UI의 검색·핀·좌표 동기화 테스트는 Node.js 18 이상에서 추가 패키지 없이 실행합니다.

```bash
node --test tests/js/location-picker.test.cjs
```

새 장소 제보(`/report/new/`)는 장소 이름과 위치 설명 사이에서 카카오맵 장소 검색 및 지도 클릭으로 핀을 선택할 수 있습니다.
선택한 위도·경도는 화면에 표시되며 직접 수정하거나 현재 위치로 채울 수도 있습니다.
검색 결과의 이름·주소·업종·전화번호를 자동 입력하고, 층은 직접 입력합니다.
제안 정보는 제보에 보관되며 운영자가 검토 화면에서 수정·승인할 때 장소에 반영됩니다.
지도 키가 없거나 SDK 연결에 실패하면 좌표·위치 설명으로 제보할 수 있습니다.
실제 지도 검증에는 `KAKAO_JAVASCRIPT_KEY`와 카카오 개발자센터의 실행 도메인 등록이 필요합니다.

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
├── accounts/               # 회원 — 커스텀 User, 카카오 로그인
├── places/                 # 장소 데이터 — 지역·건물·장소·출입구·접근성 필드 정의
├── reports/                # 접근성 값과 출처 — 제보 묶음·값·확인
├── judgments/              # 판정 — 규칙(데이터)·판정 엔진·판정 결과
├── ops/                    # 운영자 화면 — 제보 검토·장소 등록·사장님 인증 승인 (관리자 계정만)
├── owners/                 # 사장님·건물주 — 인증·한마디·선언·정정·가고 싶어요·대시보드·지원사업
├── templates/              # 전역 템플릿 — base.html(공통 레이아웃), 404, 500
├── static/                 # 전역 정적 파일 — 공통 CSS(디자인 변수)·JS(api() fetch 헬퍼)
├── nginx/                  # 배포용 nginx 설정 — http(인증서 발급 전)·https·공통 스니펫
├── scripts/                # 운영 스크립트 — backup_db.sh(DB 백업)
├── docs/                   # 문서 — deploy.md(배포 런북), structure.md(파일별 역할), survey-guide.md(답사·데이터 넣기), context/(기획·인프라 설계)
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

### 주요 화면 · API

| URL | 설명 |
| --- | --- |
| `/` → `/map/` | 지도 홈 — 검색창, 이동 조건 선택, 들어갈 수 있는 곳 우선 표시, 마커 팝업, 거리순 목록 |
| `/search/?q=` | 장소명 검색 |
| `/places/<id>/` | 장소 상세 — 판단 근거, 정보 신뢰도, 건물 공용 입구와 가게 입구를 나눠 표시, 확인 중인 제보 "맞아요" |
| `/report/new/` | 제보 작성 — 기존 장소 입구 정보 또는 새 장소 제안 (로그인·사진 필수) |
| `/api/v1/places/?region=wolgye1&profile=WHEELCHAIR` | 공개 읽기 API (목록) |
| `/api/v1/places.geojson?region=wolgye1` | GeoJSON 내보내기 |
| `/owner/` | 사장님·건물주 화면 — 인증 코드 입력, 대시보드(지금 판정·조건별 조회 수·가고 싶어요·경사로 가이드·지원사업), 한마디·도움 제공 선언·정정 요청·사진 교체 요청, 건물주 화면(`/owner/buildings/<id>/`) |
| `/buildings/<id>/improve/` | 건물 입구 개선 효과 공유 페이지 (로그인 없이) |
| `/wishes/` | 내가 "가고 싶어요" 누른 가게와 개선 여부 |
| `/support/` | 경사로 설치 지원사업 안내 |
| `/ops/` | 운영자 화면 — 대시보드, 제보 검토(판정 변화 미리보기·승인·반려·새 장소 등록), 장소 등록·수정, 사장님·건물주 인증 코드 발급·안내 쪽지·승인, 지역 집계(구청용), 전시 포스터 |
| `/admin/` | 관리자 — 전체 데이터·판정 규칙·건물 정보 관리 |

> **앱(폴더) 경계 = 기능 경계 = 담당자 경계.** 도메인 앱(장소·제보 등)은 팀 ERD 확정 후 추가합니다.
> 파일 하나하나의 역할과 구성은 **[docs/structure.md](docs/structure.md)** 에 정리되어 있습니다.

---

## 🗓 개발 로드맵

| 시기 | 목표 | 상태 |
| --- | --- | :--: |
| 9/26 | 레포 규칙 · Docker 개발 환경 · CI | ✅ |
| 9/26 | 배포 구성 (nginx · HTTPS 설정 · 자동 배포 워크플로우 · 백업 · 런북) | ✅ |
| 9/27 | EC2 · 도메인 · HTTPS 실제 적용, `develop` 머지 시 자동 배포 | ✅ |
| 9/28(월) | 중간발표·멘토링 → 피드백 반영한 기획 v2 (가게·건물주 관점, 확장성) | ✅ |
| ~ 10/7 | ERD v2 확정, Must 기능 개발 시작 | ⏳ |
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
| [django-allauth](https://allauth.org/) | 카카오 로그인 | MIT |
| [PyJWT](https://github.com/jpadilla/pyjwt) · [cryptography](https://cryptography.io/) · [oauthlib](https://github.com/oauthlib/oauthlib) | allauth 의존성 (토큰 처리) | MIT · Apache-2.0/BSD · BSD-3-Clause |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | `.env` 로드 | BSD-3-Clause |
| [dj-database-url](https://github.com/jazzband/dj-database-url) | DB URL 파싱 | BSD-3-Clause |
| [psycopg2](https://www.psycopg.org/) | PostgreSQL 드라이버 | LGPL-3.0 |
| [Gunicorn](https://gunicorn.org/) | WSGI 서버 | MIT |
| [Pillow](https://python-pillow.org/) | 이미지 처리 | MIT-CMU |
| [Requests](https://requests.readthedocs.io/) | 외부 API 호출 | Apache-2.0 |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) (cdnjs) | 사장님 인증 안내 쪽지의 QR 코드 | MIT |
| [PostgreSQL](https://www.postgresql.org/) | 데이터베이스 | PostgreSQL License |
| [Nginx](https://nginx.org/) | 리버스 프록시 (배포) | BSD-2-Clause |
| [Pretendard](https://github.com/orioncactus/pretendard) | 웹폰트 | SIL OFL 1.1 |
| [카카오맵 API](https://apis.map.kakao.com/) | 지도 · 장소 정보 | [카카오 API 이용약관](https://developers.kakao.com/terms/latest/ko/site-policies) |

### 참고 자료

- 노원구 생활밀착형 소규모시설 경사로 설치 지원 — [헤럴드경제 (2025-07)](https://www.heraldk.com/article/2025072413411590978), [파이낸셜뉴스 (2025-07)](https://www.fnnews.com/news/202507251331065891)
- 다른 자치구 경사로 지원 — [광진구 (시정일보, 2026-08)](https://www.sijung.co.kr/news/articleView.html?idxno=435912), [동작구 (아시아경제, 2026-08)](https://view.asiae.co.kr/article/2026080409135268529), [약국 경사로 지원 현황 (약사공론, 2026-08)](https://www.kpanews.co.kr/news/articleView.html?idxno=541231)
- 판정 참고 기준: 장애인·노인·임산부 등의 편의증진 보장에 관한 법률 시행규칙 [별표 1] (법 위반 판정이 아닌 참고 기준으로 사용)

### 기타

- 레포 규칙·Docker·CI 구성 방식은 팀장이 PM·인프라를 맡았던 [pirogramming/Dopamine-Ledger](https://github.com/pirogramming/Dopamine-Ledger)의 협업 규칙을 참고했습니다. (앱 코드는 사용하지 않음)
- 개발 과정에서 AI 도구(Claude Code)를 활용했으며, 결과물은 팀원 전원이 검토·이해한 뒤 반영합니다.
