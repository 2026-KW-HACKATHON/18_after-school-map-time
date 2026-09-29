# 기획 v2 개발 계획 (초안 — PM 승인 전)

> 기준 문서: [`owner-and-expansion.md`](owner-and-expansion.md) (기획 v2)
> 상태: **초안.** 아래 "결정 필요" 항목이 승인되기 전에는 모델·마이그레이션을 만들지 않는다 (v2 12장 1번).
> 현재 레포에는 도메인 모델이 없다(`core`만 존재). 따라서 v2 11장의 "기존 models.py와 비교"는 **팀 ERD와 비교**해야 하며, 이 문서는 v2 11장 표를 기준으로 작성했다.

---

## 1. 앱 구성 (앱 경계 = 기능 경계 = 담당자 경계)

| 앱 | 모델 | 기능 | v2 범위 | 담당 제안 |
| --- | --- | --- | --- | --- |
| `accounts` | `User` | 가입·로그인 (제보·사장님 인증에 필요), 가입일(7일 규칙) | Must 기반 | 강성훈 |
| `places` | `Region`, `Building`, `Place`, `Entrance`, `FieldDefinition`, `AccessibilityValue` | 지도 화면, 장소 상세(건물/가게 섹션 분리), 읽기 API, GeoJSON 내보내기 | F1·F2·F4·F6, M-8, M-11, S-10 | 윤재석 |
| `judgments` | `ConditionProfile`, `RuleSet`, `Rule`, `RuleCondition`, `Judgment` | 판정 엔진, 표시 문구 상수, 전체 재판정 커맨드 | F3, M-7, M-9 | 박현웅 |
| `reports` | `Report`, `ReportConfirmation` | 제보(사진·위치), 확인, 하향 제보 검증 대기, 악성 제보 방지 | F5, M-10 | 윤재석·박현웅 |
| `owners` | `ClaimCode`, `OwnerClaim`, `OwnerResponse`, `CorrectionRequest`, `VisitWish`, `PlaceViewStat`, `SupportProgram` | 사장님·건물주 인증, 도움 제공 선언, 정정 요청, 가고 싶어요, 사장님 대시보드, 지원사업 안내 | S-6~S-9 | 강성훈 |
| `core` | — | 헬스체크, 공통 템플릿 (기존) | — | — |

프론트: 카카오맵 호출은 `static/js/map/kakao-adapter.js` 한 곳에만 둔다 (v2 8장 "지도 SDK 교체").
디자인: 신지현 — 판정 문구·색·아이콘, 상세 화면 섹션, 사장님 안내 문구(OP-8).

---

## 2. 모델 계획 — v2 11장 대비 변경점 (결정 필요)

v2 11장 표를 그대로 구현하면 막히는 곳이 있어 아래처럼 제안한다. **D1~D10을 승인/수정해 주세요.**

