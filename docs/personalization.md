# 이동 조건 Preset과 개인화

기존 장소·건물·출입구, 검증된 제보, Rule 기반 판정 엔진을 사용한다. 개인 판정은 요청 시 계산하며 공용 Judgment를 덮어쓰지 않는다. 자기평가 입력과 안내 결과는 안전이나 실제 이용을 보장하지 않는다.

## 기본값

- 기존 휠체어·유아차·보행 보조기·목발의 수정 없는 판정은 기존 Rule과 동일하다.
- `judgments/data/mobility_presets.json`에는 이름과 초기 추천 기준만 정의한다. 수치 기본값은 활성 RuleSet의 ACCESSIBLE 출입구 Rule에서 읽는다. 제보 수치의 허용 범위를 판정 기본값으로 사용하지 않는다.
- 보행이 불편해요는 보행 보조기, 어린이 동반은 유아차, 이동 보조 동반은 휠체어를 **초기 추천**으로 사용한다. 신분이나 연령에 같은 제약이 있다고 단정하지 않는다.
- 어린이·이동 보조 동반은 실제 동반자 조건을 선택하고 별도로 수정한다. 보행이 불편해요의 추천이 맞지 않으면 다른 Preset을 선택하거나 세부 조건을 바꾼다.
- 계단·엘리베이터 등 복잡한 기존 규칙을 임의의 bool 기본값으로 단순화하지 않는다. 빈 입력 / ‘기본 규칙 사용’은 기존 도움·층 이동 규칙을 그대로 사용한다.

## 저장 구조

`accounts.MobilityPreference`: User 1:1 FK(기본 키), `data` JSON, 수정 시각. 기존 회원·장소·제보를 변경하거나 회원마다 초기 설정 행을 만들지 않는다.

```json
{
  "version": 1,
  "rule_version": 2,
  "selected": ["WHEELCHAIR", "ASSISTED_COMPANION"],
  "overrides": {
    "WHEELCHAIR": {"max_step_height_cm": "4"},
    "ASSISTED_COMPANION": {"can_use_stairs": false}
  },
  "companions": {"ASSISTED_COMPANION": "CRUTCH"}
}
```

`rule_version`은 저장 당시 기본 기준 버전이다. 바뀌면 안내하고 명시적으로 입력한 값만 유지한다. 선택하지 않은 Preset의 Override도 보존한다. 형식이 손상되거나 Preset이 비활성화되면 기본값을 표시하고 경고하며, 읽기만으로 원본을 덮어쓰지 않는다.

회원은 본인 설정 API를 사용한다. 익명은 `teokeopne.mobility.guest.v1` localStorage를 사용하고 이전 `teokeopne.profile` 선택을 복원한다. 회원 설정을 익명 저장소로 복사하거나 로그인 시 익명 값을 자동 업로드하지 않는다. 로그아웃 후에는 그 브라우저의 익명 설정으로 돌아간다. 저장이 막히면 화면 내에서만 적용하고 복원 불가를 안내한다. 건강 진단·나이·신원 정보는 받지 않는다.

## 판정과 한계

`judgments.engine.judge_profiles`가 기존 경로/Rule 평가를 재사용한다. 숫자 Override는 비교 기준을 바꾸며 관측값이나 Rule DB는 수정하지 않는다. 명시적 턱 한계는 기존 계단 도움 규칙에도 적용한다. 검증된 경사로·이동식 경사로와 도움 조건은 기존 대안 규칙으로 확인한다.

복수 조건은 **동일한 출입구 경로**에서 모두 충족해야 한다. 각 사람의 다른 최적 입구를 합치지 않는다. 최대 턱·경사는 작은 값, 최소 폭은 큰 값, 계단 이용 가능은 AND, 필수 시설 필요는 OR가 적용된다. 사람별 저장값은 변하지 않는다. 기존 bool 기본 규칙에는 도움 조건이 있어 단일 숫자/불리언으로 병합하지 않고 각 Rule을 같은 경로에서 평가한다. 자유 텍스트 시설 연결은 명시된 층만 인식한다. 세부 시설 사이의 완전한 경로 탐색은 구현하지 않는다.

- 출입문 폭은 실제 출입문 정보와 비교한다. 실내 통로 폭으로 대체하지 않는다.
- 미등록 필수 시설은 ‘없음’과 구분하여 **정보 없음**으로 처리한다.
- E/V는 기존 건물 관측값 또는 이용 가능하고 연결 층이 확인된 AccessFacility를 사용한다. 엘리베이터 불필요+계단 가능으로 바꿔도 확인된 대체 층 이동 경로가 없으면 정보 없음이다.
- AccessFacility 경사로/난간은 특정 Entrance에 연결하는 FK가 없다. 측정값이 있어도 그 입구의 경사로라고 추정하지 않는다. 개인 경사·난간 필수 조건에 해당하는 경로의 연결 정보가 부족하면 정보 없음이다.
- 실내 통로 폭과 휴식 좌석 데이터는 추가 수집이 필요하다. 통로 폭 필수 입력은 정보 없음, 휴식 좌석 **선호**는 판정을 낮추지 않고 안내만 한다.
- 수치는 기존 `places.validation.NUMERIC_LIMITS` 측정 범위, 소수점 한 자리로 검증한다. bool은 JSON true/false만 허용한다. 허용 범위는 입력 데이터 검증 범위이며 모두가 통과할 수 있다는 정책이 아니다.

