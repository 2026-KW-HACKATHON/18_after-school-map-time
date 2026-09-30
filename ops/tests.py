"""운영자 화면 테스트 (와이어프레임 10~18번)"""

from decimal import Decimal
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
    def test_review_prefills_and_saves_corrected_place_details(self):
        report = self.user_report(step_height_cm=0)
        report.suggested_category = "CAFE"
        report.suggested_address = "서울 노원구 광운로 20"
        report.suggested_floor = -1
        report.suggested_phone = "02-123-4567"
        report.save()
        url = reverse("ops:report-review", args=[report.pk])
        form = self.client.get(url).context["form"]
        self.assertEqual(form.initial["category"], "CAFE")
        self.assertEqual(form.initial["floor"], -1)
        self.assertEqual(form.initial["phone"], report.suggested_phone)
        self.assertEqual(form.initial["address"], report.suggested_address)
        res = self.client.post(url, {"action": "approve", "place_name": "확인한 카페", "category": "CAFE",
                                    "address": "서울 노원구 광운로 21", "floor": "2", "phone": "02-987-6543",
                                    "lat": "37.626100", "lng": "127.058800"})
        self.assertRedirects(res, reverse("ops:report-done", args=[report.pk]))
        report.refresh_from_db()
        place = report.target_place
        self.assertEqual((place.floor, place.phone, place.address), (2, "02-987-6543", "서울 노원구 광운로 21"))
        self.assertEqual(report.suggested_floor, -1)  # 원본 제보는 유지

    def test_new_place_review_rejects_out_of_range_coordinates(self):
        report = self.user_report(step_height_cm=0)
        res = self.client.post(reverse("ops:report-review", args=[report.pk]),
                               {"action": "approve", "place_name": "새 가게", "lat": "91", "lng": "127"})
        self.assertIn("lat", res.context["form"].errors)
        self.assertFalse(Place.objects.exists())

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


class PlaceEntrancePrefillTests(OpsTestBase):
    def edit_url(self, place):
        return reverse("ops:place-edit", args=[place.pk])

    def post_values(self, place, **changes):
        form = self.client.get(self.edit_url(place)).context["form"]
        data = {key: form[key].value() for key in
                ("name", "category", "address", "floor", "phone", "lat", "lng")}
        data.update({key: value for key, value in form.initial.items() if key in
                     ("step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type")})
        data.update(changes)
        return self.client.post(self.edit_url(place), data)

    def test_latest_verified_value_per_field_ignores_pending_and_rejected(self):
        place, door = self.cafe_with_door(step="0")
        recent = self.user_report(door, step_count=2)
        Report.objects.filter(pk=recent.pk).update(status="VERIFIED")
        old = self.user_report(door, step_height_cm=30)
        Report.objects.filter(pk=old.pk).update(status="VERIFIED", observed_at=timezone.now() - timedelta(days=2))
        self.user_report(door, step_height_cm=40)
        rejected = self.user_report(door, has_ramp=True)
        Report.objects.filter(pk=rejected.pk).update(status="REJECTED")
        form = self.client.get(self.edit_url(place)).context["form"]
        self.assertEqual(form["step_height_cm"].value(), Decimal("0"))
        self.assertEqual(form["step_count"].value(), Decimal("2"))
        self.assertEqual(form["has_ramp"].value(), "false")
        self.assertEqual(form["door_width_cm"].value(), Decimal("90"))

    def test_main_entrance_precedes_older_side_entrance(self):
        place, side = self.cafe_with_door(step="30")
        side.is_main = False
        side.save(update_fields=["is_main"])
        main = Entrance.objects.create(place=place, name="주 출입구", is_main=True)
        report = self.user_report(main, step_height_cm=0)
        Report.objects.filter(pk=report.pk).update(status="VERIFIED")
        self.assertEqual(self.client.get(self.edit_url(place)).context["form"]["step_height_cm"].value(), Decimal("0"))

    def test_get_does_not_create_entrances_or_reports(self):
        place = make_place(self.region)
        self.client.get(self.edit_url(place))
        self.assertFalse(Entrance.objects.exists())
        self.assertFalse(Report.objects.exists())

    def test_name_only_edit_does_not_copy_resident_values_into_survey(self):
        place, door = self.cafe_with_door()
        original = self.user_report(door, step_height_cm=0, step_count=0, has_ramp=False,
                                    door_width_cm=90, door_type="자동문")
        Report.objects.filter(pk=original.pk).update(status="VERIFIED")
        count = Report.objects.count()
        res = self.post_values(place, name="새 이름")
        self.assertRedirects(res, reverse("ops:place-saved", args=[place.pk]))
        self.assertEqual(Report.objects.count(), count)
        from reports.selectors import current_values
        self.assertEqual(current_values(door)["has_ramp"].report_id, original.pk)

    def test_changed_field_only_is_saved_and_blank_keeps_old_values(self):
        place, door = self.cafe_with_door()
        count = Report.objects.count()
        res = self.post_values(place, step_height_cm="30", door_width_cm="")
        self.assertRedirects(res, reverse("ops:place-saved", args=[place.pk]))
        self.assertEqual(Report.objects.count(), count + 1)
        newest = Report.objects.filter(entrance=door).first()
        self.assertEqual(set(newest.values.values_list("field_id", flat=True)), {"step_height_cm"})
        form = self.client.get(self.edit_url(place)).context["form"]
        self.assertEqual(form["step_height_cm"].value(), Decimal("30"))
        self.assertEqual(form["door_width_cm"].value(), Decimal("90"))
        self.assertEqual(form["has_ramp"].value(), "false")

    def test_explicit_recheck_keeps_new_survey_history(self):
        place, door = self.cafe_with_door()
        count = Report.objects.count()
        res = self.post_values(place, source_note="운영팀 재확인", observed_on=timezone.localdate().isoformat())
        self.assertRedirects(res, reverse("ops:place-saved", args=[place.pk]))
        self.assertEqual(Report.objects.count(), count + 1)
        self.assertIn("운영팀 재확인", Report.objects.filter(entrance=door).first().note)

    def test_validation_error_keeps_submitted_entrance_values(self):
        place, _ = self.cafe_with_door()
        res = self.post_values(place, name="", step_height_cm="12", has_ramp="true")
        self.assertEqual(res.status_code, 200)
        form = res.context["form"]
        self.assertEqual(form["step_height_cm"].value(), "12")
        self.assertEqual(form["has_ramp"].value(), "true")
        self.assertEqual(Report.objects.count(), 1)


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


class ListLabelTests(OpsTestBase):
    def test_processed_report_label_and_no_flags(self):
        _, door = self.cafe_with_door()
        report = self.user_report(door, step_height_cm=30)
        Report.objects.filter(pk=report.pk).update(status="VERIFIED")
        res = self.client.get(reverse("ops:reports"), {"status": ""})
        self.assertContains(res, "승인됨")
        self.assertNotContains(res, "반영됨")
        self.assertNotContains(res, "가입 7일 미만")     # 처리된 제보에는 검토용 배지 없음

    def test_place_form_has_picker(self):
        self.assertContains(self.client.get(reverse("ops:place-new")), 'id="picker-map"')
