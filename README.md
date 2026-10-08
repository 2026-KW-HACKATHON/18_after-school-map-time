# ♿ 턱없네

> **턱없네는 가게를 평가하지 않습니다. 들어가는 방법을 알려주고, 문턱을 없앨 수 있게 연결합니다.**
> 휠체어·유아차·보행 보조기 등 **이동 조건별로** 월계1동 가게에 들어가는 방법을 알려주는 접근성 지도 웹서비스.

🌐 **서비스:** https://teokeopne.help (www.teokeopne.help·이전 주소 teokeopne.duckdns.org는 이 주소로 자동 이동)

2026 광운대학교 해커톤 · 18조 **방과 후 지도타임** · 카테고리: 배리어프리 및 생활 편의

> **현재 상태 (2026-10-08):** 본선 무박 2일 진행 중. 서비스는 실제 도메인에서 운영 중이며 AI 기능(Google Gemini)도 켜져 있습니다.
> 본선 중 작업: Figma 디자인 적용 · 판정 기준표 반영 · 개인화 기능. 테스트 Django 383개 + 화면 JS 31개 통과. 코드는 [MIT License](LICENSE).

---

## 📌 프로젝트 소개

월계1동은 노후 건물, 계단, 턱, 고르지 않은 인도가 많고 어르신 비율이 높습니다.
그런데 "이 가게에 휠체어·유아차로 들어갈 수 있는지"에 대한 정보는 어디에도 정리되어 있지 않아, **직접 가봐야 알 수 있습니다(헛걸음).**

턱없네는 가게마다 **입구 턱 높이, 경사로, 출입문 폭, 내부 단차, 장애인 화장실, 엘리베이터**를 구조화해서 기록하고,
사용자가 고른 이동 조건(휠체어 / 유아차 / 보행 보조기 / 목발)에 맞춰 **들어갈 수 있는 곳을 먼저** 보여줍니다 — "각자에게 필요한 지도".
들어가기 어려운 곳은 사장님·건물주와 노원구 경사로 설치 지원사업으로 **개선을 연결**합니다.

- 초기 데이터: 팀원이 직접 답사해서 시딩 (답사 양식 CSV 한 번에 가져오기)
- 이후: 주민 제보(입구 사진 한 장 + 체크 몇 번)와 "지금도 맞아요" 재확인으로 확장 → 불편을 겪은 당사자가 정보 제공자가 되는 선순환

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
| F5 | 📸 간단 제보 | 사진 + 체크박스 + 현재 위치 또는 지도에서 위치 고르기, 새 장소 제안(카카오 장소 검색) | ✅ |
| F6 | 🚶 답사 데이터 | 팀 직접 답사로 만든 시드 데이터 — 답사 양식 CSV를 한 번에 가져오기 ([답사 가이드](docs/survey-guide.md)) | 🔧 도구 완료 · 답사 중 |
| M-7 | 🎨 표시 정책 v2 | 평가 대신 안내 문구, 빨간색 없음(어려움은 회색), 색 + 모양, 어려운 곳 기본 숨김 | ✅ |
| M-8 | 🏢 건물·가게 분리 | 건물 공용 입구와 가게 입구를 나눠 표시, 출입구별로 판정 (대체 출입구 포함) | ✅ |
| M-9 | 📏 판정 규칙 데이터화 | 판정 기준을 코드가 아닌 데이터로 관리, 규칙 버전·근거(법령/준용/팀 기준) 기록. 2층 이상은 층 이동(엘리베이터)까지 판정 | ✅ |
| M-10 | 🛡️ 제보 검증 | 판정이 내려가는 제보는 주민 2명 확인 또는 운영자 승인 후 반영, 가입 7일 미만 계정의 하향 제보는 운영자만, 같은 장소 24시간 1회 | ✅ |
| M-11 | 🗾 지역 확장 구조 | 모든 데이터를 지역(Region) 단위로 관리 → 노원구·서울로 확장 가능 | ✅ |
| S-AI | 🤖 AI 사진 판별 | 제보 사진·설명에서 입구·시설 항목 **후보와 근거**를 뽑아 운영자 검토를 돕고, 주민은 제보 화면에서 'AI로 항목 채우기'로 빈 칸을 채움 (자동 승인 없음) | ✅ 운영 중 |
| — | 🎨 Figma 디자인 · 📏 판정 기준표 · 👤 개인화 | 본선 중 반영 | 🔧 진행 중 |

