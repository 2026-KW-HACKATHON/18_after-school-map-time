"""운영자 화면 테스트 (와이어프레임 10~18번)"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from judgments.engine import recompute_place
from judgments.models import Judgment
from places.models import Entrance, Place, Region
from places.tests import make_place
from reports.models import AccessibilityValue, Report


class OpsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.region = Region.objects.get(code="wolgye1")
        self.staff = User.objects.create_user(username="operator", password="Ops!pass2026", is_staff=True)
        self.jumin = User.objects.create_user(username="jumin")
        self.client.force_login(self.staff)

    def cafe_with_door(self, step="0"):
        place = make_place(self.region, "턱없는 카페")
        door = Entrance.objects.create(place=place, name="정문")
        report = Report.objects.create(source="TEAM_SURVEY", status="VERIFIED", entrance=door)
        for key, raw in {"step_height_cm": step, "door_width_cm": 90, "has_ramp": False}.items():
            v = AccessibilityValue(report=report, field_id=key)
            v.set_value(raw)
            v.save()
        recompute_place(place)
        return place, door

    def user_report(self, target=None, **values):
        kwargs = {"entrance": target} if target is not None else {"suggested_name": "새 가게", "location_text": "월계역 앞",
                                                                 "lat": Decimal("37.626100"), "lng": Decimal("127.058800")}
        report = Report.objects.create(source="USER_REPORT", created_by=self.jumin, **kwargs)
        for key, raw in values.items():
            v = AccessibilityValue(report=report, field_id=key)
            v.set_value(raw)
            v.save()
        return report


class AccessTests(OpsTestBase):
    def test_non_staff_redirected_to_ops_login(self):
        self.client.force_login(self.jumin)
        res = self.client.get(reverse("ops:dashboard"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("ops:login"), res["Location"])

    def test_login_with_staff_account(self):
        self.client.logout()
        res = self.client.post(reverse("ops:login"), {"username": "operator", "password": "Ops!pass2026"})
        self.assertRedirects(res, reverse("ops:dashboard"))

    def test_nav_link_only_for_staff(self):
        self.assertContains(self.client.get(reverse("places:search")), reverse("ops:dashboard"))
        self.client.force_login(self.jumin)
        self.assertNotContains(self.client.get(reverse("places:search")), reverse("ops:dashboard"))


class DashboardAndListTests(OpsTestBase):
    def test_dashboard_counts(self):
        _, door = self.cafe_with_door()
        self.user_report(door, step_height_cm=30)
        res = self.client.get(reverse("ops:dashboard"))
        self.assertEqual(res.context["pending"], 1)
        self.assertEqual(res.context["public_places"], 1)

    def test_list_flags_downgrade_new_place_and_new_account(self):
        _, door = self.cafe_with_door()
        self.user_report(door, step_height_cm=30)       # 가능 → 어려움
        self.user_report(step_height_cm=0)              # 새 장소 제안
        res = self.client.get(reverse("ops:reports"), {"status": "PENDING"})
        self.assertContains(res, "판정 하향 제보", count=1)
        self.assertContains(res, "새 장소: 새 가게")
        self.assertContains(res, "가입 7일 미만", count=2)


class ReviewTests(OpsTestBase):
    def test_review_shows_diff_and_judgment_change(self):
        _, door = self.cafe_with_door()
        report = self.user_report(door, step_height_cm=30)
        res = self.client.get(reverse("ops:report-review", args=[report.pk]))
        self.assertContains(res, "값이 달라요")                                  # 기존 0cm vs 제보 30cm
        self.assertContains(res, "들어갈 수 있어요 → <strong>혼자 들어가기 어려워요</strong>", html=False)

    def test_approve_applies_and_recomputes(self):
        place, door = self.cafe_with_door()
        report = self.user_report(door, step_height_cm=30)
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(reverse("ops:report-review", args=[report.pk]),
                                   {"action": "approve", "review_note": "사진으로 계단 확인"})
        self.assertRedirects(res, reverse("ops:report-done", args=[report.pk]))
        report.refresh_from_db()
        self.assertEqual((report.status, report.reviewed_by, report.review_note), ("VERIFIED", self.staff, "사진으로 계단 확인"))
        self.assertEqual(Judgment.objects.get(place=place, profile="WHEELCHAIR").result, "DIFFICULT")

    def test_reject_needs_reason(self):
        _, door = self.cafe_with_door()
        report = self.user_report(door, step_height_cm=30)
        url = reverse("ops:report-review", args=[report.pk])
        self.assertContains(self.client.post(url, {"action": "reject"}), "반려 사유를 입력해 주세요")
        self.client.post(url, {"action": "reject", "reject_reason": "사진이 흐려요"})
        report.refresh_from_db()
        self.assertEqual((report.status, report.reject_reason), ("REJECTED", "사진이 흐려요"))

    def test_approve_new_place_creates_place(self):
        report = self.user_report(step_height_cm=0, door_width_cm=90, has_ramp=False)
        url = reverse("ops:report-review", args=[report.pk])
        self.assertContains(self.client.post(url, {"action": "approve", "lat": "", "lng": "", "place_name": "새 가게"}),
                            "위치를 지도에서 선택해 주세요")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"action": "approve", "place_name": "월계 새 카페", "category": "CAFE",
                                   "lat": "37.626100", "lng": "127.058800"})
        place = Place.objects.get(name="월계 새 카페")
        report.refresh_from_db()
        self.assertEqual((report.status, report.entrance.place), ("VERIFIED", place))
        self.assertEqual(place.address, "월계역 앞")
        self.assertEqual(Judgment.objects.get(place=place, profile="WHEELCHAIR").result, "ACCESSIBLE")


class PlaceFormTests(OpsTestBase):
    def test_missing_required_notice(self):
        res = self.client.post(reverse("ops:place-new"), {"category": "CAFE", "floor": 1})
        self.assertContains(res, "필수 항목이 누락되었습니다")
        self.assertContains(res, "장소명")
        self.assertContains(res, "위치 (지도에서 선택)")
        self.assertFalse(Place.objects.exists())

    def test_create_place_with_survey(self):
        res = self.client.post(reverse("ops:place-new"), {
            "name": "월계 약국", "category": "PHARMACY", "floor": 1, "lat": "37.625500", "lng": "127.057800",
            "step_height_cm": "15", "step_count": "1", "has_ramp": "false", "door_width_cm": "85",
            "portable_ramp": "true", "portable_ramp_length_cm": "120", "assistance_offered": "true",
            "source_note": "운영팀 직접 답사", "observed_on": "2026-09-20", "memo": "",
        })
        place = Place.objects.get(name="월계 약국")
        self.assertRedirects(res, reverse("ops:place-saved", args=[place.pk]))
        reports = Report.objects.filter(status="VERIFIED", source="TEAM_SURVEY")
        self.assertEqual(reports.count(), 2)                               # 입구 제보 + 장소 제보
        self.assertEqual(reports.first().observed_at.date().isoformat(), "2026-09-20")
        self.assertIn("출처: 운영팀 직접 답사", reports.first().note)
        self.assertEqual(Judgment.objects.get(place=place, profile="WHEELCHAIR").result, "CONDITIONAL")  # 이동식 경사로 1/8

    def test_edit_keeps_history(self):
        place, _ = self.cafe_with_door(step="0")
        self.client.post(reverse("ops:place-edit", args=[place.pk]), {
            "name": "턱없는 카페 (리모델링)", "category": "CAFE", "floor": 1, "lat": place.lat, "lng": place.lng,
            "step_height_cm": "30",
        })
        place.refresh_from_db()
        self.assertEqual(place.name, "턱없는 카페 (리모델링)")
        self.assertEqual(Report.objects.filter(entrance__place=place).count(), 2)   # 기존 기록 + 새 기록
        self.assertEqual(Judgment.objects.get(place=place, profile="WHEELCHAIR").result, "DIFFICULT")


class PageSmokeTests(OpsTestBase):
    def test_remaining_pages_render(self):
        place, door = self.cafe_with_door()
        report = self.user_report(door, step_height_cm=0)
        for url, text in [
            (reverse("ops:places"), "턱없는 카페"),
            (reverse("ops:places") + "?q=없는장소", "등록된 장소가 없어요"),
            (reverse("ops:place-saved", args=[place.pk]), "저장 완료"),
            (reverse("ops:report-done", args=[report.pk]), "정상적으로 처리"),
            (reverse("ops:place-edit", args=[place.pk]), "장소 수정"),
        ]:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), text)
