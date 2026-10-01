"""주민 → 운영자 입구 사진 수정 요청 (예전 모습, 얼굴·번호판)"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Notification, User
from judgments.services import required_confirmations
from places.models import Entrance, Region
from places.tests import make_place

from .models import PHOTO_FIX_PREFIX, AccessibilityValue, Report
from .selectors import latest_photo
from .test_views import TempMediaMixin, photo


class PhotoFixTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.place = make_place(Region.objects.get(code="wolgye1"), "턱없는 카페")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        self.shown = Report.objects.create(source="TEAM_SURVEY", status="VERIFIED", entrance=self.door, photo=photo())
        v = AccessibilityValue(report=self.shown, field_id="has_ramp")
        v.set_value(True)
        v.save()
        self.jumin = User.objects.create_user(username="jumin", date_joined=timezone.now() - timedelta(days=30))
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.url = reverse("reports:photo-fix", args=[self.door.pk])
        self.detail = reverse("places:detail", args=[self.place.pk])

    def request_fix(self, **extra):
        self.client.force_login(self.jumin)
        return self.client.post(self.url, {"reason": "내 얼굴이나 아는 사람 얼굴이 나와요", "next": self.detail, **extra})

    def test_link_under_photo_and_login_required(self):
        self.assertContains(self.client.get(self.detail), "사진에 문제가 있나요? 수정 요청하기")
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_request_without_photo_is_operator_only(self):
        res = self.request_fix()
        self.assertRedirects(res, self.detail)
        req = Report.objects.get(source="USER_REPORT")
        self.assertTrue(req.note.startswith(PHOTO_FIX_PREFIX))
        self.assertEqual((req.entrance, req.status, bool(req.photo)), (self.door, "PENDING", False))
        self.assertIsNone(required_confirmations(req))
        self.assertNotContains(self.client.get(self.detail), reverse("reports:confirm", args=[req.pk]))
        self.assertContains(self.request_fix(), "아직 확인 중")                    # 같은 입구 두 번째 요청
        # 사진 수정 요청은 일반 제보 24시간 제한에 걸리지 않음
        res = self.client.post(reverse("reports:new") + f"?place={self.place.pk}", {"photo": photo(), "has_ramp": "true"})
        self.assertRedirects(res, reverse("reports:done"))

    def test_operator_takes_down_current_photo(self):
        self.request_fix()
        req = Report.objects.get(source="USER_REPORT")
        old_name = self.shown.photo.name
        self.client.force_login(self.staff)
        review = reverse("ops:report-review", args=[req.pk])
        res = self.client.get(review)
        self.assertContains(res, "주민 사진 수정 요청")
        self.assertContains(res, "지금 공개된 사진")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(review, {"action": "approve", "review_note": "", "remove_current_photo": "on"})
        self.shown.refresh_from_db()
        self.assertEqual(self.shown.photo.name, "")
        self.assertFalse(self.shown.photo.storage.exists(old_name))
        self.assertIsNone(latest_photo(self.door))
        n = Notification.objects.get(user=self.jumin)
        self.assertIn("사진 수정 요청을 처리했어요", n.message)

    def test_new_photo_replaces_shown_one(self):
        self.request_fix(reason="예전 모습이에요 (공사·이전 등)", photo=photo())
        req = Report.objects.get(source="USER_REPORT")
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("ops:report-review", args=[req.pk]), {"action": "approve", "review_note": ""})
        req.refresh_from_db()
        self.assertEqual(latest_photo(self.door), req.photo)
        self.assertTrue(Report.objects.get(pk=self.shown.pk).photo)               # 체크 안 하면 예전 사진은 기록으로 남음
