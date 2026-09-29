"""지도·상세 화면과 공개 읽기 API 테스트 (표시 정책 v2 포함)"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from judgments.engine import recompute_place
from reports.models import AccessibilityValue, Report

from .models import Building, Entrance
from .tests import make_place


class ViewTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        from .models import Region

        self.region = Region.objects.get(code="wolgye1")
        self.easy = self.make("턱없는 카페", step_height_cm=0)      # 휠체어 가능
        self.hard = self.make("계단 식당", step_height_cm=30, step_count=2)  # 휠체어 어려움
        self.unknown = make_place(self.region, "정보 없는 약국")      # 출입구 정보 없음 → 미확인
        recompute_place(self.unknown)

    def make(self, name, **entrance_values):
        place = make_place(self.region, name)
        door = Entrance.objects.create(place=place)
        self.add_values(door, door_width_cm=90, has_ramp=False, **entrance_values)
        recompute_place(place)
        return place

    def add_values(self, target, status=Report.Status.VERIFIED, **values):
        key = {"Entrance": "entrance", "Place": "place", "Building": "building"}[type(target).__name__]
        report = Report.objects.create(source=Report.Source.TEAM_SURVEY, status=status, **{key: target})
        for field_key, raw in values.items():
            v = AccessibilityValue(report=report, field_id=field_key)
            v.set_value(raw)
            v.save()
        return report


class PlaceListApiTests(ViewTestBase):
    url = reverse("api:place-list")

    def names(self, **params):
        res = self.client.get(self.url, {"region": "wolgye1", **params})
        self.assertEqual(res.status_code, 200)
        return {r["name"]: r["judgment"] for r in res.json()["results"]}

    def test_default_hides_difficult_and_unknown(self):
        rows = self.names(profile="WHEELCHAIR")
        self.assertEqual(set(rows), {"턱없는 카페"})
        self.assertEqual(rows["턱없는 카페"]["label"], "들어갈 수 있어요")

    def test_show_all_includes_everything_with_v2_labels(self):
        rows = self.names(profile="WHEELCHAIR", all="1")
        self.assertEqual(rows["계단 식당"]["label"], "혼자 들어가기 어려워요")
        self.assertEqual(rows["계단 식당"]["reason"], "입구 단차 30cm · 계단 수 2칸")  # 어려움 옆 사실 한 줄
        self.assertEqual(rows["정보 없는 약국"]["code"], "UNKNOWN")
        self.assertEqual(rows["정보 없는 약국"]["shape"], "dashed-circle")

    def test_without_profile_lists_all_places(self):
        rows = self.names()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(j is None for j in rows.values()))

    def test_region_scope_and_closed_places(self):
        from .models import Region

        other = Region.objects.create(code="other", name="다른 동", center_lat=Decimal("37.6"), center_lng=Decimal("127.0"))
        make_place(other, "다른 동 가게")
        self.hard.is_closed = True
        self.hard.save()
        rows = self.names(all="1", profile="WHEELCHAIR")
        self.assertNotIn("다른 동 가게", rows)
        self.assertNotIn("계단 식당", rows)  # 폐업

    def test_bad_params(self):
        self.assertEqual(self.client.get(self.url, {"profile": "ROCKET"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"region": "nowhere"}).status_code, 404)

    def test_no_ranking_or_sort_by_accessibility(self):
        # 기획 v2 3.2: 접근성 낮은 순 정렬 없음 → sort 파라미터를 무시하고 이름순
        res = self.client.get(self.url, {"region": "wolgye1", "all": "1", "sort": "worst"})
        names = [r["name"] for r in res.json()["results"]]
        self.assertEqual(names, sorted(names))


class MetaAndGeoJsonTests(ViewTestBase):
    def test_meta(self):
        data = self.client.get(reverse("api:meta")).json()
        self.assertEqual(data["region"]["code"], "wolgye1")
        self.assertEqual([p["key"] for p in data["profiles"]], ["WHEELCHAIR", "STROLLER", "WALKER", "CRUTCH"])
        self.assertTrue(data["display"]["DIFFICULT"]["hidden_by_default"])
        self.assertNotIn("red", str(data["display"]).lower())

    def test_geojson(self):
        data = self.client.get(reverse("api:places-geojson"), {"region": "wolgye1"}).json()
        self.assertEqual(data["type"], "FeatureCollection")
        feature = next(f for f in data["features"] if f["properties"]["name"] == "턱없는 카페")
        lng, lat = feature["geometry"]["coordinates"]  # GeoJSON은 [경도, 위도]
        self.assertEqual((lat, lng), (float(self.easy.lat), float(self.easy.lng)))
        self.assertEqual(feature["properties"]["judgments"]["WHEELCHAIR"]["code"], "ACCESSIBLE")


class DetailTests(ViewTestBase):
    def setUp(self):
        super().setUp()
        self.building = Building.objects.create(region=self.region, name="월계빌딩", address="월계동 1",
                                                lat=Decimal("37.62"), lng=Decimal("127.05"))
        self.easy.building = self.building
        self.easy.save()
        self.add_values(self.building, elevator=True)
        self.add_values(self.easy.entrances.first(), status=Report.Status.PENDING, step_height_cm=5)

    def test_detail_api_sections(self):
        data = self.client.get(reverse("api:place-detail", args=[self.easy.pk])).json()
        self.assertEqual(data["building"]["building"]["name"], "월계빌딩")
        self.assertEqual(
            {f["key"]: f["value"] for f in data["building"]["fields"]}["elevator"], "있음"
        )
        step = next(f for f in data["place"]["entrances"][0]["fields"] if f["key"] == "step_height_cm")
        self.assertEqual((step["value"], step["pending"]), ("0", True))  # 기존 값 유지 + 확인 중 표시
        self.assertIsNotNone(data["last_checked"])

    def test_detail_page_policy_texts(self):
        res = self.client.get(reverse("places:detail", args=[self.easy.pk]))
        self.assertContains(res, "건물 공용 입구")        # OP-4
        self.assertContains(res, "사장님이신가요?")        # OP-3
        self.assertContains(res, "법 위반 여부를 판단한 것이 아니에요")  # OP-8
        self.assertContains(res, "새 제보 확인 중")        # OP-6
        for word in ("불량", "부적합", "점수", "순위"):   # OP-1
            self.assertNotContains(res, word)

    def test_closed_place_404(self):
        self.hard.is_closed = True
        self.hard.save()
        self.assertEqual(self.client.get(reverse("places:detail", args=[self.hard.pk])).status_code, 404)

    def test_map_page(self):
        res = self.client.get(reverse("places:map"))
        self.assertContains(res, 'data-region="wolgye1"')
        self.assertContains(res, "모든 장소 보기")
        self.assertNotContains(res, "어려운 곳만")


class EntrancePhotoTests(ViewTestBase):
    def test_latest_verified_photo_shown(self):
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        with override_settings(MEDIA_ROOT=media):
            door = self.easy.entrances.first()
            verified = self.add_values(door, step_height_cm=0)
            verified.photo = SimpleUploadedFile("door.gif", gif, content_type="image/gif")
            verified.save()
            pending = self.add_values(door, status=Report.Status.PENDING, step_height_cm=0)
            pending.photo = SimpleUploadedFile("pending.gif", gif, content_type="image/gif")
            pending.save()

            data = self.client.get(reverse("api:place-detail", args=[self.easy.pk])).json()
            url = data["place"]["entrances"][0]["photo_url"]
            self.assertIn("door", url)          # 확인 중인 사진은 보여주지 않음
            self.assertContains(self.client.get(reverse("places:detail", args=[self.easy.pk])), url)
