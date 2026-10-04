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
│   ├── images.py               ←   사진 정리 (EXIF 촬영 위치 삭제·크기 줄이기)
│   ├── tests.py
│   └── apps.py
│
├── accounts/                   ← 회원 (커스텀 User, 카카오 로그인)
│   ├── models.py               ←   User (닉네임, 가입 7일 규칙)
│   ├── adapters.py             ←   카카오 첫 로그인 시 자동 가입 + 닉네임 저장
│   ├── admin.py
│   └── tests.py
│
├── places/                     ← 장소 데이터 (지역·건물·장소·출입구·접근성 필드 정의) + 지도·상세 화면 + 공개 API
│   ├── models.py
│   ├── selectors.py            ←   화면·API 공통 조회 (표시 정책 적용: 기본 숨김, 섹션 분리)
│   ├── facilities.py            ←   출입구·시설 종류별 관측 항목 (값은 기존 제보 이력에 저장)
│   ├── api.py / api_urls.py    ←   공개 읽기 API /api/v1/ (목록·상세·GeoJSON)
│   ├── views.py / urls.py      ←   /map/, /places/<id>/
│   ├── templates/places/       ←   map.html, detail.html, _entrance.html, _facilities.html, _fields.html
│   ├── static/places/          ←   css/places.css, js/map-app.js (지도 화면)
│   ├── data/*.json             ←   기본 데이터 (월계1동, 필드 정의) — 코드 수정 없이 여기서 바꿈
│   ├── data/survey/            ←   답사 양식 template.csv (+ 팀 답사 결과 wolgye1.csv)
│   ├── data/public/            ←   공공데이터 스냅숏 (장애인편의시설 현황, 월계동, 받은 날짜별)
│   ├── geocoding.py            ←   주소·이름 → 좌표 (카카오 로컬 API)
│   ├── public_data.py          ←   공공데이터 가져오기 (항목 대응표 FIELD_MAP, 주거시설 제외)
│   └── management/commands/seed_base.py  ← 기본 데이터 넣기
│
├── reports/                    ← 접근성 값과 그 출처 (제보 묶음·값·확인)
│   ├── test_facilities.py       ←   시설별 제보·운영자 검토·공개 조회·기존 판정 회귀 테스트
│   ├── test_facility_migrations.py ← 기존 출입구 제보·사진·관측값을 보존하는 Migration 테스트
│   ├── models.py
│   ├── selectors.py            ←   "지금 쓸 값" 조회 규칙 (검증된 최신 값)
│   ├── services.py             ←   제보 반영/반려 (처리 기록 + 신호)
│   └── signals.py              ←   report_reviewed 신호 → 판정 앱이 받아서 재판정
│
├── judgments/                  ← 판정 (규칙은 데이터, 엔진, 판정 결과 캐시)
│   ├── models.py               ←   ConditionProfile·RuleSet·Rule·RuleCondition·Judgment
│   ├── engine.py               ←   판정 엔진 (기준값을 코드에 두지 않음)
│   ├── constants.py            ←   화면 문구·색·모양 (표시 정책은 여기 한 곳)
│   ├── receivers.py            ←   제보 반영 → 재판정
│   ├── data/rules_v2.json      ←   판정 규칙 (초안, 최신) — 수치는 여기서만 바꿈. rules_v1.json은 이전 버전
│   └── management/commands/    ←   load_rules, recompute_judgments
│
├── ops/                        ← 운영자 화면 (와이어프레임 10~18번, 관리자 계정만)
│   ├── views.py / urls.py      ←   /ops/ 대시보드·제보 검토·장소 등록
│   ├── services.py             ←   장소 답사 저장, 제보 승인(새 장소 생성)·반려, 기존 정보와 차이, 반복 하향 제보 확인
│   ├── forms.py
│   ├── survey_import.py        ←   팀 답사 CSV 가져오기 (검사 → 저장, 다시 넣어도 중복 없음)
│   ├── management/commands/import_survey.py ← python manage.py import_survey 답사.csv
│   └── templatetags/ops_tags.py ←   제보 상태 문구(대기 중·승인됨·반려됨)
│
├── owners/                     ← 사장님·건물주 (기획 v2 4·6장)
│   ├── models.py               ←   인증 코드·인증 신청·사장님 한마디·가고 싶어요·조회 수·지원사업
│   ├── services.py             ←   코드 인증, 사장님 제보(선언·정정), 가고 싶어요, 대시보드 숫자·경사로 가이드
│   └── views.py / urls.py      ←   /owner/..., /places/<id>/wish/, /support/
│
├── templates/                  ← 전역 템플릿
│   ├── base.html               ←   공통 레이아웃 (모든 페이지가 상속, 상단 바 로그인/로그아웃)
│   ├── account/login.html      ←   allauth 로그인 화면 덮어쓰기 (카카오 버튼만)
│   ├── includes/location_picker*.html ← 위치 고르기 지도 조각 (include 해서 사용)
│   ├── allauth/layouts/base.html ← allauth 기본 화면을 base.html 안에 보여주는 연결 파일
│   ├── 404.html
│   └── 500.html
│
├── static/                     ← 전역 정적 파일
│   ├── css/common.css          ←   디자인 변수(색·간격)와 공통 컴포넌트
│   ├── js/common.js            ←   api() fetch 헬퍼 (CSRF 자동 처리)
│   ├── js/map/kakao-adapter.js ←   카카오맵 호출은 여기 한 곳만 (지도 SDK 교체 대비)
│   ├── js/map/location-picker.js ← 지도를 눌러 위치 고르기 (새 장소 제보·운영자 공용)
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
| `views.py` | `health` — DB에 `SELECT 1`을 해보고 정상이면 200 `{"status": "ok", "db": true}`, 실패면 503. 배포 후 확인·모니터링용<br>`home` — 지도(`/map/`)로 이동 |
| `urls.py` | `/` → home, `/health/` → health. `app_name = "core"`라서 템플릿에서 `{% url 'core:home' %}`로 참조 |
| `context_processors.py` | 모든 템플릿에 `KAKAO_JAVASCRIPT_KEY`를 넘겨줌 → 지도 페이지에서 SDK 로드할 때 사용. **REST 키는 절대 넘기지 않음** |
| `images.py` | `normalize_photo()` — 사진의 EXIF(촬영 위치 등)를 지우고 방향을 바로잡아 1600px JPEG로 다시 저장, **정면 얼굴은 자동으로 흐리게**(OpenCV Haar 검출기, 서버 안에서 처리·비용 없음, 짧은 변의 4%보다 작은 무늬는 무시). 번호판은 무료 모델 정확도가 낮아 운영자 검수. OpenCV를 못 불러오면 가림만 건너뜀 (Dockerfile이 빌드 때 불러와지는지 확인). 모든 사진 업로드가 거침 |
| `tests.py` | 헬스체크 정상(200)·DB 장애(503), 홈 화면 테스트 |
| `apps.py` | 앱 등록 정보 |

---

## 2-1. 회원 — `accounts/`

| 파일 | 역할 |
| --- | --- |
| `models.py` | `User`(Django `AbstractUser` 확장). 화면 표시용 `nickname`, `display_name`, `is_new_account()`(가입 7일 미만 → 하향 제보 검수 규칙). 식별번호는 저장하지 않음 |
| `adapters.py` | 카카오 첫 로그인 때 추가 입력 없이 가입(`is_open_for_signup`), 카카오 닉네임 저장(`populate_user`). 카카오 닉네임이 한글이면 `username`은 allauth가 영문으로 자동 생성 |
| `admin.py` | 관리자 화면 회원 목록 (닉네임 검색) |
| `models.py` `Notification` · `notify.py` · `receivers.py` | **서비스 안 알림** (외부 발송 없음 → 비용 없음). 문구는 `notify.py` 한 곳. 만드는 때: 주민 제보 반영·반려(`report_reviewed` 신호), 사장님·건물주 요청 반영·반려, 인증 승인·반려(`OwnerClaim.review`), 가고 싶어요 가게 판정 상승(`judgments.signals.place_improved` → `owners/receivers.py`, 개선 때 한 번만). 팀 답사·운영자 자기 기록은 알림 없음. 상단 "알림 n"(안 읽은 게 있으면 휴대폰에서도 보임), `/notifications/`를 열면 읽음 처리 |
| `activity.py` · `views.py` · `urls.py` | **내 활동** `/me/` (로그인): 내 제보 상태(확인 중 "주민 확인 n/m명"·"운영진이 확인해요" / 반영됨 / 반려 + 사유), 기여 수, **긍정 배지만**(OP-5, 순위·비교 없음). 배지 기준은 `BADGES` 목록 한 곳에서. 상단 이름 링크·휴대폰 하단 탭·제보 완료 화면에서 들어감 |
| `tests.py` | 7일 경계값, 로그인 화면에 카카오만 있는지, 카카오 인증 페이지로 보내는지, 닉네임 저장, 로그아웃 |

로그인 구조 (`settings.py` "회원·로그인" 구역)
- **일반 회원: 카카오 로그인만** (`SOCIALACCOUNT_ONLY`). 아이디·비밀번호 가입 화면 없음. 이메일 받지 않음, 카카오 토큰 저장 안 함
- **관리자: `/admin/`** 에서 아이디·비밀번호 (`createsuperuser`로 만든 계정)
- 로그인·로그아웃 요청은 모두 POST (링크만으로 로그인·로그아웃시키는 공격 방지)
- 카카오 개발자센터 설정(Redirect URI, 동의 항목)은 `docs/deploy.md` 4-5 참고

## 2-2. 장소 — `places/`

데이터 구조 (기획 v2 5.1 · 8장)

```
Region(지역) ─┬─ Building(건물) ─── Entrance(건물 공용 출입구)
              │        │       └─ AccessFacility(건물 공용 접근 시설)
              └─ Place(가게·시설) ── Entrance(가게 출입구, 대체 출입구 포함)
                               └─ AccessFacility(가게 전용 접근 시설)

FieldDefinition(접근성 필드 정의): 입구 단차·출입문 폭·엘리베이터 … 필드마다 대상(장소/건물/출입구/접근 시설)과 값 종류
```

| 모델 | 핵심 |
| --- | --- |
| `Region` | 서비스 지역. `Place.objects.in_region("wolgye1")`처럼 **모든 장소 조회는 지역을 거침** → 다른 동·구로 확장 가능 |
| `Building` | 건물 공용 정보(공용 출입구·엘리베이터·공용 화장실)의 주인. 가게 책임과 건물 책임을 나눠 보여주기 위함 |
| `Place` | 가게·시설. `building`(선택), `category`, `floor`, `is_closed`(삭제 대신 폐업 처리) |
| `Entrance` | 장소 출입구 **또는** 건물 출입구 (둘 중 정확히 하나 — DB 제약). 출입구마다 따로 판정해 대체 출입구 안내 |
| `AccessFacility` | 출입구 외 시설 식별자. 장소 또는 건물 중 정확히 한 곳에 연결. E/V·E/S·계단·경사로·장애인 화장실·기타 구분. 위치·사진·사실은 Report 이력에 저장 |
| `FieldDefinition` | 필드 키를 자유 텍스트로 쓰지 않기 위한 정의 테이블. 대상(`PLACE`/`BUILDING`/`ENTRANCE`/`FACILITY`), 값 종류(`NUMBER`/`BOOL`/`CHOICE`/`TEXT`), 측정 방법 |

시설 확장 Migration: `places/migrations/0002_alter_fielddefinition_scope_accessfacility.py`(시설 모델), `0003_facility_fields.py`(시설용 필드 정의), `reports/migrations/0006_remove_report_report_has_one_target_or_new_place_and_more.py`(제보 연결·제안 필드·대상 제약 확장). 기존 데이터를 시설로 자동 변환하거나 삭제하지 않는다. 실제 DB 적용은 별도 승인 후 진행한다.

**공공데이터 가져오기** (`places/public_data.py`, `import_public_facilities`): 공공데이터포털 "한국사회보장정보원_장애인편의시설 현황"에서 노원구 목록을 받아 **월계동(법정동 코드 1135010200)·영업 중·주거시설 아닌 곳**만 고르고, 시설마다 "설치된 편의시설 항목"을 받는다. 항목은 뜻이 바로 맞는 것만 값으로 옮김 — 주출입구 높이차이 제거 → 입구 단차 0cm, 승강기 → 엘리베이터 있음(건물), 장애인사용가능화장실 → 장애인 화장실 있음. 문 폭처럼 수치가 없는 건 비워 둬서 휠체어는 "정보 없음"으로 남음(지어낸 값으로 판정하지 않음). 출처는 `공공데이터`, 확인 시각은 데이터 등록일이라 이후 답사·제보가 더 최신이면 그 값이 우선. 좌표가 없으면 카카오 주소 검색. 받은 내용은 `places/data/public/*.json` 스냅숏으로 레포에 두어 **호출 없이 누구나 같은 결과**(이용허락 제한 없음 데이터). 하루 호출 100회 제한 → `--limit`, 이미 가져온 시설은 다시 부르지 않음.

기본 데이터는 `places/data/regions.json`, `field_definitions.json`에 있고 `python manage.py seed_base`로 넣습니다 (여러 번 실행해도 결과 같음). 개발용 compose는 시작할 때 자동 실행.

### 화면과 공개 API

| URL | 내용 |
| --- | --- |
| `/` → `/map/` | 지도 홈 (와이어프레임 1·2·3·6번). 검색창, 이동 조건 선택(마지막 선택 기억), 상태 요약(**어려움 개수는 집계하지 않음**), 기본은 "들어갈 수 있어요"·"도움 받으면"만, **"모든 장소 보기"** 로 어려움·미확인 표시, 마커 팝업, 목록은 **거리순**, 조건 맞는 장소 없음·지도 오류 안내. 지도를 못 불러와도 목록·검색·제보는 동작 |
| `/search/?q=&profile=` | 장소명 검색 (4·5번). 이름순, 이동 조건별 판정·입구 핵심 값·확인 월, 결과 없음 안내 |
| `/places/<id>/` | 상세 (7번): 이동 조건 칩별 **판단 근거**(확인된 사실 + 적용 기준·근거 구분) → 정보 신뢰도(출처·최근 확인·반영된 주민 제보 수) → 가게 입구(대체 출입구·사진) → **건물 공용 입구·시설** → 가게 안 → **확인 중인 제보**("맞아요") → 사장님 한마디 → 제보하기 → 법 안내(OP-8) |
| `/report/new/[?place=<id>]` | 제보 작성 (8번, 로그인 필요). 기존 장소면 주 출입구에 연결(없으면 '정문' 생성), 없으면 새 장소 제안(이름·위치 설명·현재 위치). 사진 필수, 같은 장소 24시간 1회, 입구 정보 또는 설명 필수 |
| `/report/done/` | 제보 완료 안내 (9번) |
| `/reports/<id>/confirm/` (POST) | 다른 주민의 "맞아요" 확인 |
| `/api/v1/meta/` | 지역 정보, 이동 조건 목록, 표시 정책(문구·색·모양·기본 숨김) |
| `/api/v1/places/?region=wolgye1&profile=WHEELCHAIR[&all=1]` | 지도용 목록. 정렬 파라미터 없음 (접근성 낮은 순 정렬 금지) |
| `/api/v1/places/<id>/` | 상세 (건물 공용 / 가게 섹션) |
| `/api/v1/places.geojson?region=wolgye1` | GeoJSON 내보내기 (B2G 데이터 개방, 이동 조건별 판정 포함) |

지도 SDK는 `static/js/map/kakao-adapter.js`의 `TeokMap.create()`로만 씁니다. 다른 지도로 바꾸려면 같은 모양의 어댑터 파일만 새로 만들면 됩니다.

## 2-3. 제보·접근성 값 — `reports/`

**모든 접근성 값은 제보(`Report`)에 속합니다.** 팀 답사·이용자 제보·사장님 선언·AI 판별 모두 같은 구조이고 `source`로 구분합니다.

| 모델·파일 | 핵심 |
| --- | --- |
| `Report` | 제보 묶음 1건 = 사진 1장 + 값 여러 개. 대상은 장소·건물·출입구·접근 시설 중 정확히 하나(DB 제약), 대상 없이 이름이 있으면 새 장소 제안. `facility_kind`·`facility_name`으로 새 시설 제안, 승인 시 시설을 만들어 대상 연결. 상태 `PENDING`(확인 중) → `VERIFIED`(반영) / `REJECTED`(반려) |
| `AccessibilityValue` | 값 하나. 값 종류에 맞는 칸(`value_number`/`value_bool`/`value_text`) 하나만 채움. 대상과 필드의 범위가 다르면 저장 불가 |
| `ReportConfirmation` | 다른 이용자의 "맞아요" 확인 (1인 1회, 본인 제보 확인 불가) |
| `selectors.py` | `current_values(대상)`: 필드별로 **VERIFIED 제보 중 가장 최근 값**만 → 판정에 사용. `pending_fields(대상)`: "확인 중" 표시용 |
| `services.py` | `verify_report` / `reject_report`: 처리자·시각 기록 후 `report_reviewed` 신호 발송 (관리자 화면 액션도 이걸 사용) |

관리자 화면: 제보 목록에서 선택 → "반영" / "반려" 액션.

입력 범위는 `places/validation.py`의 `NUMERIC_LIMITS`를 주민·운영자 Form과
`AccessibilityValue`가 공유한다. 이는 접근성 판정 기준(Rule)이 아니라 잘못된 관측값을
거르는 입력 검증이다. 기존 단차 0~500cm, 출입문·경사로 폭 및 이동식 경사로 길이
0~1000cm, 입구 계단 수 0~50, 시설 계단 수 0~10000, 경사 0~90도 범위를 유지한다.
계단 수는 정수이며 BOOL은 명시적인 참/거짓 값만 허용한다.
`create()`/`save()`는 Form 없이도 검증하고, 기존 저장 데이터는 자동 변경하지 않는다.
`bulk_create()`/`QuerySet.update()`/직접 SQL은 Django의 `save()`를 건너뛰므로 관측값을
쓰는 경로에서 사용하지 않는다. 제보·운영자 요청의 ID는 `core/validation.py`에서
ASCII 양의 정수 및 BigAutoField 범위를 검사한 뒤 DB에 전달한다.

**항목 정의(FieldDefinition)를 끄거나 지울 때** — 새 입력과 공개 표시가 같은 기준(`is_active=True`이고 DB에 있는 항목)을 쓴다.

| | 켜진 항목 | 꺼진 항목 | 지운 항목 (값이 없을 때만 지울 수 있음) |
| --- | --- | --- | --- |
| 주민 제보 폼 (`reports/forms.py`) | 입력칸 있음 | 입력칸 없음, 값을 보내도 저장 안 함 | 같음 |
| 운영자 장소 폼 (`ops/forms.py`) | 입력 | "(사용 중지)"로 잠김, 저장 안 함 | 같음 |
| 장소 상세·API (`places/selectors.py`) | 보임 | 숨김 (저장된 값은 DB에 그대로) | — |

- 다시 켜면 입력·표시가 그대로 돌아온다. 이미 값이 저장된 항목은 지울 수 없다 (`AccessibilityValue.field`가 `PROTECT`).
- 판정 엔진은 항목 상태와 상관없이 저장된 값과 규칙(Rule)으로 계산한다. 항목을 끄는 건 입력·표시를 멈추는 것이지 판정 기준을 바꾸는 게 아니다.
- 기준은 폼을 만들 때마다 DB에서 다시 읽는다 (`places.facilities.active_keys`). 화면을 연 뒤 항목이 꺼져도 제출 시점 기준으로 검사하므로 500이 나지 않는다.

**주민 제보가 반영되는 길** (기획 v2 7장)

| 제보 효과 (`judgments/services.py`가 판정 엔진으로 미리 계산) | 반영 조건 |
| --- | --- |
| 판정이 **내려감** (예: 들어갈 수 있어요 → 혼자 들어가기 어려워요) | 다른 주민 **2명** "맞아요" 또는 운영자 승인 |
| 판정이 내려감 + **가입 7일 미만 계정** | **운영자 승인만** (주민 확인으로 반영 안 됨, 기획 v2 7장) |
| **새 시설 제안 / 출입구 외 시설 제보** | **운영자 승인만**. 반영 전 시설·사진·관측값은 공개 목록에 노출하지 않음. 기존 입구·장소·건물 판정값에는 자동 복사하지 않음 |
| 그 외 (올라감·변화 없음·미확인에서 새 정보) | 다른 주민 **1명** "맞아요" 또는 운영자 승인 |

- 확인 전까지 기존 판정 유지, 해당 값에 "새 제보 확인 중" 표시
- 확인 전 제보 사진은 운영진 검수 전이라 **로그인한 주민에게만** 보임 (기획 v2 4.4)
- **칸을 잘못 적어도 사진 유지** (`core/uploads.py` `KeepPhotoMixin`): 오류로 다시 보여 줄 때 올린 사진을 `media/upload_tmp/`에 무작위 이름으로 임시 보관(EXIF 삭제·얼굴 가림 후)하고, 폼에 서명된 표를 숨겨 둠 → 다시 제출할 때 새 사진이 없으면 그 사진을 씀. 표는 하루 지나면 무효, 하루 지난 임시 파일은 자동 정리. 주민 제보·사장님 선언·정정·사진 교체·주민 사진 수정 요청 폼 공통
- **주민 사진 수정 요청** (`/entrances/<id>/photo-fix/`, 입구 사진 아래 링크): 이유(예전 모습 / 내 얼굴·지인 얼굴 / 번호판·개인 정보 / 기타) + 새 사진(선택). 설명이 `[사진 수정 요청]`으로 시작하는 주민 제보로 저장되고 **운영자만** 처리. 운영자는 지금 사진과 새 사진을 나란히 보고, 승인할 때 "지금 공개된 입구 사진 내리기"를 체크하면 그 사진 파일을 지움. 처리 결과는 알림으로. 일반 제보 24시간 제한에는 걸리지 않음
- 올린 사진은 저장할 때 **EXIF(촬영 위치 GPS·기기 정보)를 지우고** 긴 변 1600px로 줄임 (`Report.save` → `core/images.py`, 주민 제보·사장님 요청·관리자 화면·답사 가져오기 공통). 이 규칙 전에 올라온 사진은 `python manage.py strip_photo_exif`(한 번, `--dry-run`으로 미리 보기)로 정리
- 본인 제보는 확인 불가, 한 사람이 한 번만
- 새 장소 제안(대상 없는 제보)은 운영자가 장소를 만들면서 승인

## 2-4. 판정 — `judgments/`

**판정 기준은 코드(if문)가 아니라 데이터**입니다 (기획 v2 8장). 새 이동 조건 = `ConditionProfile` 행 + `Rule` 행 추가, 코드 수정 없음 (테스트로 증명: `test_new_profile_by_data_only`).

```
RuleSet v1 (사용 중) ─ Rule [휠체어 · 우선순위 20 · 결과 가능 · 근거 법령]
                           └ RuleCondition: 입구 단차 ≤ 2cm
                           └ RuleCondition: 출입문 폭 ≥ 80cm            (조건은 모두 만족해야 함)
                     ─ Rule [휠체어 · 40 · 조건부 · 법령 준용]
                           └ 이동식 경사로 = 예 (없으면 불충족)
                           └ 입구 단차 ≤ 이동식 경사로 길이 × 0.125     (다른 필드 × 배수)
```

| 모델 | 핵심 |
| --- | --- |
| `ConditionProfile` | 이동 조건 (휠체어·유아차·보행 보조기·목발) |
| `RuleSet` | 규칙 버전. 사용 중인 버전은 하나(DB 제약). 판정 결과에 버전을 남김 |
| `Rule` | 결과(가능/조건부/어려움) · 우선순위 · 근거 구분(`LAW` 법령 / `APPLIED` 준용 / `TEAM` 팀 기준) · 근거 설명 |
| `RuleCondition` | 필드 · 비교(≤, ≥, =, 예/아니오 …) · 기준값 또는 "다른 필드 × 배수" · 값이 없을 때(모름 / 불충족) |
| `Judgment` | 판정 결과 캐시(장소 × 이동 조건): 결과, 근거 출입구, 사실 한 줄, 규칙 버전, 개선 시각 |

**엔진 동작 (`engine.py`)**

1. **경로**: 1층 가게는 가게 출입구 각각이 경로. 1층이 아니면 건물 공용 출입구 → **층 이동** → 가게 출입구가 한 경로. 출입구 정보가 없으면 미확인
   - 층 이동은 건물 값(엘리베이터)으로 판정하는 단계로, 규칙의 `stage=FLOOR`인 규칙만 씀. 이동 조건에 층 이동 규칙이 없으면 이 단계를 넣지 않음(v1과 같은 결과)
   - 어려움·조건부가 층 이동 때문이면 사실 한 줄은 "2층 · 엘리베이터 없음"
2. **출입구 판정**: 우선순위 순으로 조건이 모두 맞는 첫 규칙의 결과. 맞는 규칙이 없으면 어려움, 단 정보가 없어 판단 못 한 규칙이 있었으면 **미확인**
3. **경로 판정**: 출입구 하나라도 어려움이면 어려움
4. **장소 판정**: 경로 중 가장 좋은 결과. 순서: 가능 > 조건부 > **미확인 > 어려움** (확인 안 된 다른 출입구가 있으면 어려움으로 단정하지 않음 — 가게 부담 최소화)
5. **사실 한 줄**: 기준에 걸린 값 먼저, 기준을 통과한 값은 제외 (예: `입구 단차 30cm · 계단 수 2칸`)
6. **개선 완료 배지**: 판정이 한 단계 이상 올라가면 기록. 이후 내려가면 배지만 숨김
7. `judge(..., overrides=...)`로 가상의 값을 넣어 계산 가능 → "경사로를 놓으면?" 시뮬레이션용

값은 검증된(`VERIFIED`) 최신 값만 씁니다. 사장님 선언도 사진 확인 전(`PENDING`)에는 판정에 반영되지 않습니다.

**규칙 바꾸기**: 최신 규칙 파일 `judgments/data/rules_v2.json` 수정 → `python manage.py load_rules` (같은 버전은 교체, `activate`면 전체 재판정). 기준을 크게 바꿀 땐 `rules_v3.json`을 새로 만들어 버전을 올리고 `load_rules`의 기본 파일도 바꿉니다. 예전 버전으로 되돌리려면 `load_rules judgments/data/rules_v1.json`.

| 버전 | 내용 |
| --- | --- |
| v1 | 출입구 규칙 (턱·경사로·문 폭·이동식 경사로 1/8) |
| v2 | v1 + **층 이동 규칙**: 2층 이상·지하 가게는 엘리베이터가 있어야 휠체어·유아차·보행 보조기 가능, 목발은 없으면 도움 받으면 가능 (팀 기준) |

> ⚠️ 현재 수치는 **초안**입니다 (판정 기준표 확정 전). 박현웅 님 기준표가 나오면 JSON과 경계값 테스트(`judgments/tests.py`)를 같이 바꿉니다.

## 2-5. 운영자 화면 — `ops/`

주민이 올린 제보를 검토하고, 팀 답사 결과를 입력하는 화면입니다. **관리자(`is_staff`) 계정만** 들어올 수 있고, 상단 바에 "운영자" 링크가 보입니다.
Django 관리자(`/admin/`)는 데이터 전체를 다루는 도구로 남겨 두고, 매일 하는 일만 여기로 뺐습니다.

| URL | 와이어프레임 | 내용 |
| --- | --- | --- |
| `/ops/login/` | 10 | 관리자 아이디·비밀번호 로그인 (`createsuperuser`로 만든 계정) |
| `/ops/` | 11 | 검토 대기·오늘 승인·오늘 반려 수, 최근 제보, 공개 장소 수·이번 주 등록, 최근 수정 장소 |
| `/ops/reports/?status=` | 15 | 제보 목록 (대기/승인/반려 탭). **판정 하향 제보·새 장소·가입 7일 미만** 표시 |
| `/ops/reports/<id>/` | 16·17 | 사진·설명, **기존 공개 정보와 차이**(값이 다르면 강조), **승인하면 판정이 어떻게 바뀌는지**(판정 엔진 미리 계산), 최근 7일 5곳 이상 하향 제보자 경고, 검토 의견, 승인·반려(확인 창). 새 장소 제안은 이름·유형·위치(지도 클릭)를 정해 **장소를 만들면서 승인** |
| `/ops/reports/<id>/done/` | 18 | 처리 완료 안내 |
| `/ops/places/`, `/ops/places/new/`, `/ops/places/<id>/edit/` | 12·13 | 장소 목록·등록·수정. 이름·위치 필수(누락 시 안내 상자), 입구·가게 안 값, 출처·확인일. 저장하면 **'팀 답사' 기록을 새로 추가**(이전 값은 이력으로 남음)하고 재판정 |
| `/ops/places/<id>/saved/` | 14 | 저장 완료 안내 |
| `/ops/poster/` | — | **전시·주민투표용 QR 포스터** (A4 인쇄, 지도 QR·사용법 3단계·지도 표시 설명). 표시 문구·색은 판정 상수 그대로 |
| `/ops/reports/delete/` (POST) | — | **제보 기록 삭제**: 목록에서 체크(모두 선택 가능)하거나 상세의 "이 기록 삭제" → 확인 화면(지울 건수, 그중 지도에 반영된 건수, 사진 수) → 동의 체크 후 삭제. 값·주민 확인·사진 파일까지 지우고, 반영됐던 기록이면 해당 가게를 다시 판정. 주민 제보·사장님 요청만 (팀 답사·공공데이터 기록은 여기서 못 지움) |
| 검토 대기 폴링 | — | 모든 운영자 화면 메뉴(`_nav.html`)가 `ops/api/pending/`(운영자만, JSON)을 **10초마다** 물어 "제보 검토 n"·"사장님 인증 n" 배지와 탭 제목 "(n)"을 갱신하고, 화면을 연 뒤 새로 들어오면 "새로 검토할 일이 n건" 안내. 탭이 안 보이면 멈춤 (`ops/static/ops/js/pending-poll.js`) |
| `/ops/district/` | — | **지역 집계** (기획 v2 8장 구청 대시보드, 운영자만): 이동 조건별 판정 분포, 개선 완료·가고 싶어요·인증 수, **경사로 지원사업 검토 목록**(어려움 가게를 개선 의지 → 가고 싶어요 → 조회 순, 필요한 경사로 길이) + CSV 내려받기. 공개 화면에는 순위·목록을 보여 주지 않음 (`ops/district.py`) |

**위치 고르기** (`templates/includes/location_picker.html` + `static/js/map/location-picker.js`): 지도를 누르면 표시하고 같은 폼의 `lat`/`lng`에 좌표를 넣음. "내 위치로"는 보조. 처음 중심은 지역 설정. 주민 새 장소 제보·운영자 새 장소 승인·장소 등록에서 공용. 새 장소 제보는 지도 위치 또는 위치 설명 중 하나 필수.

확인일: 비우거나 오늘이면 지금 시각, 지난 날짜면 그날 정오로 기록 → 예전 답사를 나중에 입력해도 최신 값이 뒤바뀌지 않음.

**답사 CSV 한 번에 넣기** (F6, `ops/survey_import.py`): 한 줄 = 장소 하나. 칸 이름은 필드 정의에서 만들어서 필드를 추가하면 양식도 따라 바뀜. 장소 등록 화면과 같은 '팀 답사' 기록으로 저장하고 재판정. 이름+주소로 같은 장소를 찾고, 값·확인일이 같으면 건너뜀(다시 넣어도 중복 없음). 잘못된 칸이 하나라도 있으면 모든 줄의 문제를 알려 주고 아무것도 저장하지 않음. 위도·경도가 비면 카카오 주소 검색, 사진은 1600px로 줄이고 EXIF 삭제. 사용법: **[survey-guide.md](survey-guide.md)**

## 2-6. 사장님·건물주 — `owners/`

중간발표 피드백(가게 매출 영향, 사장님·건물주 입장)에 대한 기능입니다. 가게를 평가하지 않고, 사장님에게 **응답권**과 **개선으로 가는 길**을 줍니다 (기획 v2 4·6장).

| 흐름 | 방법 |
| --- | --- |
| 인증 (4.1) | 운영자가 장소 수정 화면에서 **6자리 코드 발급** → **안내 쪽지 인쇄**(`/ops/claim-codes/<id>/print/`, QR·코드가 채워진 주소) → 답사 때 가게에 전달 → 사장님이 `/owner/claim/`에 입력(로그인 전에도 안내가 보이고, 신청할 때 카카오 로그인) → 운영자가 `/ops/claims/`에서 승인. 식별번호는 받지 않음 |
| 상단 메뉴 '내 가게' | `owners/context_processors.py` → 인증 신청이 있는 사람에게만 링크. 승인된 곳이 하나면 그 화면으로 바로, 확인 중이면 "(확인 중)", 건물만 있으면 "내 건물" |
| 사장님 한마디·도움 요청 방법 | `OwnerResponse`. 안내 문구라 **저장하면 바로 공개**, 판정은 안 바뀜. 상세 화면 위쪽 "사장님이 알려준 들어가는 방법"(OP-2)과 "사장님 한마디"(OP-3) |
| 도움 제공·이동식 경사로 선언 (4.2) | 사진이 붙은 **사장님 출처 제보**(`Report.source=OWNER`) → 주민 **1명** 확인 또는 운영자 승인 후 반영. 반영되면 판정 엔진의 경사로 1/8 규칙으로 "도움 받으면 들어갈 수 있어요", 긍정 배지 "도움 제공 가게"(OP-5) |
| 정정 요청 (4.3) | 항목 하나 + 새 값 + 증빙 사진 → 사장님 출처 제보, 주민 **2명** 또는 운영자 승인. 확인 전엔 기존 값 유지 + "사장님이 정정을 요청했어요 (확인 중)". 같은 항목은 진행 중인 요청이 끝나야 다시. 7일 넘으면 운영자 대시보드 알림. 반려 사유는 사장님 화면에 표시 |
| 가고 싶어요 (4.5) | 상세 화면에서 **판정이 '어려움'인 이동 조건에만** 버튼. 누가 눌렀는지는 사장님께 보이지 않고 조건별 숫자만 |
| 개선 알림 (6.2) | 누른 사람에게 상단 "가고 싶어요" 메뉴와 `/wishes/` 화면. 판정이 한 단계라도 올라가면 "좋아진 곳 N" 배지(모바일에서도 보임)와 "좋아졌어요" |
| 지금도 맞아요 | 상세 "정보 신뢰도"의 버튼(로그인, 같은 가게 하루 한 번). `reports.Reconfirmation`에 기록하고 **판정·값은 바꾸지 않음** — 최근 확인일과 "최근 30일 주민 N명 확인"에만 반영. 값을 복사한 새 제보로 만들면 확인 중이던 하향 제보가 승인돼도 묻히므로 따로 기록. 지역 집계의 "재답사가 필요한 가게"(정보 없음 / 180일 넘게 확인 없음)에 쓰임 |
| 정보 충돌 안내 (7장) | 한 항목에 사장님 쪽 값(`OWNER`)과 주민 제보 값(`USER_REPORT`)이 반영·확인 중으로 섞여 있고 서로 다르면, 상세 화면에 "정보가 서로 달라요 — 방문 전에 전화로 확인해 보세요"(+ 전화번호). 운영진이 한쪽을 반영하면 사라짐 (`reports.selectors.conflicting_fields`) |
| 조건별 조회 수 (4.5) | 지도·검색에서 상세로 갈 때 붙는 `?profile=`로 일별 집계(`PlaceViewStat`). 같은 세션·같은 날은 한 번만, 개인 정보 저장 안 함 |
| 사진 교체 요청 (4.4) | `/owner/places/<id>/photo/`: 이유 + 새 사진 → 값 없는 사장님 출처 제보. **주민 확인 없이 운영자만** 승인(얼굴·번호판 확인, `required_confirmations`가 `None`). 승인되면 최신 입구 사진으로 보임. 삭제 요청은 받지 않음 |
| 사장님 대시보드 | `/owner/places/<id>/`: **지금 지도에 보이는 판정**, 이번 달 조건별 조회·가고 싶어요, **경사로 가이드(단차 × 8)**, 지원사업, 보낸 요청과 처리 결과, 건물에 있으면 건물 개선 효과 공유 링크, 법 위반 판정 아님 안내(OP-8) |
| 지원사업 (6장) | `SupportProgram` — 매년 바뀌므로 **관리자 화면에서 수정**. 공개 페이지 `/support/`. 신청은 대신하지 않음 |

**건물주 (5장)**

| 흐름 | 방법 |
| --- | --- |
| 인증 | 장소 수정 화면의 **건물주 인증 코드** 칸(장소가 건물에 연결돼 있을 때) → 가게와 같은 절차, 역할 `BUILDING_OWNER` |
| 건물주 화면 `/owner/buildings/<id>/` | 건물 공용 입구·시설(가게 정보와 분리, OP-4), 건물 안 가게와 판정, 개선 시뮬레이션, 공용 정보 **정정 요청**(건물 입구·건물 공용 항목, 주민 2명 또는 운영자), 지원사업 |
| 개선 시뮬레이션 | `owners.services.simulate`: 건물 공용 입구에 가상 값(예: 고정 경사로 있음)을 넣고 **판정 엔진(`judge`의 overrides)으로 다시 계산** → 이동 조건별 "들어갈 수 있어요" 가게 수 지금/개선 후 + 나아지는 가게. 시나리오는 `SCENARIOS` 목록, 기준값은 규칙 데이터 그대로 |
| 공유 페이지 `/buildings/<id>/improve/` | 로그인 없이 보는 개선 효과. 사장님이 건물주에게, 건물주가 구청에 보여 줄 수 있게. 지원사업 안내로 연결 |

> 2층 이상·지하 가게의 층 이동(엘리베이터)은 규칙 v2부터 판정에 들어갑니다 (`Rule.stage=FLOOR`, 위 "판정 엔진" 절).
> 개선 시뮬레이션도 같은 엔진을 쓰므로 건물 엘리베이터 값이 바뀌면 시뮬레이션 결과도 같이 바뀝니다.

## 3. 템플릿·정적 파일 — `templates/`, `static/`

| 파일 | 역할 · 구성 |
| --- | --- |
| 키보드·스크린리더 | 모든 화면 맨 앞 **본문 바로가기**(Tab 첫 번째), 링크·버튼·입력칸 공통 포커스 테두리(`:focus-visible`), 지도 영역·미리 보기 팝업에 이름, 마커는 이름·판정을 읽는 버튼, 팝업은 열리면 포커스 이동·Esc로 닫으면 누른 마커로 복귀, 목록 개수 변화는 `aria-live`로 읽어 줌. 지도를 못 써도 목록·검색으로 같은 정보 |
| `templates/base.html` | 모든 페이지의 뼈대. 상단 바(로고 + `nav` 블록), Django 메시지, 본문. 각 페이지는 `{% extends "base.html" %}` 후 아래 블록을 채움:<br>`title` · `extra_css` · `nav` · `main_class` · `content` · `extra_js` |
| `templates/404.html` | 없는 페이지 (`DEBUG=False`일 때만 보임) |
| `templates/500.html` | 서버 오류. 오류 상황에서도 뜰 수 있게 `base.html`·`url` 태그 없이 단독 HTML |
| `static/css/common.css` | 맨 위 `:root`의 **디자인 변수**(`--color-primary` 등)만 바꾸면 전체 색이 바뀜. 레이아웃·버튼·입력창·메시지 공통 스타일 |
| `static/js/common.js` | `api(url, {method, body})` — 우리 API 호출 헬퍼. POST 등에는 CSRF 토큰을 자동으로 붙이고, 실패하면 서버의 `detail` 메시지로 에러를 던짐. **큰 글씨 모드** 버튼 처리(선택은 브라우저 localStorage에 저장) |
| 휴대폰 상단 바 | 메뉴가 많아도(큰 글씨·알림·내 가게·운영자) 화면 밖으로 넘치지 않게 메뉴 줄만 옆으로 밀어 봄. 로그아웃은 휴대폰에서 하단 탭 '내 활동' 화면에 |
| 사진 표시 | 입구 사진은 잘리지 않게 전체를 보여 주고(`object-fit: contain`, 세로 사진의 문턱·계단이 안 잘림), 누르면 원본 크기. 사진 파일을 못 불러오면 깨진 그림 대신 "사진을 불러오지 못했어요" (`static/js/common.js`) |
| 큰 글씨 모드 | 상단 "큰 글씨" 버튼 → `<html class="large-text">`. 크기는 `common.css`·`places.css` 끝의 `html.large-text` 블록에서만 키움. `base.html` `<head>`의 한 줄 스크립트가 화면을 그리기 전에 저장된 선택을 적용 (깜빡임 없음) |
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