## API

기존 `/api/v1/meta/`, `/api/v1/places/`, 장소 상세 응답은 유지한다.

- `GET /api/v1/mobility/`: 활성 Preset, 필드/단위/범위, Rule 기본값, 본인 또는 익명 기본 설정, 복원 경고.
- `GET /api/v1/mobility/preferences/`: 로그인한 본인의 설정.
- `PUT /api/v1/mobility/preferences/`: 위 설정 JSON 검증 후 본인에게 저장. 세션 CSRF 필수.
- `DELETE /api/v1/mobility/preferences/`: 본인 설정 초기화. 세션 CSRF 필수.
- `POST /api/v1/mobility/places/`: `{settings, region?, all?: boolean, q?: string, place_ids?: [ID]}`. 개인 조건은 URL 대신 JSON body로 전달하고 DB 저장 없이 계산한다. `q`와 `place_ids`는 동시에 사용할 수 없다. 유효하지 않은 입력 400, 없는 장소/지역 404, 본인 설정 API 비로그인 403. 응답에는 기존 장소 요약과 개인 판정, 병합 기준, 주의/선호 안내가 있다.

설정/판정 응답은 `Cache-Control: private, no-store`를 사용한다. 클라이언트가 다른 user ID를 지정할 수 없다.

## 화면 사용

지도·검색·상세의 ‘내 조건 수정’ → 현재 Preset 선택 → 필요한 항목만 입력 → 설정 저장 → 현재 조건으로 재판정. 기존 네 칩은 유지하고 신규 조건은 ‘다른 이동 조건’에 제공한다. 동반자 Preset에서는 ‘동반자의 실제 이동 조건’ 선택을 표시한다. 복수 조건은 펼침 영역에서 추가하고, 편집할 조건은 현재 Preset에서 선택한다.

취소/Esc는 변경을 버리고 진입 버튼으로 포커스를 돌린다. ‘이 조건 기본값으로’는 편집 중인 Preset의 Override만 제거하며 저장할 때 반영한다. 기본 Preset 전환은 다른 Preset의 저장값을 지우지 않는다. PC는 native dialog, 모바일은 전체 화면 dialog를 사용하고 기존 디자인 토큰, 큰 글씨, 입력 label/단위/도움말을 유지한다. 비동기 오류·빈 결과·계산/저장 중 상태를 안내하고 늦은 응답은 무시한다.

Figma 원본은 수정하지 않았다. 추후 Figma 반영과 경사로/난간 경로 FK, 실내 통로/좌석 정보 수집, 층 연결의 구조화 및 실제 시설 간 경로 연결이 후속 범위다.

## 가본 장소로 참고값 가져오기

‘내 조건 수정’ → ‘가본 장소로 참고값 가져오기’ → 현재 지역의 등록 장소에서 이름/주소로 검색 → 실제 이용한 입구 경로 선택 → 확인값 보기 → ‘참고값으로 채우기’ → 필요하면 직접 수정 → ‘설정 저장’ 순서다. 기본 지도 판정에서 숨겨지는 장소도 이 선택 목록에는 포함한다. 장소 선택만으로 기존 입력을 바꾸거나 설정을 저장하지 않는다.

`GET /api/v1/mobility/places/<ID>/reference/`는 기존 `build_routes`와 `current_values`를 재사용해 검증된 최신 입구 관측값, 확인일, 경로별 수치와 경고를 반환한다. DB는 읽기만 한다. 잘못된 ID는 JSON 400, 없거나 폐업/비활성 지역의 장소는 JSON 404, GET 외 요청은 405다. 기존 장소 목록/API 응답은 변경하지 않는다.

- 여러 입구가 있으면 하나의 경로를 직접 선택한다. 서로 다른 입구의 낮은 턱과 넓은 문을 합치지 않는다.
- 건물 공용 입구와 가게 입구가 포함된 같은 경로에서는 가장 높은 단차와 가장 좁은 문 폭을 참고값으로 제시한다. 일부 입구가 미등록이거나 해당 수치가 빠지면 전체 경로 값을 추정하지 않는다.
- 현재 이용 불가 입구, 비활성 정의, 검토 중 측정 항목, 범위 밖 과거 값은 참고 수치에서 제외한다. 소수점 한 자리로 표현할 수 없는 관측값도 임의로 반올림하지 않는다.
- 턱 높이는 ‘경사로·들어 올리는 도움 없이 표시된 턱을 직접 통과했어요’를 확인한 경우에만 채운다. 경사로 정보가 있으면 도움 이용을 직접 턱 통과로 오인하지 않도록 안내한다.
- 문 폭은 최소 출입문 폭을 지원하는 Preset에만 채운다. 실내 통로 폭으로 대체하지 않는다. 계단 이용 가능, 엘리베이터/화장실/난간 필요 여부, 경사는 방문 사실만으로 추정하지 않는다.
- 이 수치는 자기평가의 출발점이며 실제 최대 이동 능력이나 안전 보장이 아니다. 이후 다른 장소 판정에는 기존 개인화 Override를 사용한다.
- 명시적으로 적용할 때 편집 중인 Preset의 지원 수치만 바꾼다. 다른 Preset/동반자 설정과 기존 bool 값은 보존한다. 취소하면 원래 저장 설정을 유지한다.
- 방문 장소/경로 선택은 설정 JSON과 DB에 기록하지 않는다. 기존 회원/익명 저장 구조와 Model/Migration을 유지한다.
- 검색/장소 오류·빈 목록·입구 미등록을 안내하며 취소, Preset/경로 변경 이후 늦은 응답은 이전 선택을 덮어쓰지 않는다. 검색 칸의 Enter로 설정이 저장되지 않는다.

