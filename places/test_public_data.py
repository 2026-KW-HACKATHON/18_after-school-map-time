"""공공데이터(장애인편의시설 현황) 가져오기 — 공공데이터포털은 가짜 응답으로 대신함"""

import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.urls import reverse
from django.test import TestCase, override_settings

from judgments.models import Judgment
from reports.models import Report
from reports.selectors import current_values

from .models import Place, Region
from .public_data import display_name, import_facilities, load_or_fetch, select_facilities

LIST_XML = """<?xml version="1.0" encoding="UTF-8"?><facInfoList><totalCount>4</totalCount>
<servList><estbDate>20200101</estbDate><faclLat>37.6262</faclLat><faclLng>127.0587</faclLng><faclNm>월계 우체국</faclNm>
<faclTyCd>우체국</faclTyCd><lcMnad>서울특별시 노원구 월계로 317</lcMnad><salStaDivCd>Y</salStaDivCd><wfcltId>1135010200-1-00000001</wfcltId></servList>
<servList><estbDate>20200101</estbDate><faclLat>37.62</faclLat><faclLng>127.05</faclLng><faclNm>다세대주택</faclNm>
<faclTyCd>다세대주택</faclTyCd><lcMnad>서울특별시 노원구 광운로 1</lcMnad><salStaDivCd>Y</salStaDivCd><wfcltId>1135010200-3-00000002</wfcltId></servList>
<servList><estbDate>20200101</estbDate><faclLat>37.65</faclLat><faclLng>127.07</faclLng><faclNm>공릉 은행</faclNm>
<faclTyCd>금융업소 등 일반업무시설</faclTyCd><lcMnad>서울특별시 노원구 공릉로 1</lcMnad><salStaDivCd>Y</salStaDivCd><wfcltId>1135010300-3-00000003</wfcltId></servList>
<servList><estbDate>20200101</estbDate><faclLat>37.6265</faclLat><faclLng>127.0590</faclLng><faclNm>일반음식점</faclNm>
<faclTyCd>일반음식점</faclTyCd><lcMnad>서울특별시 노원구 석계로1길 18</lcMnad><salStaDivCd>Y</salStaDivCd><wfcltId>1135010200-3-00000004</wfcltId></servList>
<resultCode>0</resultCode></facInfoList>"""

ITEMS_XML = """<?xml version="1.0" encoding="UTF-8"?><facInfoList><servList>
<evalInfo>승강기, 장애인사용가능화장실, 주출입구 높이차이 제거, 승강기, 장애인전용주차구역</evalInfo></servList>
<resultCode>0</resultCode></facInfoList>"""


def fake_get(url, params=None, timeout=None):
    res = mock.Mock(status_code=200)
    res.content = (LIST_XML if url.endswith("getDisConvFaclList") else ITEMS_XML).encode("utf-8")
    return res


@override_settings(PUBLIC_DATA_API_KEY="test-key")
class PublicDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.region = Region.objects.get(code="wolgye1")
        self.cache = Path(tempfile.mkdtemp()) / "cache.json"

    def fetch(self):
        with mock.patch("places.public_data.requests.get", side_effect=fake_get) as get:
            data, calls = load_or_fetch(str(self.cache), "서울특별시", "노원구", "1135010200", 90, set())
        return data, calls, get

    def test_fetch_keeps_only_dong_and_non_residential_and_caches(self):
        data, calls, get = self.fetch()
        self.assertEqual([d["row"]["wfcltId"][-1] for d in data], ["1", "4"])   # 주거시설·다른 동 제외
        self.assertEqual(calls, 3)                                               # 목록 1 + 시설 2
        again, calls, get = self.fetch()                                         # 캐시 파일 → 호출 0
        self.assertEqual((calls, get.call_count), (0, 0))
        self.assertEqual(again, json.loads(self.cache.read_text(encoding="utf-8")))

    def test_import_maps_only_direct_items(self):
        data, _, _ = self.fetch()
        rows = import_facilities(data, self.region)
        self.assertEqual([r.status for r in rows], ["새 장소", "새 장소"])
        office = Place.objects.get(name="월계 우체국")
        self.assertEqual(office.category, Place.Category.PUBLIC)
        door = office.entrances.get()
        self.assertEqual(current_values(door)["step_height_cm"].value, Decimal("0"))
        self.assertNotIn("door_width_cm", current_values(door))                 # 수치가 없는 항목은 비워 둠
        self.assertIs(current_values(office)["accessible_toilet"].value, True)
        self.assertIs(current_values(office.building)["elevator"].value, True)
        report = Report.objects.filter(source="PUBLIC_DATA").first()
        self.assertEqual(report.get_source_display(), "공공데이터")
        self.assertEqual(report.observed_at.date().isoformat(), "2020-01-01")
        # 문 폭이 없으니 휠체어는 '정보 없음', 유아차는 단차 0cm로 '들어갈 수 있어요'
        results = dict(Judgment.objects.filter(place=office).values_list("profile_id", "result"))
        self.assertEqual((results["WHEELCHAIR"], results["STROLLER"]), ("UNKNOWN", "ACCESSIBLE"))
        # 이용 조건: 상세 화면에 공공데이터 출처(제공 기관·데이터 이름)를 표시
        page = self.client.get(reverse("places:detail", args=[office.pk]))
        self.assertContains(page, "한국사회보장정보원_장애인편의시설 현황")

    def test_generic_names_get_address_and_reimport_is_noop(self):
        data, _, _ = self.fetch()
        import_facilities(data, self.region)
        self.assertTrue(Place.objects.filter(name="일반음식점 (석계로1길 18)").exists())
        self.assertEqual([r.status for r in import_facilities(data, self.region)], ["변경 없음", "변경 없음"])
        self.assertEqual(display_name({"faclNm": "", "faclTyCd": "", "lcMnad": ""}), "이름 없는 시설")

    def test_dry_run_and_radius(self):
        data, _, _ = self.fetch()
        import_facilities(data, self.region, dry_run=True)
        self.assertFalse(Place.objects.exists())
        rows = import_facilities(data, self.region, radius_m=10)
        self.assertEqual([r.status for r in rows], ["새 장소", "건너뜀"])          # 우체국은 중심, 음식점은 약 40m

    def test_select_skips_closed(self):
        rows = [{"wfcltId": "1135010200-1-1", "faclTyCd": "우체국", "salStaDivCd": "N"}]
        self.assertEqual(select_facilities(rows, "1135010200"), [])

    def test_committed_snapshot_has_no_key(self):
        snapshot = Path(__file__).resolve().parent / "data" / "public" / "wolgye-facilities-20261001.json"
        text = snapshot.read_text(encoding="utf-8")
        self.assertNotIn("serviceKey", text)
        self.assertGreater(len(json.loads(text)), 0)