| # | v2 11장 | 문제 | 제안 |
| --- | --- | --- | --- |
| D1 | `AccessibilityValue.target`, `Entrance`(place 또는 building), `OwnerClaim`·`CorrectionRequest`의 대상 | "여러 모델 중 하나"를 가리키는 방법이 정해지지 않음 | 대상별 **nullable FK를 나란히** 두고 "정확히 하나만 채워짐"을 DB 제약(`CheckConstraint`)으로 보장. Django의 GenericForeignKey보다 팀원이 설명하기 쉽고 FK 무결성이 지켜짐 |
| D2 | `AccessibilityValue.value` | 판정은 숫자 비교(단차 ≤ 2cm)인데 값 타입이 하나 | `FieldDefinition.value_type`(`NUMBER`/`BOOL`/`CHOICE`/`TEXT`)에 맞춰 `value_number`(Decimal)·`value_bool`·`value_text` 중 하나를 채움. 저장 시 타입 검증 |
| D3 | `Rule`: field·operator·threshold **1개** | 4.2 "단차 ≤ 경사로 길이 ÷ 8 **그리고** 도움 제공 **그리고** 사진 확인" 같은 **복합 조건**을 표현 못함 | `Rule`(profile, outcome, priority, basis, note) + **`RuleCondition`**(field, operator, 고정값 또는 "다른 필드 × 배수") 여러 개를 AND로 결합. 판정 방식은 3장 참고 |
| D4 | `AccessibilityValue`에 photo·created_by가 직접 있음 | 제보 1건(사진 1장)에 필드 값이 여러 개 → 사진·작성자가 값마다 중복, "제보 단위 확인"이 불가 | **`Report`**(제보 묶음: 대상, 사진, 작성자, 출처, 상태) 추가 → 값은 `Report`에 속함. 확인·검수도 제보 단위 |
| D5 | (없음) | 7장 "다른 사용자 2명 확인"을 셀 곳이 없음 | **`ReportConfirmation`**(report, user) 추가. 사용자당 1회, 본인 제보 확인 불가 |
| D6 | `OwnerClaim` | 4.1 "답사 때 6자리 코드 전달"의 코드를 저장할 곳이 없음 | **`ClaimCode`**(place 또는 building, code, used_at) 추가. 1회용, 관리자 화면에서 발급 |
| D7 | `OwnerResponse`에 판정용 값(portable_ramp_length_cm, assistance_offered)과 안내 문구가 섞임 | 판정 엔진이 두 곳을 읽어야 함 | 판정에 쓰는 값은 **`AccessibilityValue`(source=`OWNER`)** 로 저장해 같은 검증 흐름을 탐. `OwnerResponse`는 화면 안내용(연락 방법·시간·대체 출입구 설명·코멘트)만 |
| D8 | (없음) | 4.5 "조건별 조회 수"를 저장할 곳이 없음 | **`PlaceViewStat`**(place, profile, date, count) — 일별 집계만 저장, 개인 식별 정보 없음 |
| D9 | `Judgment`는 결과 캐시만 | 6.3 "개선 완료" 배지(판정이 올라간 날)와 3.1 "DIFFICULT 옆 사실 한 줄"을 알 수 없음 | `Judgment`에 `entrance`(판정 근거 출입구), `reason`(사실 한 줄, 예: "입구 계단 2칸 (약 30cm)"), `improved_at` 추가 |
| D10 | 사용자 모델 언급 없음 | 7장 "가입 7일 미만", 사장님·관리자 구분이 필요 | 커스텀 **`accounts.User`**. ⚠️ 배포·로컬 DB에 이미 기본 사용자 테이블 마이그레이션이 적용돼 있어 **DB를 한 번 초기화**해야 함 (현재 실데이터 없음 → 지금이 가장 싼 시점) |

기타 (결정 불필요, 기본값으로 진행)
- 좌표: `DecimalField(max_digits=9, decimal_places=6)`. `Region.boundary`는 `JSONField`(GeoJSON). 월계1동 규모라 PostGIS 없이 전체 조회 후 지도에서 필터.
- 사진: `ImageField` → media 볼륨 (기존 인프라). 업로드 10MB.
- 모든 장소 조회는 `Region` 스코프를 거침 (`Place.objects.in_region(code)`).

---

## 3. 판정 엔진 설계 (D3 상세 — 박현웅 판정 명세와 맞춰야 함)

```
판정(장소, 이동 조건):
  1. 경로 만들기: 장소의 출입구마다 [건물 공용 출입구(있으면)] + [가게 출입구] 를 하나의 경로로
  2. 경로마다: 현재 규칙셋에서 해당 이동 조건의 Rule을 priority 순서로 보고,
             모든 RuleCondition이 맞는 첫 Rule의 outcome을 그 경로의 결과로
             필요한 필드 값이 없으면 → UNKNOWN
  3. 장소 결과 = 경로 결과 중 가장 좋은 것 (ACCESSIBLE > CONDITIONAL > DIFFICULT > UNKNOWN)
             ※ 모든 경로가 UNKNOWN이 아니면 UNKNOWN보다 DIFFICULT를 우선할지 명세 필요
  4. Judgment에 결과, 근거 출입구, 사실 한 줄, rule_version 저장
```

