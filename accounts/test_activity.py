"""내 활동 — 내 제보 상태·기여 수·긍정 배지"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from places.models import Entrance, Region
from places.tests import make_place
from reports.models import AccessibilityValue, Reconfirmation, Report, ReportConfirmation

from .activity import BADGES
from .models import User


class ActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.place = make_place(Region.objects.get(code="wolgye1"), "턱없는 카페")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        self.user = User.objects.create_user(username="jumin", nickname="동네주민",
                                             date_joined=timezone.now() - timedelta(days=30))
        self.url = reverse("accounts:me")

    def report(self, status, reason="", **values):
        r = Report.objects.create(source="USER_REPORT", status=status, entrance=self.door, created_by=self.user,
                                  reject_reason=reason)
        for key, raw in values.items():
            v = AccessibilityValue(report=r, field_id=key)
            v.set_value(raw)
            v.save()
        return r

    def test_login_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_shows_status_progress_and_reject_reason(self):
        self.report("VERIFIED", has_ramp=True)
        self.report("PENDING", door_width_cm=90)
        self.report("REJECTED", reason="사진이 흐려요", step_height_cm=5)
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertContains(res, "동네주민님의 활동")
        self.assertContains(res, "지도에 반영된 제보 <strong>1건</strong>")
        self.assertContains(res, "지도에 반영됐어요")
        self.assertContains(res, "주민 확인 0/1명")
        self.assertContains(res, "사진이 흐려요")

    def test_badges_are_positive_only_and_follow_the_list(self):
        self.report("VERIFIED", has_ramp=True)
        other = Report.objects.create(source="USER_REPORT", status="PENDING", entrance=self.door)
        ReportConfirmation.objects.create(report=other, user=self.user)
        Reconfirmation.objects.create(place=self.place, user=self.user)
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        earned = {b["key"] for b in res.context["badges"] if b["earned"]}
        self.assertEqual(earned, {"first_report"})
        self.assertContains(res, "확인 도우미 1/3")
        self.assertEqual(len(res.context["badges"]), len(BADGES))
        for word in ("순위", "등수", "불량"):
            self.assertNotContains(res, word)

    def test_menu_links(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("places:map"))
        self.assertContains(res, f'href="{self.url}"', count=2)                  # 상단 이름 + 하단 탭
        self.assertContains(self.client.get(reverse("reports:done")), "내 제보 현황 보기")
