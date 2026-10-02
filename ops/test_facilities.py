"""장소 관리에서 접근 시설 종류·소속·확인 중 제안을 조회한다."""
from django.urls import reverse

from places.models import AccessFacility, Building, Entrance
from places.tests import make_place
from reports.models import Report

from .tests import OpsTestBase


class PlaceFacilityInventoryTests(OpsTestBase):
    def setUp(self):
        super().setUp()
        self.building = Building.objects.create(region=self.region, name="공용 건물", lat="37.62", lng="127.05")
        self.place = make_place(self.region, "시설 있는 가게", building=self.building)
        Entrance.objects.create(place=self.place, name="가게 정문")
        self.elevator = AccessFacility.objects.create(place=self.place, kind="ELEVATOR", name="가게 전용 E/V")
        self.escalator = AccessFacility.objects.create(building=self.building, kind="ESCALATOR", name="공용 E/S")
        self.report = Report.objects.create(facility=self.elevator, source="USER_REPORT", status="VERIFIED")
        self.pending = Report.objects.create(building=self.building, facility_kind="RAMP", facility_name="로비 경사로",
                                             source="USER_REPORT", status="PENDING")

    def test_edit_shows_types_ownership_pending_proposal_and_review_links(self):
        response = self.client.get(reverse("ops:place-edit", args=[self.place.pk]))
        for text in ("접근 시설 현황", "장소 전용", "건물 공용", "출입구", "가게 정문",
                     "엘리베이터 (E/V)", "에스컬레이터 (E/S)", "공용 E/S", "로비 경사로", "새 시설 확인 중"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("ops:report-review", args=[self.report.pk]))
        self.assertContains(response, reverse("ops:report-review", args=[self.pending.pk]))
        self.assertEqual(Report.objects.count(), 2)  # 조회로 기록을 생성하지 않는다.

    def test_list_shows_facility_counts_and_keeps_other_places_separate(self):
        unrelated = make_place(self.region, "다른 가게")
        AccessFacility.objects.create(place=unrelated, kind="TOILET", name="다른 가게 화장실")
        response = self.client.get(reverse("ops:places"), {"q": self.place.name})
        self.assertContains(response, "엘리베이터 (E/V) 1개")
        self.assertContains(response, "에스컬레이터 (E/S) 1개")
        self.assertNotContains(response, "장애인 화장실")
        self.assertNotContains(response, "다른 가게")

    def test_inventory_is_staff_only_and_not_shown_on_new_place_form(self):
        self.assertNotContains(self.client.get(reverse("ops:place-new")), "접근 시설 현황")
        self.client.force_login(self.jumin)
        self.assertEqual(self.client.get(reverse("ops:place-edit", args=[self.place.pk])).status_code, 302)
