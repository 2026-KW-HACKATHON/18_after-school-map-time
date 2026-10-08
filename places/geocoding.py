"""
주소·이름 → 좌표 (카카오 로컬 REST API, 서버 전용 키 KAKAO_REST_API_KEY).

1. 주소 검색: "서울 노원구 월계로 372" 같은 도로명·지번 주소
2. 주소로 못 찾으면 키워드 검색: "광운대학교", "월계 약국" 같은 이름을 지역 중심 반경 안에서만 찾는다
   (다른 동네의 같은 이름 가게가 잡히지 않게)

결과의 label 은 찾은 주소·장소 이름 — 답사 가져오기 미리 보기에서 맞게 찾았는지 사람이 확인하는 용도.
"""

from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
NEAR_RADIUS_M = 3000   # 키워드 검색 범위: 지역 중심에서 3km (월계1동과 주변을 덮는 정도)
COORD = Decimal("0.000001")


@dataclass
class GeocodeResult:
    lat: Decimal
    lng: Decimal
    label: str      # 찾은 주소 또는 장소 이름
    method: str     # "주소" / "이름"

    def __iter__(self):
        # lat, lng = geocode(...) 처럼 풀어 쓸 수 있게 (예전 코드 호환)
        return iter((self.lat, self.lng))


def _search(url, params):
    key = settings.KAKAO_REST_API_KEY
    if not key:
        raise ValueError("위도·경도가 비어 있어요. 주소로 찾으려면 .env에 KAKAO_REST_API_KEY가 필요해요")
    try:
        res = requests.get(url, params=params, headers={"Authorization": f"KakaoAK {key}"}, timeout=5)
    except requests.RequestException as e:
        raise ValueError(f"카카오 주소 검색에 연결하지 못했어요 ({e.__class__.__name__})")
    if res.status_code != 200:
        # 401/403: 키가 틀렸거나 카카오 개발자센터에서 '카카오맵' 사용 설정이 꺼져 있음
        raise ValueError(f"카카오 주소 검색 실패 (HTTP {res.status_code}). 위도·경도를 직접 적어 주세요")
    return res.json().get("documents") or []


def _coord(doc):
    return Decimal(doc["y"]).quantize(COORD), Decimal(doc["x"]).quantize(COORD)


def geocode(query, near=None):
    """
    주소나 이름 → GeocodeResult. near=(위도, 경도) 를 주면 주소로 못 찾을 때 그 근처에서 이름으로 찾는다.
    못 찾으면 ValueError (화면·명령에 그대로 보여 줄 문장)
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("위도·경도와 주소가 모두 비어 있어요")
    docs = _search(ADDRESS_URL, {"query": query})
    if docs:
        lat, lng = _coord(docs[0])
        return GeocodeResult(lat, lng, docs[0].get("address_name") or query, "주소")
    if near is not None:
        docs = _search(KEYWORD_URL, {"query": query, "y": str(near[0]), "x": str(near[1]),
                                     "radius": NEAR_RADIUS_M, "sort": "accuracy"})
        if docs:
            lat, lng = _coord(docs[0])
            doc = docs[0]
            label = " · ".join(filter(None, [doc.get("place_name"), doc.get("road_address_name") or doc.get("address_name")]))
            return GeocodeResult(lat, lng, label, "이름")
    raise ValueError(f"'{query}'를 찾지 못했어요. 위도·경도를 직접 적어 주세요")