관련 구현: `judgments/place_reference.py`, `places/mobility_api.py`, `templates/includes/mobility_settings.html`, `static/js/mobility-settings.js`. 관련 테스트: `judgments/test_place_reference.py`, `tests/js/mobility-settings.test.cjs`. 추적 Issue: #70. 이 기능은 DB schema를 추가하지 않는다.

확장 검증(2026-10-08): Django 전체 432개(기존 418 + 신규 14), JS 전체 83개(최신 develop 75 + 신규 8), check/Migration 누락/JS 문법/diff 검사 통과. 임시 test DB의 Chrome에서 PC 1280×800·모바일 390×844·320×640 및 큰 글씨, 다중 입구 7cm/75cm, 건물 공용 경로 5cm/85cm, 입력 보존·저장/복원·입구 미등록·Enter/Esc를 확인했다. 실제 지도 SDK와 운영 PostgreSQL은 검증하지 않았고 실제 DB에는 Migration을 적용하지 않았다.

## Migration과 검증

`accounts/0003_mobilitypreference`는 새 테이블만 추가한다. 기존 User/Place/Entrance/Report 데이터의 변환은 없다. 구현 검증은 메모리/임시 test DB에서만 수행하며 실제 local/production DB에는 적용하지 않는다. 운영 반영은 승인된 PR과 기존 배포 Migration 정책을 따른다.

CI와 같은 `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py test`, `node --test tests/js/*.test.cjs`를 사용한다. `judgments/test_mobility.py`, `accounts/test_mobility.py`, `accounts/test_mobility_migration.py`, `tests/js/mobility-settings.test.cjs`가 개인 기준, 공통 경로, 저장/권한/손상 복원, 기존 데이터 보존, UI 상태와 기존 기능 호환성을 검증한다.

## 구현 검증 기록 (2026-10-08)

- 기준: 최신 `origin/develop` `d6bff27`. 기존 Django 383개 + 신규 35개 = 418개 통과, 기존 JS 31개 + 신규 13개 = 44개 통과. Fail/Skip 없음. Django check, Migration 누락 검사, JS 문법 검사, git diff 공백 검사 통과.
- CI에는 별도 lint/build 단계가 없다. Python 가상환경과 SQLite 메모리 test DB로 동일한 검사 명령을 실행했다. 운영 PostgreSQL/배포 검증은 실행하지 않았다.
- 임시 test DB/가상 장소 40개를 사용하는 Chrome에서 PC 1280×800, 모바일 390×844, 좁은 모바일 320×640 및 큰 글씨를 확인했다. 숫자 저장/복원, 5→40곳 재판정, 0곳 빈 상태, 다수 목록 스크롤, 동반자 기준 변경, 검색→상세 연결, 범위 초과 저장 방지, Tab/Esc/취소를 확인했다.
- 브라우저는 익명 흐름을 검증했고 회원 저장·사용자 간 격리·CSRF·로그아웃은 API/JS 테스트로 검증했다. 외부 지도 키를 쓰지 않아 브라우저에서는 SDK 실패 시 목록 대체 흐름을 확인했다. 실제 카카오 지도 마커/운영 로그인은 후속 환경 검증이 필요하다.
- 현재 단계에서 실제 DB Migration, commit, push, PR, merge, Figma 수정은 수행하지 않았다.

## 변경 파일

- 판정/설정: `judgments/engine.py`, `judgments/mobility.py`, `judgments/mobility_checks.py`, `judgments/data/mobility_presets.json`
- 회원 저장: `accounts/models.py`, `accounts/mobility_api.py`, `accounts/migrations/0003_mobilitypreference.py`
- 장소 API/화면 데이터: `places/api_urls.py`, `places/mobility_api.py`, `places/views.py`
- 화면: `templates/includes/mobility_settings.html`, `static/js/mobility-settings.js`, `places/templates/places/map.html`, `places/templates/places/search.html`, `places/templates/places/detail.html`, `places/static/places/js/map-app.js`, `places/static/places/css/places.css`
- 테스트: `judgments/test_mobility.py`, `accounts/test_mobility.py`, `accounts/test_mobility_migration.py`, `tests/js/mobility-settings.test.cjs`
- 문서: `README.md`, `docs/structure.md`, `docs/personalization.md`
