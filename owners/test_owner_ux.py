"""사장님 편의(내 가게 메뉴·안내 쪽지)·사진 교체 요청·건물주 화면 테스트 (기획 v2 4.1·4.4·5장)"""

from decimal import Decimal

from django.urls import reverse
from django.utils.http import urlencode

from judgments.engine import recompute_place
from judgments.services import required_confirmations
from places.models import Building, Entrance
from places.tests import make_place
from reports.models import AccessibilityValue, Report
from reports.selectors import latest_photo
from reports.test_views import photo

from .models import ClaimCode, OwnerClaim
from .services import claim_with_code, simulate, SCENARIOS
from .tests import OwnerTestBase


def survey(target_kw, values, source="TEAM_SURVEY"):
    report = Report.objects.create(source=source, status="VERIFIED", **target_kw)
    for key, raw in values.items():
        v = AccessibilityValue(report=report, field_id=key)
        v.set_value(raw)
        v.save()
    return report


class OwnerMenuTests(OwnerTestBase):
    def test_menu_goes_straight_to_single_approved_place(self):
        self.approved_owner()
        res = self.client.get(reverse("places:map"))
        self.assertContains(res, f'href="{reverse("owners:dashboard", args=[self.place.pk])}">내 가게')

    def test_pending_claim_shows_waiting_and_others_see_nothing(self):
        claim_with_code(self.owner, ClaimCode.issue(place=self.place).code)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("places:map")), "(확인 중)")
        self.client.force_login(self.neighbor)
        self.assertNotContains(self.client.get(reverse("places:map")), "내 가게")

    def test_claim_page_explains_before_login_and_prefills_code(self):
        url = reverse("owners:claim") + "?code=123456"
        res = self.client.get(url)
        self.assertContains(res, "카카오로 로그인하고 인증하기")
        self.assertContains(res, "123456")
        self.assertRedirects(self.client.post(url, {"code": "123456"}),
                             f"{reverse('account_login')}?{urlencode({'next': url})}", fetch_redirect_response=False)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(url), 'value="123456"')

    def test_print_slip_has_code_url_for_staff_only(self):
        code = ClaimCode.issue(place=self.place)
        url = reverse("ops:claim-code-print", args=[code.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.staff)
        res = self.client.get(url)
        self.assertContains(res, f"/owner/claim/?code={code.code}")
        self.assertContains(res, "계단 약국 사장님께", count=2)

    def test_dashboard_shows_current_judgments(self):
        self.approved_owner()
        res = self.client.get(reverse("owners:dashboard", args=[self.place.pk]))
        self.assertContains(res, "지금 지도에 이렇게 보여요")
        self.assertContains(res, "혼자 들어가기 어려워요")


class PhotoRequestTests(OwnerTestBase):
    def test_photo_request_is_operator_only_and_replaces_photo(self):
        self.approved_owner()
        url = reverse("owners:photo", args=[self.place.pk])
        self.client.post(url, {"reason": "사람 얼굴이 나와요", "photo": photo()})
        report = Report.objects.get(source="OWNER")
        self.assertEqual((report.entrance, report.values.count()), (self.door, 0))
        self.assertIsNone(required_confirmations(report))
        self.assertIn("사진 교체 요청: 사람 얼굴이 나와요", report.note)
        # 진행 중이면 다시 요청 불가
        self.assertContains(self.client.post(url, {"reason": "기타", "photo": photo()}), "아직 확인 중")

        # 주민 확인 목록에 나오지 않고, 직접 확인해도 반영되지 않음
        self.client.force_login(self.neighbor)
        detail = reverse("places:detail", args=[self.place.pk])
        self.assertNotContains(self.client.get(detail), reverse("reports:confirm", args=[report.pk]))
        self.client.post(reverse("reports:confirm", args=[report.pk]), {"next": detail})
        report.refresh_from_db()
        self.assertEqual(report.status, "PENDING")

        # 운영자: 목록에 종류 표시 → 승인하면 입구 사진이 바뀜
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("ops:reports")), "사장님 사진 교체 요청")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("ops:report-review", args=[report.pk]), {"action": "approve", "review_note": ""})
        report.refresh_from_db()
        self.assertEqual(report.status, "VERIFIED")
        self.assertEqual(latest_photo(self.door), report.photo)