> ✅ = 구현 완료 · 🔧 = 진행 중. 판정 기준 수치는 초안(`judgments/data/rules_v2.json`)이며 본선 중 판정 기준표로 교체합니다. F6은 도구 완료 후 실제 답사 데이터 입력 중입니다.

**사장님·건물주 기능 (Should, ✅):** 사장님 인증(6자리 코드 + QR 안내 쪽지, 상단 "내 가게" 메뉴), 도움 제공·이동식 경사로 선언(사진 확인 후 반영), 정정 요청, 입구 사진 교체 요청, "가고 싶어요" + 사장님 대시보드(조건별 조회 수·경사로 가이드), 경사로 설치 지원사업 안내, 공개 API·GeoJSON 내보내기

**AI 사진 판별 (✅ 서버에서 사용 중, 2026-10-05~):** Google Gemini API **유료 등급**(`gemini-3.5-flash-lite`, 입력을 구글 제품 개선에 쓰지 않음). 개인정보 고지는 법적 검토(신지현) 완료.
- **운영자 검토 보조** — 제보 검토 화면에서 "AI 후보 불러오기" → 입구 단차·계단·경사로·문 폭·문 형태와 엘리베이터·계단·경사로·화장실 등 접근 시설 항목의 **후보·근거·확실성**을 표로 보여 줌. 운영자가 고른 값만 제보에 저장하고 승인은 직접
- **주민 'AI로 항목 채우기'** — 제보 화면에서 버튼을 눌렀을 때만 사진·설명을 보내 **빈 칸만** 채우고 근거 표시 (1명 하루 3회)
- **지키는 원칙** — 자동 승인 없음 · 근거 없으면 "모름" · 사진은 위치 정보 삭제·얼굴 가림 후, 설명은 전화번호 가림 후 전송 · AI 값이 들어간 제보는 운영자만 승인(이전 주민 확인 제외) · 하루 전체 한도 · 설정이 잘못되면 운영자 화면에 경고
- 명세: 윤재석 「AI 연동 명세서 v1.3」(A안). 구조와 켜는 방법은 [docs/structure.md](docs/structure.md), [docs/deploy.md](docs/deploy.md) 5-5

**공공데이터 연동 (✅):** 공공데이터포털 장애인편의시설 현황에서 월계동 공공·업무시설 46곳을 초기 데이터로 (주거시설 제외, 뜻이 바로 맞는 항목만 값으로, 출처 "공공데이터" 표시)

### 장소별 접근 시설 제보

- 제보 화면에서 **무엇을 확인했나요?** → 출입구 / 엘리베이터 / 에스컬레이터 / 계단 / 경사로 / 장애인 화장실 / 기타 시설을 선택하고, 해당 시설의 입력 항목을 엽니다.
- 시설 종류·소속을 바꾸면 입력 항목과 기존 시설 목록이 자동으로 바뀝니다. 사진·지도 위치·공통 입력은 유지하고, 이전 종류로 돌아가면 작성했던 항목도 복원합니다. JavaScript를 끈 경우에는 작성 전에 전환 버튼을 사용합니다.
- 운영자 **장소 관리** 목록에는 전용·공용 시설별 개수를 표시하고, **장소 수정 → 접근 시설 현황**에서는 출입구·E/V·E/S 등 종류, 시설 이름, 최근 제보 상태와 확인일을 조회합니다. 승인 전 새 시설 제안도 별도로 표시하며 제보 검토로 연결합니다.
- 건물에 연결된 장소는 **가게 전용 / 건물 공용**을 선택할 수 있습니다. 기존 시설을 고르거나 새 시설을 제안한 뒤 위치·사진·이용 가능 여부·설명·확인일을 보냅니다. 수치는 선택 입력입니다.
- 새 시설과 출입구 외 시설 제보는 **운영자 검토 후** 공개합니다. 기존 입구의 주민 확인 흐름은 유지합니다. 같은 시설은 24시간에 한 번 제보하며, 서로 다른 시설은 각각 제보할 수 있습니다.
- 장소 상세와 `GET /api/v1/places/<id>/`에서 가게/건물별 `facilities`, `facility_counts`를 확인합니다. 기존 `entrances`, `fields`, 판정 응답은 유지합니다.
- `Entrance`는 유지하고, `AccessFacility`는 장소 또는 건물 한 곳에 연결합니다. 사진·위치·관측값은 기존 `Report` / `AccessibilityValue` 이력에 보존합니다. 새 시설 사실은 기존 엘리베이터·화장실 BOOL 값에 자동 복사하지 않으며 기존 판정을 바꾸지 않습니다.
- 건물 공용 입구 → 층 이동 시설 → 가게 입구를 나눠 기록할 수 있지만, 시설 간 경로 그래프·자동 경로 탐색·시설을 조합한 새로운 판정은 후속 범위입니다.
- 이 확장의 Migration(`places` 0002·0003, `reports` 0006)은 배포 서버에 적용되어 있습니다. 테스트는 임시 DB에서 시설 등록·조회·검증·검토·기존 데이터 보존을 확인합니다.

