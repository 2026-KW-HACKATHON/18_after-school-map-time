"""주민 제보 화면 테스트 (와이어프레임 8·9번, 기획 v2 7장)"""

import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from places.models import Entrance, Place
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

    def test_new_place_details_remain_pending_until_review(self):
        res = self.post(suggested_name="새 약국", suggested_category="PHARMACY",
                        suggested_address="서울 노원구 광운로 20", suggested_floor="-1",
                        suggested_phone="02-123-4567", lat="37.626123", lng="127.058789", note="입구 확인")
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertEqual(report.status, "PENDING")
        self.assertIsNone(report.target)
        self.assertEqual((report.suggested_category, report.suggested_floor), ("PHARMACY", -1))
        self.assertEqual(report.suggested_address, "서울 노원구 광운로 20")
        self.assertEqual(report.suggested_phone, "02-123-4567")
        self.assertEqual(str(report.lat), "37.626123")

    def test_invalid_coordinates_and_details_do_not_create_report(self):
        for invalid in ({"lat": "91", "lng": "127"}, {"lat": "37", "lng": "181"},
                        {"lat": "37"}, {"lng": "127"}, {"suggested_category": "INVALID"},
                        {"suggested_floor": "32768"}):
            with self.subTest(invalid=invalid):
                res = self.post(suggested_name="새 가게", location_text="월계역 앞", note="입구 확인", **invalid)
                self.assertEqual(res.status_code, 200)
                self.assertTrue(res.context["form"].errors)
                self.assertFalse(Report.objects.exists())

    def test_map_and_details_preserved_after_validation_error(self):
        res = self.client.post(self.url, {"suggested_name": "새 카페", "suggested_category": "CAFE",
                                        "suggested_floor": "2", "lat": "37.626100", "lng": "127.058800"})
        self.assertContains(res, 'id="picker-map"')
        self.assertContains(res, 'value="37.626100"')
        self.assertEqual(res.context["form"]["suggested_floor"].value(), "2")

    def test_invalid_entrance_values_are_rejected_before_saving(self):
        for key, value in (("step_height_cm", "-1"), ("step_count", "51"), ("has_ramp", "invalid"),
                           ("door_width_cm", "1001"), ("door_type", "창문"), ("profiles", ["INVALID"])):
            with self.subTest(field=key):
                res = self.post(suggested_name="새 가게", location_text="월계역 앞", note="입구 확인",
                                **{key: value})
                self.assertEqual(res.status_code, 200)
                self.assertIn(key, res.context["form"].errors)
                self.assertFalse(Report.objects.exists())

    def test_existing_place_has_no_new_place_fields(self):
        res = self.client.get(self.url, {"place": self.place.pk})
        self.assertNotContains(res, 'id="picker-map"')
        self.assertNotIn("suggested_category", res.context["form"].fields)

    def test_new_place_needs_point_or_location_text(self):
        res = self.post(suggested_name="위치 없는 가게", note="입구 확인")
        self.assertContains(res, "지도를 눌러 위치를 표시하거나")
        self.assertFalse(Report.objects.exists())

    def test_location_text_only_is_saved_without_coordinates(self):
        res = self.post(suggested_name="새 가게", location_text="월계역 정문 옆", step_height_cm="0")
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertEqual(report.location_text, "월계역 정문 옆")
        self.assertIsNone(report.lat)
        self.assertIsNone(report.lng)

    def test_all_entrance_inputs_and_both_coordinates_are_saved_to_their_fields(self):
        res = self.post(suggested_name="새 가게", lat="0", lng="0", step_height_cm="0",
                        step_count="0", has_ramp="false", door_width_cm="90.5", door_type="자동문",
                        profiles=["WHEELCHAIR"], note="직접 확인")
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertEqual((report.lat, report.lng), (Decimal("0"), Decimal("0")))
        self.assertEqual({v.field_id: v.value for v in report.values.all()}, {
            "step_height_cm": Decimal("0"), "step_count": Decimal("0"), "has_ramp": False,
            "door_width_cm": Decimal("90.5"), "door_type": "자동문",
        })
        self.assertEqual((report.profiles, report.note), (["WHEELCHAIR"], "직접 확인"))

    def test_new_place_uses_shared_picker_region_and_search_sdk(self):
        with override_settings(KAKAO_JAVASCRIPT_KEY="test-key"):
            res = self.client.get(self.url)
        self.assertContains(res, 'data-lat="37.626200"')
        self.assertContains(res, 'id="picker-locate"')
        self.assertContains(res, 'id="place-search"')
        self.assertContains(res, "libraries=services")
        self.assertTemplateUsed(res, "includes/location_picker.html")
        self.assertTemplateUsed(res, "includes/location_picker_js.html")
        self.assertTemplateNotUsed(res, "ops/_picker_js.html")

    def test_existing_place_ignores_suggestion_and_owner_fields(self):
        res = self.client.get(self.url, {"place": self.place.pk})
        for key in ("assistance_offered", "portable_ramp", "portable_ramp_length_cm", "suggested_phone"):
            self.assertNotIn(key, res.context["form"].fields)
        res = self.post(place=self.place.pk, has_ramp="false", suggested_name="덮어쓴 이름",
                        suggested_phone="02-000", assistance_offered="true", portable_ramp="true")
        self.assertRedirects(res, reverse("reports:done"))
        report = Report.objects.get()
        self.assertEqual(report.suggested_name, "")
        self.assertEqual(report.suggested_phone, "")
        self.assertEqual(set(report.values.values_list("field_id", flat=True)), {"has_ramp"})
        self.place.refresh_from_db()
        self.assertEqual(self.place.name, "월계 약국")

    def test_suggestion_to_operator_review_preserves_details_and_recomputes_judgment(self):
        from judgments.models import Judgment

        self.post(suggested_name="제안 약국", suggested_category="PHARMACY", suggested_floor="-1",
                  suggested_address="광운로 20", suggested_phone="02-123", lat="37.626123", lng="127.058789",
                  step_height_cm="0", door_width_cm="90", has_ramp="false")
        self.assertFalse(Place.objects.filter(name="제안 약국").exists())
        report = Report.objects.get()
        staff = User.objects.create_user(username="reviewer", is_staff=True)
        self.client.force_login(staff)
        url = reverse("ops:report-review", args=[report.pk])
        res = self.client.get(url)
        data = {key: res.context["form"][key].value() for key in
                ("place_name", "category", "address", "floor", "phone", "lat", "lng")}
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(url, {"action": "approve", **data})
        self.assertRedirects(res, reverse("ops:report-done", args=[report.pk]))
        report.refresh_from_db()
        place = report.entrance.place
        self.assertEqual((place.name, place.category, place.address, place.floor, place.phone),
                         ("제안 약국", "PHARMACY", "광운로 20", -1, "02-123"))
        self.assertEqual((place.lat, place.lng), (Decimal("37.626123"), Decimal("127.058789")))
        self.assertEqual(report.status, Report.Status.VERIFIED)
        self.assertTrue(Judgment.objects.filter(place=place).exists())
        form = self.client.get(reverse("ops:place-edit", args=[place.pk])).context["form"]
        self.assertEqual(form["step_height_cm"].value(), Decimal("0"))
        self.assertEqual(form["door_width_cm"].value(), Decimal("90"))
        self.assertEqual(form["has_ramp"].value(), "false")

    def test_existing_report_approval_fills_operator_entrance_fields(self):
        self.post(place=self.place.pk, step_height_cm="0", step_count="0", has_ramp="false",
                  door_width_cm="90.5", door_type="자동문")
        report = Report.objects.get()
        staff = User.objects.create_user(username="reviewer", is_staff=True)
        self.client.force_login(staff)
        url = reverse("ops:place-edit", args=[self.place.pk])
        self.assertIsNone(self.client.get(url).context["form"]["step_height_cm"].value())
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(reverse("ops:report-review", args=[report.pk]), {"action": "approve"})
        self.assertRedirects(res, reverse("ops:report-done", args=[report.pk]))
        res = self.client.get(url)
        form = res.context["form"]
        for key, expected in {"step_height_cm": Decimal("0"), "step_count": Decimal("0"),
                              "has_ramp": "false", "door_width_cm": Decimal("90.5"),
                              "door_type": "자동문"}.items():
            with self.subTest(field=key):
                self.assertEqual(form[key].value(), expected)
        self.assertInHTML('<option value="false" selected>없음</option>', str(form["has_ramp"]))
        self.assertInHTML('<option value="자동문" selected>자동문</option>', str(form["door_type"]))


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


class NewPlaceLocationTests(TempMediaMixin, TestCase):
    """새 장소 제보는 지도에서 고른 위치 또는 위치 설명이 있어야 함"""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.client.force_login(User.objects.create_user(username="jumin"))
        self.url = reverse("reports:new")

    def post(self, **data):
        return self.client.post(self.url, {"photo": photo(), "suggested_name": "새 가게", "step_height_cm": "0", **data})

    def test_location_required(self):
        self.assertContains(self.post(), "지도를 눌러 위치를 표시하거나")
        self.assertFalse(Report.objects.exists())

    def test_map_point_only_is_enough(self):
        self.assertEqual(self.post(lat="37.626100", lng="127.058800").status_code, 302)

    def test_location_text_only_is_enough(self):
        self.assertEqual(self.post(location_text="월계역 2번 출구 앞").status_code, 302)

    def test_picker_only_for_new_place(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'id="picker-map"')
        self.assertContains(res, 'data-lat="37.626200"')   # 지역 중심에서 시작
        place = make_place(make_region("test"))
        self.assertNotContains(self.client.get(self.url, {"place": place.pk}), 'id="picker-map"')
