# 검색어 없는 장소 탐색

`/search/`는 검색어가 없거나 공백이면 현재 활성 서비스 지역의 폐업하지 않은 장소를 표시한다.
기존 이름/주소 검색, 업종 필터와 이름·ID 순 정렬은 유지한다. 검색어 유무와 관계없이
30곳씩 나눠 이전/다음 페이지로 전체 목록을 탐색한다. 접근성 낮은 순 정렬은 제공하지 않는다.

HTML 검색의 `q`, `category`, `profile`, `page`를 페이지 이동에도 보존한다.
잘못된 HTML page는 첫 페이지, 범위를 넘는 정상 숫자는 마지막 페이지를 사용한다.
개인화 설정은 기존 브라우저/계정 저장을 유지하고 수치 설정을 URL에 넣지 않는다.

개인화 읽기 계산 API `POST /api/v1/mobility/places/`의 검색 요청(`q` 제공)에만
선택 `page`(ASCII 양의 정수, 기본 1)를 추가했다. `q: ""`도 전체 탐색을 수행한다.
기존 `count`는 현재 응답 행 수이고, 추가 필드 `total_count`, `page`, `num_pages`,
`has_previous`, `has_next`로 페이지 정보를 제공한다. 기본 요청은 여전히 최대 30행이다.
잘못된 API page는 JSON 400, 지도/ID 조회 요청에 page를 주면 400이다.
지도·장소 상세의 응답 구조와 판정 정책, DB/Model/Migration은 변경하지 않는다.

관련 회귀: `places.test_search_browse`, `places.test_views`, `accounts.test_mobility`,
`tests/js/mobility-settings.test.cjs`. 실제 로컬/운영 DB 대신 임시 테스트 DB에서 검증한다.