**정보 신뢰도·개인정보 (✅):** 주민 "지금도 맞아요" 재확인(최근 확인일 갱신, 판정은 그대로), 운영자 지역 집계의 재답사 대상(180일 넘게 확인 없음), 아이폰 HEIC 사진 업로드(JPEG로 바꿔 저장), 올리기 전 브라우저에서 사진 줄이기(1600px·위치 정보 없이 전송, 10MB 초과 미리 안내), 올린 사진의 촬영 위치(EXIF) 자동 삭제와 **얼굴 자동 가림**(서버 안 OpenCV, 외부 전송 없음), 확인 전 제보 사진은 로그인한 주민에게만

**개선 연결·분쟁 방지 (✅):** "가고 싶어요" 누른 가게가 좋아지면 알림, 사장님 정보와 주민 제보가 다르면 "방문 전 전화 확인" 안내, 운영자용 **지역 집계**(판정 분포·경사로 지원사업 검토 목록 CSV — 구청 협력용, 비공개)

**어르신·접근성·전시 대비 (✅):** 모든 화면 상단 **큰 글씨** 버튼(선택 기억), 본문 바로가기·키보드 포커스 표시·지도 팝업 키보드 사용(스크린리더), 전시·주민투표용 QR 포스터(운영자 화면에서 인쇄)

**제보 편의 (✅):** 칸을 잘못 적어 다시 보여 줘도 올린 사진 유지(사장님 요청 폼 포함), 입구 사진 아래 **"사진에 문제가 있나요? 수정 요청하기"**(예전 모습·얼굴·번호판 → 운영자가 새 사진으로 바꾸거나 지금 사진 내림)

**주민 참여·알림 (✅):** 내 활동(`/me/`) — 내 제보 처리 상태·반려 사유, 기여 수, 긍정 배지 (순위·비교 없음). **서비스 안 알림**(`/notifications/`, 외부 발송·비용 없음) — 제보·사장님 요청 처리 결과, 인증 결과, 가고 싶어요 가게가 좋아졌을 때

**건물주 기능 (Could, ✅):** 건물주 인증, 건물 공용 정보 정정 요청, 건물 입구 **개선 시뮬레이션**(판정 엔진으로 재계산)과 로그인 없이 보는 공유 페이지

---

## 🛠 기술 스택

