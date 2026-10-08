"""주소·이름 → 좌표 (카카오 로컬 API는 가짜 응답으로 대신함 — CI에 키가 없어도 돌게)"""

from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase, override_settings

from .geocoding import ADDRESS_URL, KEYWORD_URL, NEAR_RADIUS_M, geocode

NEAR = (Decimal("37.626200"), Decimal("127.058700"))


def fake_kakao(address_docs=(), keyword_docs=(), status=200):
    """URL에 따라 주소 검색·키워드 검색 응답을 돌려주는 가짜 requests.get"""
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        res = mock.Mock(status_code=status)
        res.json.return_value = {"documents": list(address_docs if url == ADDRESS_URL else keyword_docs)}
        return res

    return get, calls


@override_settings(KAKAO_REST_API_KEY="test-key")
class GeocodeTests(SimpleTestCase):
    def test_address_first(self):
        get, calls = fake_kakao(address_docs=[{"x": "127.059664", "y": "37.629247", "address_name": "서울 노원구 월계로 372"}])
        with mock.patch("places.geocoding.requests.get", get):
            r = geocode("월계로 372", near=NEAR)
        self.assertEqual((r.lat, r.lng, r.method), (Decimal("37.629247"), Decimal("127.059664"), "주소"))
        lat, lng = r                                    # 예전처럼 풀어 쓰기
        self.assertEqual(len(calls), 1)                 # 주소로 찾으면 키워드 검색은 안 함
        self.assertEqual(calls[0][2]["Authorization"], "KakaoAK test-key")

    def test_name_falls_back_to_keyword_near_region(self):
        get, calls = fake_kakao(keyword_docs=[{"x": "127.058271", "y": "37.619240", "place_name": "광운대학교",
                                               "road_address_name": "서울 노원구 광운로 20"}])
        with mock.patch("places.geocoding.requests.get", get):
            r = geocode("광운대학교", near=NEAR)
        self.assertEqual((r.method, r.label), ("이름", "광운대학교 · 서울 노원구 광운로 20"))
        url, params, _ = calls[1]
        self.assertEqual((url, params["radius"], params["y"]), (KEYWORD_URL, NEAR_RADIUS_M, "37.626200"))

    def test_no_keyword_search_without_region(self):
        get, calls = fake_kakao()
        with mock.patch("places.geocoding.requests.get", get), self.assertRaisesMessage(ValueError, "찾지 못했어요"):
            geocode("광운대학교")
        self.assertEqual(len(calls), 1)

    def test_errors_are_readable(self):
        get, _ = fake_kakao(status=401)
        with mock.patch("places.geocoding.requests.get", get), self.assertRaisesMessage(ValueError, "HTTP 401"):
            geocode("월계로 372", near=NEAR)
        with override_settings(KAKAO_REST_API_KEY=""), self.assertRaisesMessage(ValueError, "KAKAO_REST_API_KEY"):
            geocode("월계로 372")
        with self.assertRaisesMessage(ValueError, "비어 있어요"):
            geocode("  ")
