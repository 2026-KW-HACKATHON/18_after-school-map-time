# 서비스 지역 경계

지도 메타 API `GET /api/v1/meta/`의 `region.boundary`로 기존 `Region.boundary`를 공개한다.
DB에 지정된 경계가 우선이며, 비어 있는 `wolgye1`에만 배포 파일 `places/data/wolgye1.geojson`을 사용한다.
다른 지역에는 월계1동 경계를 재사용하지 않는다. DB·Migration·기존 장소 범위를 변경하지 않는다.

지도의 ‘장소 표시 설정’에서 **동별 구역 표시**로 경계를 켜고 끌 수 있다. 경계는 안내용 점선으로 표시하며
장소 노출·검색·제보를 제한하는 판정에는 사용하지 않는다. Polygon·MultiPolygon 및 내부 고리를 지원한다.
SDK/경계 오류는 기존 지도·목록 대체 흐름으로 처리한다.

## 출처와 이용 조건

- 원자료: 통계청 통계지리정보서비스 [SGIS](https://sgis.kostat.go.kr), 공공누리 제1유형(출처표시).
- 가공 자료: [vuski/admdongkor](https://github.com/vuski/admdongkor), CC BY 4.0.
- 기준일: 2026-07-01. 행정동 코드 11110510 / 행정기관 코드 1135056000, 서울특별시 노원구 월계1동.
- 원본 commit: `7360288277dfd12d74e54b959c59bdd66f852e3a`.
- [원본 GeoJSON](https://raw.githubusercontent.com/vuski/admdongkor/7360288277dfd12d74e54b959c59bdd66f852e3a/ver20260701/HangJeongDong_ver20260701.geojson)
- [데이터 라이선스](https://github.com/vuski/admdongkor/blob/master/LICENSE-DATA) / [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

전체 파일에서 월계1·2·3동 Feature를 추출하고 출처·기준일·라이선스 속성을 추가했다.
월계2동 코드는 11110520 / 1135057000, 월계3동은 11110530 / 1135058000이다.
개별 동 좌표는 변형하지 않았다. 화면에도 출처를 표시한다. 측량·법적 경계 확정용으로 사용하지 않는다.
경계 업데이트는 출처/기준일/코드를 확인한 후 파일을 교체하고 테스트하며 운영 DB를 직접 변경하지 않는다.

## 확대 단계별 표시

기존 `region.boundary` 응답 및 월계1동 파일은 그대로 유지한다. `region.boundary_layers`를 추가하여
월계1동 서비스 지도에 월계1·2·3동 안내 레이어를 표시한다. DB 경계가 지정된 지역과 다른 지역에는 추가 레이어를 적용하지 않는다.
서비스 장소 범위·Region 레코드·검색·접근성 판정은 확장하지 않는다.

- 카카오 지도 level 1~5 (확대): 월계1동 보라 `#7b4fc9` (빨간색 금지 원칙), 월계2동 파랑 `#245ccc`, 월계3동 초록 `#16804a`.
- level 6~14 (축소): `wolgye.geojson`의 합쳐진 외곽만 기존 primary 색상으로 표시한다. 내부 동 경계는 숨긴다.
- 점선 굵기는 2px → 2.6px (1.3배), 채움은 없음. 색상은 장소 판정과 독립적이며 텍스트 범례를 함께 표시한다.
- 확대/축소 전환 시 중심·장소 마커·개인화 조건을 변경하지 않는다. 토글을 끄면 확대해도 다시 나타나지 않는다.

`wolgye-districts.geojson`은 세 동의 원본 좌표, `wolgye.geojson`은 그 기하학적 합집합(내부 공유 경계 제거)이다.
여기서 ‘전체’는 월계1·2·3동 합친 **행정동 안내 구역**이며 법정동 월계동 경계라고 단정하지 않는다.
좌표 단순화·버퍼를 적용하지 않았다. Shapely 2.1.2는 파일 생성/검증에만 사용하며 서비스 의존성에는 추가하지 않는다.

재생성: 동일 원본 commit의 GeoJSON을 받아 임시 도구 환경에 `shapely==2.1.2`를 설치한 후
`python scripts/extract_wolgye_boundaries.py <원본파일> places/data`를 실행한다. 기존 월계1동과 원본 좌표 일치,
세 동 이름/코드/유효성 및 연속된 외곽을 검증하며, 생성 파일을 테스트한 뒤 PR로 반영한다.

## 검증 (2026-10-09)

- Django 482개 / JavaScript 131개 통과, `check` 및 `makemigrations --check --dry-run` 통과.
- 생성한 전체 외곽과 세 동 합집합의 대칭차 면적 0, 유효한 Polygon 및 외부 고리 1개 확인.
- 실제 템플릿·메타 API·지도 어댑터와 SVG SDK 대역을 이용해 PC 1280×800 / 모바일 375×812,
  320×640 큰 글씨에서 토글·색상·굵기·5↔6 단계 전환·키보드·가로 넘침 없음 확인.
- 실제 카카오 타일/SDK 및 운영 기기에서의 시각 확인은 별도 필요. 테스트용 서버는 임시 DB만 사용.
- [PC 동별 표시](screenshots/district-boundary-pc.png), [축소 외곽](screenshots/district-boundary-overview.png),
  [모바일](screenshots/district-boundary-mobile.png). 화면의 SVG 지도는 검증 대역이며 운영 지도 타일이 아니다.
