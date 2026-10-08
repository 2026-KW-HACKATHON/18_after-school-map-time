"""운영자 제보 기록 삭제 — 확인 화면, 동의 필수, 사진·값 정리, 반영된 기록이면 다시 판정"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from judgments.engine import recompute_place
from judgments.models import Judgment
from places.models import Entrance, Region
from places.tests import make_place
from reports.models import AccessibilityValue, Report
from reports.test_views import TempMediaMixin, photo


class ReportDeleteTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.place = make_place(Region.objects.get(code="wolgye1"), "계단 약국")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        self.survey = self.report("TEAM_SURVEY", "VERIFIED", step_height_cm=15, step_count=1, door_width_cm=90, has_ramp=False)
        self.ramp = self.report("USER_REPORT", "VERIFIED", has_ramp=True)          # 반영된 주민 제보 → 휠체어 가능
        self.rejected = self.report("USER_REPORT", "REJECTED", with_photo=True, door_width_cm=70)
        recompute_place(self.place)
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.url = reverse("ops:reports-delete")

    def report(self, source, status, with_photo=False, **values):
        r = Report.objects.create(source=source, status=status, entrance=self.door, photo=photo() if with_photo else "")
        for key, raw in values.items():
            v = AccessibilityValue(report=r, field_id=key)
            v.set_value(raw)
            v.save()
        return r

    def wheelchair(self):
        return Judgment.objects.get(place=self.place, profile="WHEELCHAIR").result

    def test_confirm_then_delete_and_recompute(self):
        self.client.force_login(self.staff)
        ids = [self.ramp.pk, self.rejected.pk]
        self.assertEqual(self.wheelchair(), "ACCESSIBLE")
        res = self.client.post(self.url, {"ids": ids, "back": "REJECTED"})
        self.assertContains(res, "2건을 삭제해요")
        self.assertContains(res, "1건은 지도에 반영된 기록")
        res = self.client.post(self.url, {"ids": ids, "back": "REJECTED", "confirm_step": "1"})   # 동의 안 함
        self.assertContains(res, "동의해 주세요")
        self.assertEqual(Report.objects.count(), 3)

        photo_name = self.rejected.photo.name
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(self.url, {"ids": ids, "back": "REJECTED", "confirm_step": "1", "confirm": "on"})
        self.assertRedirects(res, reverse("ops:reports") + "?status=REJECTED")
        self.assertEqual(list(Report.objects.values_list("pk", flat=True)), [self.survey.pk])
        self.assertFalse(AccessibilityValue.objects.filter(report_id__in=ids).exists())
        self.assertFalse(self.rejected.photo.storage.exists(photo_name))
        self.assertEqual(self.wheelchair(), "DIFFICULT")                           # 경사로 제보가 빠져 다시 판정

    def test_team_survey_cannot_be_deleted_here_and_staff_only(self):
        self.client.force_login(self.staff)
        res = self.client.post(self.url, {"ids": [self.survey.pk], "confirm_step": "1", "confirm": "on"})
        self.assertRedirects(res, reverse("ops:reports") + "?status=")
        self.assertTrue(Report.objects.filter(pk=self.survey.pk).exists())
        self.client.force_login(User.objects.create_user(username="jumin"))
        self.client.post(self.url, {"ids": [self.rejected.pk], "confirm_step": "1", "confirm": "on"})
        self.assertTrue(Report.objects.filter(pk=self.rejected.pk).exists())

    def test_list_and_review_have_delete_controls(self):
        self.client.force_login(self.staff)
        res = self.client.get(reverse("ops:reports") + "?status=REJECTED")
        self.assertContains(res, "선택한 기록 삭제")
        self.assertContains(res, f'name="ids" value="{self.rejected.pk}"')
        self.assertContains(self.client.get(reverse("ops:report-review", args=[self.rejected.pk])), "이 기록 삭제")
