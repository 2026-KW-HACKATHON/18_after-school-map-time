"""주민 제보 화면 테스트 (와이어프레임 8·9번, 기획 v2 7장)"""

import shutil
import tempfile
from datetime import timedelta
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from places.models import Entrance
from places.tests import make_place, make_region

from .models import Report

# 1×1 GIF (사진 필드 테스트용)
GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def photo():
    return SimpleUploadedFile("door.gif", GIF, content_type="image/gif")


class TempMediaMixin:
    def use_temp_media(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)


class ReportFormTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.place = make_place(make_region("test"), "월계 약국")
        self.user = User.objects.create_user(username="jumin")
        self.client.force_login(self.user)
        self.url = reverse("reports:new")

    def post(self, **data):
        return self.client.post(self.url, {"photo": photo(), **data})

    def test_login_required(self):
        self.client.logout()
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("account_login"), res["Location"])

    def test_report_existing_place_goes_to_main_entrance_as_pending(self):
        res = self.post(place=self.place.pk, step_height_cm="12", has_ramp="false", door_type="여닫이",
                        profiles=["WHEELCHAIR"], note="문이 무거워요")
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertEqual((report.status, report.source, report.created_by), ("PENDING", "USER_REPORT", self.user))
        self.assertEqual(report.entrance, Entrance.objects.get(place=self.place))  # 출입구가 없으면 '정문' 생성
        self.assertEqual(report.profiles, ["WHEELCHAIR"])
        values = {v.field_id: v.value for v in report.values.all()}
        self.assertEqual(set(values), {"step_height_cm", "has_ramp", "door_type"})  # '모름'은 저장 안 함
        self.assertIs(values["has_ramp"], False)
        self.assertTrue(report.photo.name)

    def test_photo_required(self):
        res = self.client.post(self.url, {"place": self.place.pk, "step_height_cm": "3"})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Report.objects.exists())

    def test_needs_some_information(self):
        res = self.post(place=self.place.pk)
        self.assertContains(res, "입구 정보를 하나 이상")
        self.assertFalse(Report.objects.exists())

    def test_same_place_once_per_24_hours(self):
        self.post(place=self.place.pk, step_height_cm="3")
        res = self.post(place=self.place.pk, step_height_cm="4")
        self.assertContains(res, "24시간에 한 번")
        Report.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.post(place=self.place.pk, step_height_cm="4").status_code, 302)

    def test_new_place_suggestion(self):
        res = self.post(step_height_cm="0")
        self.assertContains(res, "장소 이름을 입력해 주세요")
        res = self.post(suggested_name="월계시장 입구 카페", location_text="시장 정문 옆",
                        lat="37.626000", lng="127.059000", step_height_cm="0")
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertTrue(report.is_new_place)
        self.assertEqual(report.suggested_name, "월계시장 입구 카페")

    def test_done_page(self):
        self.assertContains(self.client.get(reverse("reports:done")), "제보가 접수되었습니다")


class ConfirmViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.place = make_place(make_region("test"))
        door = Entrance.objects.create(place=self.place)
        self.author = User.objects.create_user(username="author")
        self.report = Report.objects.create(source="USER_REPORT", entrance=door, created_by=self.author)
        self.neighbor = User.objects.create_user(username="neighbor")
        self.detail = reverse("places:detail", args=[self.place.pk])

    def test_neighbor_confirms(self):
        self.client.force_login(self.neighbor)
        res = self.client.post(reverse("reports:confirm", args=[self.report.pk]), {"next": self.detail})
        self.assertRedirects(res, self.detail, fetch_redirect_response=False)
        self.assertEqual(self.report.confirmations.count(), 1)

    def test_external_next_is_ignored(self):
        self.client.force_login(self.neighbor)
        res = self.client.post(reverse("reports:confirm", args=[self.report.pk]), {"next": "//evil.example.com/"})
        self.assertEqual(res["Location"], "/")

    def test_author_cannot_confirm(self):
        self.client.force_login(self.author)
        self.client.post(reverse("reports:confirm", args=[self.report.pk]), {"next": self.detail})
        self.assertEqual(self.report.confirmations.count(), 0)