class BuildingOwnerTests(OwnerTestBase):
    def setUp(self):
        super().setUp()
        self.building = Building.objects.create(region=self.region, name="월계빌딩", address="월계로 2",
                                                lat=Decimal("37.62"), lng=Decimal("127.05"))
        self.common = Entrance.objects.create(building=self.building, name="공용 입구")
        survey({"entrance": self.common}, {"step_height_cm": 15, "step_count": 1, "door_width_cm": 90, "has_ramp": False})
        self.clinic = make_place(self.region, "2층 치과", building=self.building, floor=2)
        door = Entrance.objects.create(place=self.clinic, name="정문")
        survey({"entrance": door}, {"step_height_cm": 0, "step_count": 0, "door_width_cm": 90, "has_ramp": False})
        recompute_place(self.clinic)

    def approved_building_owner(self):
        claim = claim_with_code(self.owner, ClaimCode.issue(building=self.building).code)
        self.assertEqual(claim.role, OwnerClaim.Role.BUILDING_OWNER)
        claim.review(OwnerClaim.Status.APPROVED, self.staff)
        self.client.force_login(self.owner)

    def test_staff_issues_building_code_from_place_page(self):
        self.client.force_login(self.staff)
        edit = reverse("ops:place-edit", args=[self.clinic.pk])
        self.assertContains(self.client.get(edit), "건물주 인증 코드 · 월계빌딩")
        res = self.client.post(reverse("ops:building-claim-code", args=[self.building.pk]), {"place": self.clinic.pk})
        self.assertRedirects(res, edit)
        self.assertTrue(ClaimCode.objects.filter(building=self.building).exists())

    def scenario(self, key):
        rows = simulate(self.building, next(s for s in SCENARIOS if s["key"] == key))
        return {r["profile"].key: r for r in rows}

    def test_simulation_counts_places_that_improve(self):
        survey({"building": self.building}, {"elevator": True})
        rows = self.scenario("ramp")
        self.assertEqual((rows["WHEELCHAIR"]["before"], rows["WHEELCHAIR"]["after"]), (0, 1))
        self.assertEqual(rows["WHEELCHAIR"]["improved"], ["2층 치과"])

    def test_elevator_scenarios(self):
        survey({"building": self.building}, {"elevator": False})
        wheelchair = lambda key: (self.scenario(key)["WHEELCHAIR"]["before"], self.scenario(key)["WHEELCHAIR"]["after"])
        self.assertEqual(wheelchair("ramp"), (0, 0))       # 경사로만으로는 2층에 못 감
        self.assertEqual(wheelchair("elevator"), (0, 0))   # 엘리베이터만으로는 입구 턱 15cm
        self.assertEqual(wheelchair("both"), (0, 1))

    def test_building_dashboard_menu_and_access(self):
        self.client.force_login(self.neighbor)
        self.assertRedirects(self.client.get(reverse("owners:building", args=[self.building.pk])), reverse("owners:home"))
        self.approved_building_owner()
        dashboard = reverse("owners:building", args=[self.building.pk])
        self.assertContains(self.client.get(reverse("places:map")), f'href="{dashboard}">내 건물')
        res = self.client.get(dashboard)
        self.assertContains(res, "건물 공용 입구에 고정 경사로를 설치하면")
        self.assertContains(res, "나아지는 가게: 2층 치과")
        self.assertContains(res, "엘리베이터를 설치하면")

    def test_building_correction_goes_to_common_entrance(self):
        self.approved_building_owner()
        self.client.post(reverse("owners:building-correction", args=[self.building.pk]),
                         {"field": "has_ramp", "value": "있음", "photo": photo()})
        report = Report.objects.get(source="OWNER")
        self.assertEqual((report.entrance, required_confirmations(report)), (self.common, 2))
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("ops:reports")), "건물주 정정 요청")

    def test_public_improve_page_and_owner_link(self):
        res = self.client.get(reverse("owners:building-improve", args=[self.building.pk]))
        self.assertContains(res, "월계빌딩 입구가 좋아지면")
        claim = claim_with_code(self.owner, ClaimCode.issue(place=self.clinic).code)
        claim.review(OwnerClaim.Status.APPROVED, self.staff)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("owners:dashboard", args=[self.clinic.pk])),
                            reverse("owners:building-improve", args=[self.building.pk]))
