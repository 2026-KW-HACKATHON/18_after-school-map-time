"""서비스 안 알림 — 제보·사장님 요청 결과, 인증 결과, 가고 싶어요 가게 개선"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from judgments.engine import recompute_place
from owners.models import ClaimCode, OwnerClaim, VisitWish
from owners.services import claim_with_code
from places.models import Entrance, Region
from places.tests import make_place
from reports.models import AccessibilityValue, Report
from reports.services import reject_report, verify_report

from .models import Notification, User


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.place = make_place(Region.objects.get(code="wolgye1"), "계단 약국")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        self.jumin = User.objects.create_user(username="jumin", date_joined=timezone.now() - timedelta(days=30))
        self.staff = User.objects.create_user(username="staff", is_staff=True)

    def report(self, source="USER_REPORT", status="PENDING", by=None, **values):
        r = Report.objects.create(source=source, status=status, entrance=self.door, created_by=by or self.jumin)
        for key, raw in values.items():
            v = AccessibilityValue(report=r, field_id=key)
            v.set_value(raw)
            v.save()
        return r

    def review(self, func, report, **kw):
        with self.captureOnCommitCallbacks(execute=True):
            func(report, by=self.staff, **kw)

    def test_resident_report_verified_and_rejected(self):
        self.review(verify_report, self.report(has_ramp=True))
        self.review(reject_report, self.report(door_width_cm=90), reason="사진이 흐려요")
        verified, rejected = Notification.objects.filter(user=self.jumin).order_by("created_at")
        self.assertEqual((verified.kind, verified.url), ("REPORT", reverse("places:detail", args=[self.place.pk])))
        self.assertIn("계단 약국 제보가 지도에 반영됐어요", verified.message)
        self.assertIn("반영되지 않았어요 — 사진이 흐려요", rejected.message)

    def test_auto_verified_by_neighbors_also_notifies(self):
        with self.captureOnCommitCallbacks(execute=True):
            verify_report(self.report(has_ramp=True), by=None)
        self.assertEqual(Notification.objects.filter(user=self.jumin).count(), 1)

    def test_owner_request_and_claim_results(self):
        claim = claim_with_code(self.jumin, ClaimCode.issue(place=self.place).code)
        claim.review(OwnerClaim.Status.APPROVED, self.staff)
        n = Notification.objects.get(user=self.jumin, kind="CLAIM")
        self.assertIn("인증이 승인됐어요", n.message)
        self.assertEqual(n.url, reverse("owners:dashboard", args=[self.place.pk]))

        self.review(reject_report, self.report(source="OWNER", step_height_cm=3), reason="증빙 사진이 달라요")
        n = Notification.objects.get(user=self.jumin, kind="OWNER_REQUEST")
        self.assertIn("요청이 반려됐어요 — 증빙 사진이 달라요", n.message)

    def test_no_notification_for_staff_own_survey(self):
        self.review(verify_report, self.report(source="TEAM_SURVEY", by=self.staff, has_ramp=True))
        self.assertFalse(Notification.objects.exists())

    def test_wishers_hear_when_place_improves_once(self):
        self.report(status="VERIFIED", by=self.staff, source="TEAM_SURVEY",
                    step_height_cm=15, step_count=1, door_width_cm=90, has_ramp=False)
        recompute_place(self.place)                                      # 휠체어: 어려움
        VisitWish.objects.create(user=self.jumin, place=self.place, profile_id="WHEELCHAIR")
        self.report(status="VERIFIED", by=self.staff, source="TEAM_SURVEY", has_ramp=True)
        recompute_place(self.place)                                      # 경사로 설치 → 들어갈 수 있어요
        recompute_place(self.place)                                      # 다시 계산해도 중복 알림 없음
        n = Notification.objects.get(user=self.jumin, kind="WISH")
        self.assertIn("휠체어 기준 '들어갈 수 있어요'", n.message)

    def test_menu_count_and_page_marks_read(self):
        Notification.objects.create(user=self.jumin, kind="REPORT", message="테스트 알림")
        self.client.force_login(self.jumin)
        self.assertContains(self.client.get(reverse("places:map")), "안 읽은 알림 1개")
        res = self.client.get(reverse("accounts:notifications"))
        self.assertContains(res, "테스트 알림")
        self.assertContains(res, ">새<")
        self.assertFalse(Notification.objects.filter(read_at__isnull=True).exists())
        self.assertNotContains(self.client.get(reverse("places:map")), "안 읽은 알림")