| 구분 | 기술 |
| --- | --- |
| Backend | Python 3.12, Django 5.2 (LTS), Django REST Framework |
| Frontend | Django Template, HTML/CSS, Vanilla JS (지도 데이터는 DRF JSON API) |
| 지도 | 카카오맵 JavaScript SDK, 카카오 로컬 REST API |
| AI | Google Gemini API (`gemini-3.5-flash-lite`, 구조화 JSON 출력) — `requests`로 직접 호출, 설정으로 OpenAI 전환 가능 |
| 사진 처리 | Pillow, OpenCV(얼굴 자동 가림), pi-heif(아이폰 HEIC), 브라우저 사진 줄이기(Canvas) |
| DB | PostgreSQL 16 (Docker 없이 실행 시 SQLite 폴백) |
| 서버 | Gunicorn, Nginx (리버스 프록시·HTTPS·정적 파일) |
| 인프라 | Docker, Docker Compose, AWS EC2 |
| CI/CD | GitHub Actions (PR마다 Django 테스트 + 화면 JS 테스트, `develop` 머지 시 EC2 자동 배포) |

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
| `AI_ENABLED` | AI 기능 켜기 (운영자 검토 보조 + 주민 'AI로 항목 채우기'). 배포 서버는 `True` | `False` |
| `AI_PROVIDER` | 사진·설명을 보낼 곳: `gemini` 또는 `openai` | `gemini` |
| `GEMINI_API_KEY` | Google AI Studio 키 (**서버 전용**, 결제 연결한 유료 등급 프로젝트만) | |
| `GEMINI_MODEL` | 이미지 입력 + JSON 출력 형식 지원 모델 (사진 판단을 더 원하면 `gemini-3.8-flash`) | `gemini-3.5-flash-lite` |
| `GEMINI_THINKING_LEVEL` | Gemini 3 이후 생각 단계 (`low`/`medium`/`high`, `minimal`은 형식이 깨져 `low`로 바뀜) | `low` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | `AI_PROVIDER=openai`일 때만 | |
| `AI_PREFILL_USER_DAILY_LIMIT` | 주민 1명이 제보 화면 'AI로 항목 채우기'를 하루에 쓸 수 있는 횟수 (0이면 버튼 숨김) | `3` |
| `AI_DAILY_LIMIT` | 서울 시간 하루 외부 분석 시도 한도 (운영자 분석 + 주민 채우기 합산, 0이면 호출 안 함) | `100` (권장 50) |
| `AI_NOTICE_SINCE` | 제보 화면 AI 안내를 붙인 시각 (시간대 포함 ISO 8601). 이전 제보는 보내지 않음 | |
| `AI_NOTICE_VERSION` | 제보 화면 AI 안내 문구 버전. 제보에 기록된 버전과 같아야 보냄 (문구를 바꾸면 SINCE와 함께 올림) | |
| `DOMAIN` | 대표 주소 (배포 서버에서만, `https://` 없이) | `teokeopne.help` |
| `REDIRECT_DOMAINS` | 대표 주소로 301 이동시킬 다른 주소 (공백 구분, 비우면 이동 없음) | `www.teokeopne.help teokeopne.duckdns.org` |
| `CERT_NAME` | 인증서 폴더 이름 (비우면 `DOMAIN`). 인증서 하나에 모든 주소 포함 | `teokeopne.duckdns.org` |
| `NGINX_CONF` | nginx 설정 선택: 인증서 발급 전 `http` → 발급 후 `https` | `http` |
| `IMAGE_TAG` | 배포 이미지 태그. 롤백할 때만 이전 커밋 SHA로 변경 | `latest` |

### 자주 쓰는 관리 명령

| 명령 | 언제 |
| --- | --- |
| `python manage.py seed_base` | 지역·접근성 필드 정의 기본 데이터 (개발 compose는 시작할 때 자동) |
| `python manage.py load_rules` | 판정 규칙(`judgments/data/rules_v2.json`)을 넣고 전체 재판정. 규칙 파일을 바꿨을 때 |
| `python manage.py recompute_judgments` | 규칙은 그대로 두고 전체 장소 다시 판정 |
| `python manage.py import_survey 답사.csv --photos 사진폴더 --dry-run` | 팀 답사 CSV 검사·판정 미리 보기 (`--dry-run` 빼면 저장). [답사 가이드](docs/survey-guide.md) |
| `python manage.py import_survey --template 파일.csv` | 빈 답사 양식 만들기 |
| `python manage.py import_public_facilities --cache places/data/public/wolgye-facilities-20261001.json --dry-run` | 공공데이터(장애인편의시설 현황) 월계동 시설 미리 보기 (`--dry-run` 빼면 저장, 스냅숏이라 호출 0회) |
| `python manage.py strip_photo_exif --dry-run` | 예전에 올라온 사진의 촬영 위치(EXIF) 정리 (한 번). `--all`이면 모든 사진을 다시 처리해 얼굴도 가림 |

> Docker로 실행 중이면 앞에 `docker compose exec web`, 배포 서버에서는 `docker compose -f docker-compose.prod.yml exec -T web`을 붙입니다.

### 테스트 실행

```bash
docker compose exec web python manage.py test
```

2026-10-08 기준 Django 테스트 383개. AI 테스트는 가짜 AI 클라이언트를 써서 키·네트워크·비용 없이 돌아갑니다.