- 값은 **검증된(`VERIFIED`) 최신 값**만 사용. `PENDING`은 화면에 "확인 중"으로만 표시 (OP-6).
- 새 이동 조건 추가 = `ConditionProfile` + `Rule` 행 추가만으로 동작해야 함 → 테스트로 증명 (v2 8장).
- 경계값 테스트: 단차 2cm / 2.1cm, 단차 = 경사로 길이 ÷ 8 (예: 120cm → 15cm / 15.1cm).
- 규칙 초기 데이터는 마이그레이션이 아닌 **fixture + 관리 명령**(`load_rules`)으로 넣어 관리자 화면에서 수정 가능하게.

---

## 4. 개발 순서 (이슈 단위로 쪼갬)

| 단계 | 이슈 | 범위 |
| --- | --- | --- |
| 0 | 계획 승인, 운영진 확인, 판정 기준표(조건별 수치) 확정 | — |
| 1 | `[accounts]` 커스텀 User + DB 초기화 1회 | 기반 |
| 1 | `[places]` Region·Building·Place·Entrance·FieldDefinition·AccessibilityValue + 관리자 화면 + 월계1동 Region·필드 정의 초기 데이터 | M-8, M-11, F2 |
| 1 | `[judgments]` 규칙 모델 + 판정 엔진 + 경계값 테스트 + 표시 문구 상수 + 재판정 커맨드 | F3, M-7, M-9 |
| 2 | `[places]` 읽기 API `/api/v1/places/` (region·profile 필터, 판정 포함) | F1, S-10 일부 |
| 2 | `[places]` 지도 화면: 카카오 어댑터, 이동 조건 선택, 기본 숨김·"모든 장소 보기", 거리순 목록 | F1, M-7 |
| 2 | `[places]` 장소 상세: 건물/가게 섹션, 방법 먼저(OP-2), 사장님 코멘트 영역(OP-3), 법 안내(OP-8) | F4, M-8 |
| 3 | `[reports]` 제보: 사진 + 체크 + 현재 위치 / 확인 / 하향 제보 검증 대기 / 24시간 1회·7일 규칙 | F5, M-10 |
| 3 | `[places]` 답사 시드 데이터 입력 (관리자 화면 또는 CSV 가져오기) | F6 |
| 4 | `[owners]` 인증 코드·도움 제공 선언·코멘트 → 정정 요청 → 가고 싶어요·대시보드 → 지원사업 안내 | S-6~S-9 |
| 4 | `[places]` GeoJSON 내보내기 | S-10 |
| 5 | Could: 건물 개선 시뮬레이션, 구청 대시보드, 자동 블러, 개선 완료 알림 | — |

승인되면 위 이슈를 GitHub 이슈(`feature.md` 템플릿)로 등록하고 담당자를 지정한다.

---

## 5. 결정 필요 (PM)

1. **운영진 확인**: 해커톤 규정상 기능 코드 착수 가능한 시점인지 (CLAUDE.md 결정 사항)
2. **팀 ERD 공유**: v2 11장이 말하는 "기존 가게 테이블"·"ERD 지적 사항"의 원본 — 이 계획과 비교 필요
3. **판정 기준표**: 조건(휠체어·유아차·보행 보조기·목발)별 필드 수치와 근거(`LAW`/`APPLIED`/`TEAM`) — 박현웅 명세
4. **D1~D10 승인** (특히 D3 복합 조건, D10 DB 초기화)
5. **로그인 방식**: 아이디·비밀번호만 / 카카오 로그인 추가 — 제보에 로그인이 필수(7장)라, 주민투표 기간 가입 장벽을 낮추려면 카카오 로그인이 유리하지만 작업량이 늘어남
