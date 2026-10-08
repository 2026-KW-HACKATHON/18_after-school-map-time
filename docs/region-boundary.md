# 서비스 지역 경계

지도 메타 API `GET /api/v1/meta/`의 `region.boundary`로 기존 `Region.boundary`를 공개한다.
DB에 지정된 경계가 우선이며, 비어 있는 `wolgye1`에만 배포 파일 `places/data/wolgye1.geojson`을 사용한다.
다른 지역에는 월계1동 경계를 재사용하지 않는다. DB·Migration·기존 장소 범위를 변경하지 않는다.

지도의 ‘장소 표시 설정’에서 경계를 켜고 끌 수 있다. 경계는 안내용 점선으로 표시하며
장소 노출·검색·제보를 제한하는 판정에는 사용하지 않는다. Polygon·MultiPolygon 및 내부 고리를 지원한다.
SDK/경계 오류는 기존 지도·목록 대체 흐름으로 처리한다.

## 출처와 이용 조건

- 원자료: 통계청 통계지리정보서비스 [SGIS](https://sgis.kostat.go.kr), 공공누리 제1유형(출처표시).
- 가공 자료: [vuski/admdongkor](https://github.com/vuski/admdongkor), CC BY 4.0.
- 기준일: 2026-07-01. 행정동 코드 11110510 / 행정기관 코드 1135056000, 서울특별시 노원구 월계1동.
- 원본 commit: `7360288277dfd12d74e54b959c59bdd66f852e3a`.
- [원본 GeoJSON](https://raw.githubusercontent.com/vuski/admdongkor/7360288277dfd12d74e54b959c59bdd66f852e3a/ver20260701/HangJeongDong_ver20260701.geojson)
- [데이터 라이선스](https://github.com/vuski/admdongkor/blob/master/LICENSE-DATA) / [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

전체 파일에서 월계1동 Feature 하나만 추출하고 출처·기준일·라이선스 속성을 추가했다.
좌표는 변형하지 않았다. 화면에도 출처를 표시한다. 측량·법적 경계 확정용으로 사용하지 않는다.
경계 업데이트는 출처/기준일/코드를 확인한 후 파일을 교체하고 테스트하며 운영 DB를 직접 변경하지 않는다.