화면 JS 테스트(장소 선택의 검색·핀·좌표 동기화, 제보 시설 종류 전환, 사진 줄이기, AI로 항목 채우기)는 Node.js 18 이상에서 추가 패키지 없이 실행합니다. CI에서도 같이 돌아갑니다.

```bash
node --test tests/js/*.test.cjs
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
├── core/                   # 헬스체크(/health/), 홈, 공통 context processor, 사진 정리(EXIF 삭제·얼굴 가림)
├── accounts/               # 회원 — 커스텀 User, 카카오 로그인, 내 활동(/me/), 서비스 안 알림
├── places/                 # 장소 데이터 — 지역·건물·장소·출입구·접근성 필드 정의
├── reports/                # 접근성 값과 출처 — 제보 묶음·값·확인, AI 사진 판별(ai.py)
├── judgments/              # 판정 — 규칙(데이터)·판정 엔진·판정 결과
├── ops/                    # 운영자 화면 — 제보 검토·장소 등록·인증 승인·지역 집계·전시 포스터·답사 CSV 가져오기 (관리자 계정만)
├── owners/                 # 사장님·건물주 — 인증·한마디·선언·정정·가고 싶어요·대시보드·지원사업
├── templates/              # 전역 템플릿 — base.html(공통 레이아웃), 404, 500
├── static/                 # 전역 정적 파일 — 공통 CSS(디자인 변수·큰 글씨 모드)·JS(api() fetch 헬퍼, 지도 어댑터·위치 고르기)
├── nginx/                  # 배포용 nginx 설정 — http(인증서 발급 전)·https·공통 스니펫
├── scripts/                # 운영 스크립트 — backup_db.sh(DB 백업)
├── docs/                   # 문서 — deploy.md(배포 런북), structure.md(파일별 역할), survey-guide.md(답사·데이터 넣기), context/(기획·인프라 설계)
├── tests/js/               # 화면 JS 테스트 (Node 내장 테스트 러너, 추가 패키지 없음)
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
├── LICENSE                 # MIT License (팀 작성 코드·문서)
├── THIRD_PARTY_NOTICES.md  # 사용한 오픈소스·외부 서비스와 라이선스 준수 방법
└── README.md
```

### 주요 화면 · API

| URL | 설명 |
| --- | --- |
| `/` → `/map/` | 지도 홈 — 검색창, 이동 조건 선택, 들어갈 수 있는 곳 우선 표시, 마커 팝업, 거리순 목록 |
| `/search/?q=` | 장소명 검색 |
| `/places/<id>/` | 장소 상세 — 판단 근거, 정보 신뢰도("지금도 맞아요"), 건물 공용 입구와 가게 입구를 나눠 표시, 확인 중인 제보 "맞아요", "가고 싶어요", 사장님 안내 |
| `/report/new/` | 제보 작성 — 기존 장소 입구 정보 또는 새 장소 제안 (로그인·사진 필수) |
| `/api/v1/places/?region=wolgye1&profile=WHEELCHAIR` | 공개 읽기 API (목록) |
| `/api/v1/places.geojson?region=wolgye1` | GeoJSON 내보내기 |
| `/owner/` | 사장님·건물주 화면 — 인증 코드 입력, 대시보드(지금 판정·조건별 조회 수·가고 싶어요·경사로 가이드·지원사업), 한마디·도움 제공 선언·정정 요청·사진 교체 요청, 건물주 화면(`/owner/buildings/<id>/`) |
| `/buildings/<id>/improve/` | 건물 입구 개선 효과 공유 페이지 (로그인 없이) |
| `/wishes/` | 내가 "가고 싶어요" 누른 가게와 개선 여부 |
| `/me/` | 내 활동 — 내 제보 처리 상태(반려 사유 포함), 기여 수, 긍정 배지 |
| `/notifications/` | 알림 — 제보·요청 처리 결과, 인증 결과, 가고 싶어요 가게 소식 |
| `/support/` | 경사로 설치 지원사업 안내 |
| `/report/ai-prefill/` | (JSON, 로그인) 제보 화면 'AI로 항목 채우기' |
| `/ops/` | 운영자 화면 — **10초마다 새 검토 대기 확인(메뉴 배지·안내·탭 제목)**, 제보 기록 선택 삭제(확인 화면), 대시보드(AI 사용량·설정 경고), 제보 검토(판정 변화 미리보기·**AI 후보 불러오기**·승인·반려·새 장소 등록), 장소 등록·수정, 사장님·건물주 인증 코드 발급·안내 쪽지·승인, 지역 집계(구청용), 전시 포스터 |
| `/admin/` | 관리자 — 전체 데이터·판정 규칙·건물 정보 관리 |

