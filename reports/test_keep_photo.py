"""칸을 잘못 적어 다시 보여 줄 때 올린 사진을 잃지 않기 (core/uploads.py)"""

import re
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from places.models import Entrance, Region
from places.tests import make_place

from .models import Report
from .test_views import TempMediaMixin, photo


def token_in(res):
    m = re.search(r'name="photo_token" value="([^"]+)"', res.content.decode())
    return m.group(1) if m else None


class KeepPhotoTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.place = make_place(Region.objects.get(code="wolgye1"), "턱없는 카페")
        Entrance.objects.create(place=self.place, name="정문")
        self.user = User.objects.create_user(username="jumin", date_joined=timezone.now() - timedelta(days=30))
        self.client.force_login(self.user)
        self.url = reverse("reports:new") + f"?place={self.place.pk}"

    def test_photo_survives_a_mistake(self):
        res = self.client.post(self.url, {"photo": photo()})                    # 입구 정보도 설명도 없음 → 오류
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "올리신 사진을 그대로 쓸게요")
        token = token_in(res)
        self.assertTrue(token)
        res = self.client.post(self.url, {"photo_token": token, "has_ramp": "true"})  # 사진 다시 안 고름
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertTrue(report.photo.name.startswith("reports/"))
        self.assertTrue(report.photo.storage.exists(report.photo.name))

    def test_tampered_token_is_ignored(self):
        res = self.client.post(self.url, {"photo_token": "upload_tmp/../../secret", "has_ramp": "true"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("photo", res.context["form"].errors)
        self.assertFalse(Report.objects.exists())

    def test_owner_form_keeps_photo_too(self):
        from owners.models import ClaimCode, OwnerClaim
        from owners.services import claim_with_code

        staff = User.objects.create_user(username="staff", is_staff=True)
        claim_with_code(self.user, ClaimCode.issue(place=self.place).code).review(OwnerClaim.Status.APPROVED, staff)
        url = reverse("owners:declaration", args=[self.place.pk])
        res = self.client.post(url, {"portable_ramp": "true", "photo": photo()})   # 경사로 길이 빠짐
        self.assertContains(res, "올리신 사진을 그대로 쓸게요")
        self.client.post(url, {"portable_ramp": "true", "portable_ramp_length_cm": "120",
                               "photo_token": token_in(res)})
        self.assertTrue(Report.objects.filter(source="OWNER").exclude(photo="").exists())
