"""시설 제보: 실제 폼 제출 → 검토 → 공개 조회와 기존 입구 판정 회귀 테스트."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from html.parser import HTMLParser

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from judgments.engine import recompute_place
from judgments.models import Judgment
from judgments.services import report_effect, required_confirmations
from ops.services import approve_report
from places.facilities import KIND_FIELDS
from places.models import AccessFacility, Building, Entrance, FieldDefinition
from places.tests import make_place, make_region

from .forms import ReportForm
from .models import AccessibilityValue, Report
from .selectors import current_values
from .services import ConfirmationError, confirm_report, has_public_info, last_checked_at, reject_report, verify_report
from .test_views import TempMediaMixin, photo


SAMPLES = {
    "ENTRANCE": {"step_height_cm": "0", "step_count": "0", "has_ramp": "false", "door_width_cm": "90",
                 "door_type": "자동문", "entrance_automatic_door": "true", "entrance_available": "true"},
    "ELEVATOR": {"facility_available": "true", "facility_connected_floors": "지하 1층 → 1층 → 2층",
                 "facility_wheelchair": "true", "facility_door_width_cm": "90", "facility_interior_space": "140 × 150 cm",
                 "facility_accessible_buttons": "false", "facility_braille": "true"},
    "ESCALATOR": {"facility_available": "false", "facility_connected_floors": "1층 → 2층",
                  "facility_direction": "상승", "facility_operating": "false", "facility_alternative_route": "true"},
    "STAIRS": {"facility_available": "true", "facility_connected_floors": "1층 → 2층",
               "facility_step_count": "20", "facility_handrail": "true", "facility_alternative_route": "false"},
    "RAMP": {"facility_available": "true", "facility_width_cm": "120", "facility_slope_deg": "5.5",
             "facility_handrail": "false"},
    "TOILET": {"facility_available": "true", "facility_wheelchair": "true", "facility_door_width_cm": "85",
               "facility_handrail": "true"},
    "OTHER": {"facility_available": "true"},
}


class HiddenInputs(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden" and attrs.get("name"):
            self.inputs[attrs["name"]] = attrs.get("value", "")


class FacilityReportTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.region = make_region("facilities")
        self.building = Building.objects.create(region=self.region, name="공용 건물", address="월계로 1",
                                                lat="37.620000", lng="127.050000")
        self.place = make_place(self.region, "2층 가게", building=self.building, floor=2)
        self.user = User.objects.create_user(username="facility_reporter")
        self.staff = User.objects.create_user(username="reviewer", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("reports:new")

    def submit(self, kind="ELEVATOR", **overrides):
        payload = dict(place=self.place.pk, facility_kind=kind, ownership="PLACE", target_reference="new",
                       facility_name=f"{kind} 시설", location_text="2층 복도 동쪽", note="직접 확인했어요",
                       lat="37.620001", lng="127.050001", photo=photo(), **SAMPLES[kind])
        payload.update(overrides)
        return self.client.post(self.url, payload)

    def proposal(self, kind="ELEVATOR", **overrides):
        self.assertRedirects(self.submit(kind, **overrides), reverse("reports:done"))
        return Report.objects.latest("pk")

    def test_each_kind_registers_only_after_operator_approval_and_preserves_values(self):
        for kind in SAMPLES:
            with self.subTest(kind=kind):
                report = self.proposal(kind)
                self.assertTrue(report.is_facility_proposal)
                self.assertIsNone(report.facility_id)
                self.assertIsNone(report.entrance_id)
                self.assertEqual(set(report.values.values_list("field_id", flat=True)), set(SAMPLES[kind]))
                self.assertIsNone(required_confirmations(report))
                self.assertEqual(report_effect(report), [])
                self.assertEqual(report.lat, Decimal("37.620001"))
                self.assertEqual(report.lng, Decimal("127.050001"))
                self.assertEqual(report.location_text, "2층 복도 동쪽")
                verify_report(report, by=self.staff)
                report.refresh_from_db()
                target = report.entrance if kind == "ENTRANCE" else report.facility
                self.assertEqual(target.place, self.place)
                self.assertIsNone(target.building_id)
                self.assertEqual(target.name, f"{kind} 시설")
                for key, raw in SAMPLES[kind].items():
                    expected = {"true": True, "false": False}.get(raw, raw)
                    value = current_values(target)[key]
                    if value.field.value_type == "NUMBER":
                        expected = Decimal(raw)
                    self.assertEqual(value.value, expected)
                self.assertEqual(report.status, "VERIFIED")

    def test_building_common_facility_is_visible_to_all_shops_in_same_building(self):
        other = make_place(self.region, "3층 가게", building=self.building, floor=3)
        report = self.proposal(ownership="BUILDING")
        self.assertEqual(report.building, self.building)
        verify_report(report, by=self.staff)
        self.assertEqual(report.facility.building, self.building)
        self.assertIsNone(report.facility.place_id)
        for place in (self.place, other):
            data = self.client.get(f"/api/v1/places/{place.pk}/").json()
            self.assertEqual(data["building"]["facilities"][0]["name"], "ELEVATOR 시설")
            self.assertEqual(data["place"]["facilities"], [])

    def test_building_without_shops_can_receive_facility_reports(self):
        self.place.delete()
        response = self.submit(place="", building=self.building.pk, ownership="BUILDING")
        self.assertRedirects(response, reverse("reports:done"))
        report = Report.objects.get()
        verify_report(report, by=self.staff)
        self.assertEqual(report.facility.building_id, self.building.pk)

    def test_multiple_same_kind_facilities_are_separate_and_existing_facility_can_be_updated(self):
        first = self.proposal(facility_name="동쪽 E/V")
        verify_report(first, by=self.staff)
        second = self.proposal(facility_name="서쪽 E/V")
        verify_report(second, by=self.staff)
        self.assertEqual(self.place.facilities.count(), 2)
        Report.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(hours=25))
        updated = self.proposal(target_reference=f"facility:{first.facility_id}", facility_name="무시할 이름",
                                facility_available="false")
        self.assertEqual(updated.facility_id, first.facility_id)
        self.assertEqual(self.place.facilities.count(), 2)
        self.assertEqual(current_values(first.facility)["facility_available"].value, True)
        verify_report(updated, by=self.staff)
        self.assertIs(current_values(first.facility)["facility_available"].value, False)
        self.assertIs(current_values(second.facility)["facility_available"].value, True)
        first.facility.refresh_from_db()
        self.assertEqual(first.facility.name, "동쪽 E/V")

    def test_additional_entrance_does_not_replace_main_entrance(self):
        main = Entrance.objects.create(place=self.place, name="정문", is_main=True)
        report = self.proposal("ENTRANCE", facility_name="후문")
        verify_report(report, by=self.staff)
        self.assertFalse(report.entrance.is_main)
        self.assertEqual(self.place.entrances.get(is_main=True), main)
        self.assertEqual(self.place.entrances.count(), 2)

    def test_new_place_suggestion_can_include_non_entrance_facility(self):
        report = self.proposal("TOILET", place="", suggested_name="새 공공 장소", suggested_floor="1",
                               suggested_phone="02-123-4567")
        self.assertTrue(report.is_new_place)
        approved = approve_report(report, self.staff, new_place={"name": "새 공공 장소", "category": "PUBLIC",
            "lat": report.lat, "lng": report.lng, "floor": 1, "phone": report.suggested_phone})
        self.assertEqual(approved.facility.place.name, "새 공공 장소")
        self.assertEqual(approved.facility.kind, "TOILET")
        self.assertEqual(approved.facility.place.phone, "02-123-4567")
        self.assertFalse(approved.facility.place.entrances.exists())

    def test_invalid_inputs_are_rejected_without_saving(self):
        for override in ({"facility_kind": "FAKE"}, {"facility_available": "perhaps"},
                         {"facility_door_width_cm": "-1"}, {"facility_door_width_cm": "1001"},
                         {"lng": ""}, {"observed_on": (timezone.localdate() + timedelta(days=1)).isoformat()},
                         {"facility_name": "가" * 51}, {"ownership": "OTHER"}):
            with self.subTest(override=override):
                response = self.submit(**override)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["form"].is_valid())
                self.assertFalse(Report.objects.exists())

    def test_kind_specific_numeric_and_choice_validation(self):
        for kind, override in (("RAMP", {"facility_slope_deg": "91"}),
                               ("STAIRS", {"facility_step_count": "3.5"}),
                               ("ESCALATOR", {"facility_direction": "옆으로"})):
            with self.subTest(kind=kind):
                response = self.submit(kind, **override)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Report.objects.exists())

    def test_optional_dimensions_can_be_omitted_and_unrelated_fields_are_ignored(self):
        response = self.client.post(self.url, dict(place=self.place.pk, facility_kind="RAMP", target_reference="new",
            photo=photo(), note="폭은 재지 못했어요", door_width_cm="-10", facility_direction="FAKE"))
        self.assertRedirects(response, reverse("reports:done"))
        self.assertFalse(Report.objects.get().values.exists())

    def test_wrong_parent_wrong_kind_and_unpublished_targets_cannot_be_selected(self):
        other = make_place(self.region, "다른 가게")
        alien = AccessFacility.objects.create(place=other, kind="ELEVATOR", name="다른 가게 시설")
        hidden = AccessFacility.objects.create(place=self.place, kind="ELEVATOR", name="미확인 시설")
        wrong_kind = AccessFacility.objects.create(place=self.place, kind="RAMP", name="경사로")
        for target in (alien, hidden, wrong_kind):
            with self.subTest(target=target):
                response = self.submit(target_reference=f"facility:{target.pk}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("target_reference", response.context["form"].errors)
        self.assertFalse(Report.objects.exists())

    def test_owner_choice_requires_linked_building(self):
        detached = make_place(self.region, "단독 가게")
        response = self.submit(place=detached.pk, ownership="BUILDING")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ownership", response.context["form"].errors)

    def test_photo_and_observation_are_required(self):
        response = self.client.post(self.url, {"place": self.place.pk, "facility_kind": "OTHER"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("photo", response.context["form"].errors)
        self.assertFalse(Report.objects.exists())

    def test_duplicate_submission_is_limited_but_other_facilities_are_not(self):
        self.proposal(facility_name="동쪽")
        response = self.submit(facility_name="동쪽")
        self.assertContains(response, "24시간에 한 번")
        self.proposal(facility_name="서쪽")
        self.proposal("RAMP", facility_name="동쪽")
        self.assertEqual(Report.objects.count(), 3)

    def test_pending_and_rejected_facilities_are_not_public(self):
        report = self.proposal()
        data = self.client.get(f"/api/v1/places/{self.place.pk}/").json()
        self.assertEqual(data["place"]["facilities"], [])
        detail = self.client.get(reverse("places:detail", args=[self.place.pk]))
        self.assertNotContains(detail, "ELEVATOR 시설")
        reject_report(report, by=self.staff, reason="확인 필요")
        self.assertFalse(self.place.facilities.exists())

    def test_facility_detail_api_and_html_include_counts_location_photo_date_and_facts(self):
        date = timezone.localdate() - timedelta(days=3)
        report = self.proposal(observed_on=date.isoformat())
        verify_report(report, by=self.staff)
        data = self.client.get(f"/api/v1/places/{self.place.pk}/").json()
        section = data["place"]
        facility = section["facilities"][0]
        self.assertEqual(facility["kind"], "ELEVATOR")
        self.assertEqual(facility["location_text"], "2층 복도 동쪽")
        self.assertAlmostEqual(facility["lat"], 37.620001)
        self.assertTrue(facility["photo_url"])
        self.assertTrue(facility["checked_at"].startswith(date.isoformat()))
        self.assertEqual(next(f["value"] for f in facility["fields"] if f["key"] == "facility_available"), "이용 가능")
        self.assertEqual({f["key"] for f in facility["fields"]}, set(KIND_FIELDS["ELEVATOR"]))
        self.assertEqual(next(c["count"] for c in section["facility_counts"] if c["kind"] == "ELEVATOR"), 1)
        response = self.client.get(reverse("places:detail", args=[self.place.pk]))
        self.assertContains(response, "엘리베이터 (E/V) 1개")
        self.assertContains(response, "ELEVATOR 시설")
        self.assertContains(response, "2층 복도 동쪽")
        self.assertContains(response, f'href="{facility["photo_url"]}" target="_blank" rel="noopener" title="사진 크게 보기"')
        self.assertTrue(has_public_info(self.place))
        self.assertEqual(last_checked_at(self.place), report.observed_at)

    def test_note_only_facility_also_has_public_check_date(self):
        report = self.proposal("OTHER", facility_available="", note="로비에 휠체어 대여대가 있어요")
        verify_report(report, by=self.staff)
        self.assertFalse(report.values.exists())
        self.assertTrue(has_public_info(self.place))
        self.assertEqual(last_checked_at(self.place), report.observed_at)

    def test_resident_cannot_approve_facility_or_confirm_it(self):
        report = self.proposal()
        for user in (None, self.user):
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                verify_report(report, by=user)
        with self.assertRaises(ConfirmationError):
            confirm_report(report, self.staff, required=1)
        self.assertFalse(report.confirmations.exists())

    def test_repeated_approval_is_idempotent(self):
        report = self.proposal()
        stale = Report.objects.get(pk=report.pk)
        approve_report(report, self.staff)
        approve_report(stale, self.staff)
        self.assertEqual(self.place.facilities.count(), 1)

    def test_operator_can_delete_place_and_building_facility_reports_without_public_ghosts(self):
        for ownership in ("PLACE", "BUILDING"):
            with self.subTest(ownership=ownership):
                self.client.force_login(self.user)
                report = self.proposal(ownership=ownership)
                verify_report(report, by=self.staff)
                facility_id = report.facility_id
                photo_name = report.photo.name
                self.client.force_login(self.staff)
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse("ops:reports-delete"), {
                        "ids": [report.pk], "confirm_step": "1", "confirm": "on",
                    })
                self.assertEqual(response.status_code, 302)
                self.assertFalse(Report.objects.filter(pk=report.pk).exists())
                self.assertFalse(AccessibilityValue.objects.filter(report_id=report.pk).exists())
                self.assertFalse(report.photo.storage.exists(photo_name))
                self.assertTrue(AccessFacility.objects.filter(pk=facility_id).exists())
                data = self.client.get(f"/api/v1/places/{self.place.pk}/").json()
                self.assertEqual(data["place"]["facilities"], [])
                self.assertEqual(data["building"]["facilities"], [])
                self.assertFalse(has_public_info(self.place))

    def test_operator_review_page_and_approval_use_existing_flow(self):
        report = self.proposal()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("ops:report-review", args=[report.pk]))
        self.assertContains(response, "엘리베이터 (E/V)")
        self.assertContains(response, "2층 복도 동쪽")
        response = self.client.post(reverse("ops:report-review", args=[report.pk]), {"action": "approve"})
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, "VERIFIED")
        self.assertIsNotNone(report.facility_id)

    def test_kind_selection_renders_only_selected_fields_and_reuses_common_picker(self):
        for kind in SAMPLES:
            with self.subTest(kind=kind):
                response = self.client.get(self.url, {"place": self.place.pk, "facility_kind": kind})
                self.assertEqual(response.status_code, 200)
                self.assertEqual({field.name for field in response.context["form"].observation_fields}, set(KIND_FIELDS[kind]))
                if kind != "ENTRANCE":
                    self.assertContains(response, 'id="picker-map"')
                    self.assertNotContains(response, 'name="step_height_cm"')
                self.assertNotContains(response, 'name="assistance_offered"')

    def test_detail_link_selects_existing_facility(self):
        report = self.proposal()
        verify_report(report, by=self.staff)
        response = self.client.get(self.url, {"place": self.place.pk, "facility_kind": "ELEVATOR",
                                              "target_reference": f"facility:{report.facility_id}"})
        self.assertEqual(response.context["form"]["target_reference"].value(), f"facility:{report.facility_id}")

    def test_switch_partial_uses_each_kind_form_without_creating_records(self):
        for kind in KIND_FIELDS:
            with self.subTest(kind=kind):
                response = self.client.get(self.url, {"place": self.place.pk, "facility_kind": kind,
                                                      "partial": "facility-fields"})
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual((data["kind"], data["ownership"]), (kind, "PLACE"))
                for key in KIND_FIELDS[kind]:
                    self.assertIn(f'name="{key}"', data["fields_html"])
                for key in set().union(*KIND_FIELDS.values()) - set(KIND_FIELDS[kind]):
                    self.assertNotIn(f'name="{key}"', data["fields_html"])
                self.assertNotIn('name="photo"', data["fields_html"])
                self.assertNotIn('name="note"', data["fields_html"])
        self.assertFalse(Report.objects.exists())
        self.assertFalse(Entrance.objects.exists())
        self.assertFalse(AccessFacility.objects.exists())

    def test_switch_partial_limits_targets_to_selected_kind_and_ownership(self):
        own = self.proposal("ELEVATOR", facility_name="가게 E/V")
        common = self.proposal("ELEVATOR", ownership="BUILDING", facility_name="공용 E/V")
        other_kind = self.proposal("ESCALATOR", ownership="BUILDING", facility_name="공용 E/S")
        for report in (own, common, other_kind):
            verify_report(report, by=self.staff)
        response = self.client.get(self.url, {"place": self.place.pk, "facility_kind": "ELEVATOR",
                                              "ownership": "BUILDING", "partial": "facility-fields"})
        data = response.json()
        self.assertEqual(data["targets"], [[f"facility:{common.facility_id}", "공용 E/V"], ["new", "새 시설 제안"]])
        self.assertEqual(data["ownership"], "BUILDING")

    def test_switch_partial_rejects_invalid_kind_scope_and_requires_login(self):
        for params in ({"facility_kind": "INVALID"}, {"ownership": "INVALID"}):
            response = self.client.get(self.url, {"place": self.place.pk, "partial": "facility-fields", **params})
            self.assertEqual(response.status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"partial": "facility-fields"}).status_code, 302)

    def test_switch_page_keeps_no_javascript_fallback(self):
        response = self.client.get(self.url, {"place": self.place.pk})
        self.assertContains(response, 'id="facility-observations"')
        self.assertContains(response, 'js/reports/facility-switcher.js')
        self.assertContains(response, '<noscript><button type="submit"')

    def test_post_ignores_fields_from_previous_facility_kind(self):
        report = self.proposal("RAMP", step_height_cm="30", facility_braille="true")
        self.assertEqual(set(report.values.values_list("field_id", flat=True)), set(SAMPLES["RAMP"]))

    def test_rendered_hidden_fields_round_trip_building_ownership_and_facility_kind(self):
        response = self.client.get(self.url, {"place": self.place.pk, "facility_kind": "RAMP", "ownership": "BUILDING"})
        payload = HiddenInputs(response.content.decode()).inputs
        self.assertEqual(payload["ownership"], "BUILDING")
        self.assertEqual(payload["facility_kind"], "RAMP")
        self.assertEqual(payload["place"], str(self.place.pk))
        payload.update(photo=photo(), note="건물 공용 경사로", facility_name="로비 경사로", facility_width_cm="120")
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, reverse("reports:done"))
        report = Report.objects.get()
        self.assertEqual(report.building_id, self.building.pk)
        self.assertEqual(report.facility_kind, "RAMP")

    def test_facility_observations_do_not_change_existing_judgments(self):
        entrance = Entrance.objects.create(place=self.place, is_main=True)
        base = Report.objects.create(entrance=entrance, source="TEAM_SURVEY", status="VERIFIED")
        for key, raw in {"step_height_cm": 0, "has_ramp": False, "door_width_cm": 90}.items():
            value = AccessibilityValue(report=base, field_id=key)
            value.set_value(raw)
            value.save()
        recompute_place(self.place)
        before = dict(Judgment.objects.filter(place=self.place).values_list("profile_id", "result"))
        report = self.proposal(ownership="BUILDING", facility_available="false")
        with self.captureOnCommitCallbacks(execute=True):
            verify_report(report, by=self.staff)
        after = dict(Judgment.objects.filter(place=self.place).values_list("profile_id", "result"))
        self.assertEqual(before, after)
        self.assertFalse(current_values(self.building))  # 기존 elevator BOOL에 자동 복사하지 않는다.

    def test_model_constraints_reject_double_owners_and_double_targets(self):
        for parent in ({}, {"place": self.place, "building": self.building}):
            with self.subTest(parent=parent), self.assertRaises(IntegrityError), transaction.atomic():
                AccessFacility.objects.create(kind="ELEVATOR", name="잘못된 시설", **parent)
        facility = AccessFacility.objects.create(place=self.place, kind="ELEVATOR", name="시설")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Report.objects.create(place=self.place, facility=facility, source="USER_REPORT")
        with self.assertRaises(ValidationError):
            Report(facility=facility, facility_kind="RAMP", source="USER_REPORT").full_clean()

    def test_wrong_scope_and_kind_cannot_be_saved_as_observation(self):
        report = self.proposal()
        for key in ("step_height_cm", "facility_slope_deg"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                AccessibilityValue(report=report, field_id=key, value_number=1).full_clean()

    def test_existing_legacy_form_keeps_original_entrance_fields(self):
        form = ReportForm({"note": "문 앞은 평평해요", "step_height_cm": "0"}, {"photo": photo()},
                          place=self.place, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.entrance_values(), {"step_height_cm": Decimal("0")})

    def test_inactive_or_deleted_definitions_are_not_offered_or_saved(self):
        """관리자가 끄거나 지운 항목은 입력칸도 없고 저장도 안 된다 (QA-02)"""
        FieldDefinition.objects.filter(key="facility_available").update(is_active=False)
        FieldDefinition.objects.filter(key="facility_braille").delete()  # 저장된 값이 없는 항목은 지울 수 있다
        form = ReportForm(place=self.place, user=self.user, kind="ELEVATOR")
        self.assertNotIn("facility_available", form.fields)
        self.assertNotIn("facility_braille", form.fields)
        self.assertIn("facility_wheelchair", [f.name for f in form.observation_fields])

        report = self.proposal("ELEVATOR")  # 꺼진 항목 값을 보내도 500 없이 나머지만 저장
        saved = set(report.values.values_list("field_id", flat=True))
        self.assertEqual(saved, set(SAMPLES["ELEVATOR"]) - {"facility_available", "facility_braille"})

    def test_inactive_entrance_definition_is_removed_from_entrance_form(self):
        FieldDefinition.objects.filter(key="step_count").update(is_active=False)
        form = ReportForm(place=self.place, user=self.user)
        self.assertNotIn("step_count", form.fields)
        report = self.proposal("ENTRANCE")
        self.assertNotIn("step_count", set(report.values.values_list("field_id", flat=True)))

    def test_ops_place_form_locks_inactive_definitions(self):
        from ops.forms import PlaceForm

        FieldDefinition.objects.filter(key="has_ramp").update(is_active=False)
        form = PlaceForm()
        self.assertTrue(form.fields["has_ramp"].disabled)
        self.assertIn("사용 중지", form.fields["has_ramp"].label)
        self.assertFalse(form.fields["step_height_cm"].disabled)
        form.cleaned_data = {"has_ramp": "true", "step_height_cm": Decimal("2")}
        self.assertEqual(form.values_for(["has_ramp", "step_height_cm"]), {"step_height_cm": Decimal("2")})