공개 API 오류는 항상 JSON `{"detail": "..."}` 입니다. 없는 장소(`/api/v1/places/999999/`)와 잘못된 주소(`/api/v1/places/abc/`, 없는 API 경로) 모두 `404 application/json`.
슬래시 없는 주소(`/api/v1/places`)는 `/api/v1/places/`로 301. 개발 환경(`DEBUG=True`)에서 잘못된 주소는 Django 디버그 404 화면이 나옵니다.

> **앱(폴더) 경계 = 기능 경계 = 담당자 경계.**
> 파일 하나하나의 역할과 구성은 **[docs/structure.md](docs/structure.md)** 에 정리되어 있습니다.

---

## 🗓 개발 로드맵

| 시기 | 목표 | 상태 |
| --- | --- | :--: |
| 9/26 | 레포 규칙 · Docker 개발 환경 · CI | ✅ |
| 9/26 | 배포 구성 (nginx · HTTPS 설정 · 자동 배포 워크플로우 · 백업 · 런북) | ✅ |
| 9/27 | EC2 · 도메인 · HTTPS 실제 적용, `develop` 머지 시 자동 배포 | ✅ |
| 9/28(월) | 중간발표·멘토링 → 피드백 반영한 기획 v2 (가게·건물주 관점, 확장성) | ✅ |
| 9/29 ~ 10/1 | 기획 v2 모델·판정 엔진, 와이어프레임 18개 화면, 사장님·건물주 기능, 엘리베이터 판정, 지역 집계, 전체 QA | ✅ |
| 10/2 ~ 10/5 | 접근 시설 제보(박현웅), QA 후속·입력 검증, HEIC·브라우저 사진 줄이기, 롤백·복구 런북, AI 명세 v1.3(윤재석) 구현 → Gemini 유료 연동(운영자 검토 보조·시설 분석·주민 'AI로 항목 채우기'), 서버에서 AI 켜기 | ✅ |
| 10/8(목) ~ 10/9(금) | **본선 무박 2일** — Figma 디자인 적용, 판정 기준표 반영, 개인화 기능, 시연 준비 · 10/9 최종발표 | 🔧 |
| 진행 중 | 실제 답사 데이터 입력, 노원구 2026년 지원사업 공고 확인 | ⏳ |
| 10/11(일) ~ 10/13(화) | 전시 + 주민투표 (서비스 무중단 운영) | ⏳ |

---

## 내 이동 조건 수정

지도·검색·장소 상세에서 Preset 기본값으로 바로 탐색하거나 ‘내 조건 수정’으로 본인/동반자의 실제 이동 기준을 저장할 수 있습니다. 신규 Preset은 초기 추천이며 신분에 따른 제약을 뜻하지 않습니다. 데이터 구조·API·판정 한계·test DB Migration 정책은 [docs/personalization.md](docs/personalization.md)를 참고하세요.

수치를 모르겠다면 ‘가본 장소로 참고값 가져오기’에서 등록된 장소와 실제 이용한 입구 경로를 선택할 수 있습니다. 확인된 문 폭과 직접 통과했다고 확인한 턱 높이를 초안에 채우고 수정·저장하세요. 방문 사실만으로 이동 능력이나 시설 필요 여부를 추정하지 않습니다.

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

대회 규정에 따라 사용한 오픈소스와 외부 서비스를 명시합니다. **버전·하위 패키지·바이너리에 포함된 라이브러리까지 전체 목록과 라이선스 준수 방법은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)** 에 있습니다.

### 라이선스 준수

