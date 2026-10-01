"""QA에서 찾은 문제의 회귀 테스트 (사진 EXIF, 잘못된 주소, 검색어 NUL, 확인 전 사진 공개 범위, 정정 요청 표시)"""

import io
from datetime import timedelta
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from places.models import Building, Entrance, Region
from places.tests import make_place

from .models import AccessibilityValue, Report
from .test_views import TempMediaMixin, photo


def phone_photo():
    """GPS·기기 정보(EXIF)가 든 큰 JPEG — 폰으로 찍은 사진 흉내"""
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"                  # 기기 제조사
    exif[0x8825] = {1: "N", 2: (37.0, 37.0, 0.0)}  # GPS 정보
    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), "gray").save(buf, "JPEG", exif=exif)
    return SimpleUploadedFile("IMG_0001.jpg", buf.getvalue(), content_type="image/jpeg")


class QATests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.region = Region.objects.get(code="wolgye1")
        self.place = make_place(self.region, "턱없는 카페")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        self.user = User.objects.create_user(username="jumin", date_joined=timezone.now() - timedelta(days=30))

    def test_uploaded_photo_loses_exif_and_is_resized(self):
        report = Report.objects.create(source="USER_REPORT", entrance=self.door, photo=phone_photo())
        with Image.open(report.photo) as im:
            self.assertEqual(len(im.getexif()), 0)
            self.assertEqual(max(im.size), 1600)
        self.assertTrue(report.photo.name.endswith(".jpg"))

    def test_bad_place_id_is_404_not_500(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("reports:new") + "?place=abc").status_code, 404)

    def test_search_ignores_nul_character(self):
        res = self.client.get(reverse("places:search"), {"q": "턱없\x00는"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["q"], "턱없는")

    def test_pending_photo_only_for_logged_in(self):
        report = Report.objects.create(source="USER_REPORT", status="PENDING", entrance=self.door,
                                       created_by=self.user, photo=photo())
        v = AccessibilityValue(report=report, field_id="has_ramp")
        v.set_value(True)
        v.save()
        detail = reverse("places:detail", args=[self.place.pk])
        self.assertContains(self.client.get(detail), "제보 사진은 로그인하면 볼 수 있어요")
        self.client.force_login(User.objects.create_user(username="neighbor"))
        self.assertContains(self.client.get(detail), report.photo.url)

    def test_building_correction_label_says_building_owner(self):
        building = Building.objects.create(region=self.region, address="월계로 2", lat=self.place.lat, lng=self.place.lng)
        self.place.building = building
        self.place.save()
        report = Report.objects.create(source="OWNER", status="PENDING", building=building, photo=photo())
        v = AccessibilityValue(report=report, field_id="elevator")
        v.set_value(True)
        v.save()
        res = self.client.get(reverse("places:detail", args=[self.place.pk]))
        self.assertContains(res, "건물주가 정정을 요청했어요 (확인 중)")
        self.assertNotContains(res, "사장님이 정정을 요청했어요")


class StripExifCommandTests(TempMediaMixin, TestCase):
    def setUp(self):
        self.use_temp_media()
        call_command("seed_base", stdout=StringIO())
        place = make_place(Region.objects.get(code="wolgye1"))
        self.door = Entrance.objects.create(place=place, name="정문")

    def test_cleans_old_photos_saved_before_the_fix(self):
        report = Report.objects.create(source="USER_REPORT", entrance=self.door)
        report.photo.save("old.jpg", phone_photo(), save=False)          # 수정 전처럼 원본 그대로 저장
        Report.objects.filter(pk=report.pk).update(photo=report.photo.name)
        out = StringIO()
        call_command("strip_photo_exif", "--dry-run", stdout=out)
        self.assertIn("정리 대상 1장", out.getvalue())
        call_command("strip_photo_exif", stdout=StringIO())
        report.refresh_from_db()
        with Image.open(report.photo) as im:
            self.assertEqual(len(im.getexif()), 0)
        out = StringIO()
        call_command("strip_photo_exif", stdout=out)
        self.assertIn("정리 0장 · 이미 깨끗함 1장", out.getvalue())

    def test_all_option_reprocesses_clean_photos(self):
        report = Report.objects.create(source="USER_REPORT", entrance=self.door, photo=phone_photo())  # 이미 정리됨
        out = StringIO()
        call_command("strip_photo_exif", stdout=out)
        self.assertIn("정리 0장 · 이미 깨끗함 1장", out.getvalue())
        out = StringIO()
        call_command("strip_photo_exif", "--all", stdout=out)
        self.assertIn("정리 1장", out.getvalue())
        report.refresh_from_db()
        self.assertTrue(report.photo.storage.exists(report.photo.name))
