""""지금도 맞아요" 재확인 테스트 — 판정·값은 그대로, 최근 확인일·신뢰도 표시만"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from judgments.engine import recompute_place
from judgments.models import Judgment
from places.models import Entrance, Region
from places.tests import make_place
from reports.selectors import current_values

from .models import AccessibilityValue, Reconfirmation, Report
from .services import last_checked_at, verify_report


class ReconfirmTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.region = Region.objects.get(code="wolgye1")
        self.place = make_place(self.region, "턱없는 카페")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        self.old = timezone.now() - timedelta(days=200)
        self.report(self.door, {"step_height_cm": 0, "step_count": 0, "door_width_cm": 90, "has_ramp": False},
                    observed_at=self.old)
        recompute_place(self.place)
        self.user = User.objects.create_user(username="jumin")
        self.detail = reverse("places:detail", args=[self.place.pk])
        self.url = reverse("reports:reconfirm", args=[self.place.pk])

    def report(self, entrance, values, status="VERIFIED", **kw):
        r = Report.objects.create(source="USER_REPORT", status=status, entrance=entrance, **kw)
        for key, raw in values.items():
            v = AccessibilityValue(report=r, field_id=key)
            v.set_value(raw)
            v.save()
        return r

    def test_updates_last_checked_but_not_judgment(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.detail), "지금도 맞아요")
        self.client.post(self.url, {"next": self.detail})
        self.assertEqual(timezone.localtime(last_checked_at(self.place)).date(), timezone.localdate())
        res = self.client.get(self.detail)
        self.assertContains(res, f"최근 확인: {timezone.localdate():%Y}년")
        self.assertContains(res, '주민 1명이 "지금도 맞아요"라고 확인했어요')
        self.assertEqual(Judgment.objects.get(place=self.place, profile="WHEELCHAIR").result, "ACCESSIBLE")
        self.assertEqual(Report.objects.count(), 1)                              # 값 기록은 늘지 않음

    def test_once_per_day(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"next": self.detail})
        res = self.client.post(self.url, {"next": self.detail}, follow=True)
        self.assertContains(res, "오늘은 이미 확인해 주셨어요")
        self.assertEqual(Reconfirmation.objects.count(), 1)

    def test_not_offered_without_public_info(self):
        empty = make_place(self.region, "정보 없는 가게")
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("places:detail", args=[empty.pk])), "지금도 맞아요")
        self.client.post(reverse("reports:reconfirm", args=[empty.pk]), {"next": "/"})
        self.assertFalse(Reconfirmation.objects.exists())
        self.assertIsNone(last_checked_at(empty))

    def test_pending_downgrade_still_applies_after_reconfirm(self):
        """재확인이 값을 복사하지 않으므로, 나중에 승인된 하향 제보가 그대로 반영된다"""
        pending = self.report(self.door, {"step_height_cm": 30}, status="PENDING",
                              observed_at=timezone.now() - timedelta(days=1))
        self.client.force_login(self.user)
        self.client.post(self.url, {"next": self.detail})
        with self.captureOnCommitCallbacks(execute=True):
            verify_report(pending)
        self.assertEqual(current_values(self.door)["step_height_cm"].value, 30)
        self.assertEqual(Judgment.objects.get(place=self.place, profile="WHEELCHAIR").result, "DIFFICULT")

    def test_district_lists_stale_places(self):
        staff = User.objects.create_user(username="staff", is_staff=True)
        make_place(self.region, "정보 없는 가게")
        self.client.force_login(staff)
        recheck = self.client.get(reverse("ops:district")).context["recheck"]
        self.assertEqual((recheck["never"], recheck["stale_count"]), (1, 1))     # 200일 전 확인
        Reconfirmation.objects.create(place=self.place, user=self.user)            # 주민이 오늘 확인
        recheck = self.client.get(reverse("ops:district")).context["recheck"]
        self.assertEqual(recheck["stale_count"], 0)

    def test_login_required(self):
        res = self.client.post(self.url, {"next": self.detail})
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Reconfirmation.objects.exists())