- 모든 오픈소스는 **수정 없이** 공식 배포본(`pip`, Docker 공식 이미지, CDN)으로 사용하고, 다른 프로젝트의 소스 코드를 레포에 복사하지 않았습니다 (대회 규정).
- 서버 이미지에는 각 패키지의 **라이선스·저작권 표시 원문**이 `site-packages/*.dist-info/`에 그대로 들어 있습니다.
- **LGPL**(psycopg2, pi-heif 바이너리의 libheif·libde265, OpenCV 바이너리의 일부 라이브러리)은 수정 없이 별도 공유 라이브러리로 쓰고, 원본 소스 위치를 밝힙니다. `requirements.txt`·`Dockerfile`이 공개돼 있어 다른 버전으로 교체해 다시 빌드할 수 있습니다.
- **MPL-2.0**(certifi)은 수정 없이 사용합니다. **OFL-1.1**(Pretendard)·**MIT**(qrcode-generator)는 원본 CDN 주소로 불러옵니다.
- 공공데이터는 출처(공공데이터포털 · 한국사회보장정보원)를 장소 상세 화면과 이 문서에 표시합니다.
- 외부 API(카카오, Google Gemini)는 각 약관을 따르고, AI 결과는 사람이 확인한 뒤에만 반영합니다.

| 이름 | 용도 | 라이선스 / 약관 |
| --- | --- | --- |
| [Django](https://www.djangoproject.com/) | 웹 프레임워크 | BSD-3-Clause |
| [Django REST Framework](https://www.django-rest-framework.org/) | JSON API | BSD-3-Clause |
| [django-allauth](https://allauth.org/) | 카카오 로그인 | MIT |
| [PyJWT](https://github.com/jpadilla/pyjwt) · [cryptography](https://cryptography.io/) · [oauthlib](https://github.com/oauthlib/oauthlib) | allauth 의존성 (토큰 처리) | MIT · Apache-2.0/BSD · BSD-3-Clause |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | `.env` 로드 | BSD-3-Clause |
| [dj-database-url](https://github.com/jazzband/dj-database-url) | DB URL 파싱 | BSD-3-Clause |
| [psycopg2](https://www.psycopg.org/) (psycopg2-binary) | PostgreSQL 드라이버 | LGPL-3.0-or-later (예외 조항 포함) |
| [Gunicorn](https://gunicorn.org/) | WSGI 서버 | MIT |
| [Pillow](https://python-pillow.org/) | 이미지 처리 | MIT-CMU |
| [OpenCV](https://opencv.org/) (opencv-python-headless) | 제보 사진 얼굴 자동 가림 (정면 얼굴 검출기 포함) | Apache-2.0 |
| [NumPy](https://numpy.org/) | OpenCV 이미지 배열 | BSD-3-Clause |
| [pi-heif](https://github.com/bigcat88/pillow_heif) | 아이폰 HEIC/HEIF 사진 읽기 (JPEG로 바꿔 저장) | BSD-3-Clause (포함된 libheif·libde265는 LGPL-3.0) |
| [Requests](https://requests.readthedocs.io/) (+ urllib3 · idna · charset-normalizer · certifi) | 외부 API 호출 | Apache-2.0 (MIT · BSD-3-Clause · MIT · MPL-2.0) |
| [asgiref](https://github.com/django/asgiref) · [sqlparse](https://github.com/andialbrecht/sqlparse) · [tzdata](https://github.com/python/tzdata) · [cffi](https://github.com/python-cffi/cffi) · [pycparser](https://github.com/eliben/pycparser) | Django·cryptography 의존성 | BSD-3-Clause · BSD-3-Clause · Apache-2.0 · MIT-0 · BSD-3-Clause |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) (cdnjs) | 사장님 인증 안내 쪽지·전시 포스터의 QR 코드 | MIT |
| [PostgreSQL](https://www.postgresql.org/) | 데이터베이스 | PostgreSQL License |
| [Nginx](https://nginx.org/) | 리버스 프록시 (배포) | BSD-2-Clause |
| [Python](https://www.python.org/) (`python:3.12-slim` 이미지) · [Docker](https://www.docker.com/) · [Certbot](https://certbot.eff.org/) | 서버 실행 환경 · 컨테이너 · HTTPS 인증서 | PSF-2.0 · Apache-2.0 · Apache-2.0 |
| GitHub Actions (`actions/checkout`·`setup-python`·`setup-node`, `docker/login-action`, `appleboy/ssh-action`) | CI·자동 배포 | MIT · Apache-2.0 · MIT |
| [Pretendard](https://github.com/orioncactus/pretendard) | 웹폰트 | SIL OFL 1.1 |
| [카카오맵 API](https://apis.map.kakao.com/) · 카카오 로그인 | 지도 · 장소 정보 · 로그인 | [카카오 API 이용약관](https://developers.kakao.com/terms/latest/ko/site-policies) |
| [Google Gemini API](https://ai.google.dev/) (유료 등급) | 제보 사진·설명에서 접근성 항목 후보 추출 | [Gemini API 추가 약관](https://ai.google.dev/gemini-api/terms) (유료 등급: 입력을 제품 개선에 쓰지 않음) |
| [Let's Encrypt](https://letsencrypt.org/) · [DuckDNS](https://www.duckdns.org/) | HTTPS 인증서 · 이전 주소(새 주소로 이동) | 각 서비스 약관 |
| [한국사회보장정보원_장애인편의시설 현황](https://www.data.go.kr/data/15092317/openapi.do) (공공데이터포털) | 월계동 공공·업무시설 초기 데이터 (`places/data/public/`) | 이용허락범위 제한 없음 |

### 📄 라이선스와 저작권

- 이 레포의 코드와 문서는 **[MIT License](LICENSE)** 입니다 (Copyright (c) 2026 18조 방과 후 지도타임).
- MIT는 **팀이 작성한 코드·문서에만** 적용됩니다. 다음은 각자의 라이선스·이용 조건을 따릅니다.
  - 사용한 오픈소스·폰트·외부 서비스 → [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
  - `places/data/public/` 공공데이터 스냅숏 → 공공데이터포털 이용 조건 (출처: 한국사회보장정보원)
  - 서비스에 주민이 올린 사진·글 → 레포에 들어 있지 않음
- **저작권 문제를 막기 위해 하는 일**
  - 다른 프로젝트의 소스 코드를 복사하지 않았습니다. 레포 규칙을 참고한 Dopamine-Ledger도 규칙만 참고했습니다.
  - 아이콘·로고(`static/img/`)는 팀이 AI 도구(Claude)로 새로 만든 그림입니다. 파일 안에 출처 정보(C2PA)가 들어 있습니다.
  - `docs/screenshots/`는 우리 서비스 화면만 찍었습니다(지도 화면 없음). 뉴스 기사는 링크로만 인용합니다.
  - 사진 칸마다 "직접 찍은 사진만, 인터넷·지도 로드뷰 캡처 금지, 올린 사진은 공개됨"을 안내합니다. 운영자는 남이 찍은 사진이 보이면 반려합니다.
  - 판정 참고 기준인 법령(편의증진법 시행규칙)은 저작권 보호 대상이 아니며, 출처를 밝혀 인용합니다.

### 참고 자료

- 노원구 생활밀착형 소규모시설 경사로 설치 지원 — [헤럴드경제 (2025-07)](https://www.heraldk.com/article/2025072413411590978), [파이낸셜뉴스 (2025-07)](https://www.fnnews.com/news/202507251331065891), [서울Pn (2025-07)](https://go.seoul.co.kr/news/newsView.php?id=20250725500121), [시민일보 (2025-07)](https://www.siminilbo.co.kr/news/newsview.php?ncode=1160281934467177), [경향신문 (2025-07)](https://www.khan.co.kr/article/202507251411001)
- 다른 자치구 경사로 지원 — [광진구 (시정일보, 2026-08)](https://www.sijung.co.kr/news/articleView.html?idxno=435912), [동작구 (아시아경제, 2026-08)](https://view.asiae.co.kr/article/2026080409135268529), [약국 경사로 지원 현황 (약사공론, 2026-08)](https://www.kpanews.co.kr/news/articleView.html?idxno=541231)
- 판정 참고 기준: 장애인·노인·임산부 등의 편의증진 보장에 관한 법률 시행규칙 [별표 1] (법 위반 판정이 아닌 참고 기준으로 사용)

### 기타

- 레포 규칙·Docker·CI 구성 방식은 팀장이 PM·인프라를 맡았던 [pirogramming/Dopamine-Ledger](https://github.com/pirogramming/Dopamine-Ledger)의 협업 규칙을 참고했습니다. (앱 코드는 사용하지 않음)
- 개발 과정에서 AI 도구(Claude Code)를 활용했으며, 결과물은 팀원 전원이 검토·이해한 뒤 반영합니다.
- 서비스 안의 AI 기능은 Google Gemini API를 쓰며, 사용 사실과 받는 곳을 제보 화면에 안내합니다.
