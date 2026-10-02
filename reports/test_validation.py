"""ID 요청과 Form을 거치지 않는 관측값 저장의 회귀 검사."""

from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.test_validation import INVALID_IDS
from core.validation import MAX_PK
from ops.forms import PlaceForm
from places.facilities import KIND_FIELDS, FIELD_SPECS
from places.models import AccessFacility, Building, Entrance, FieldDefinition
from places.tests import make_place, make_region
from places.validation import INTEGER_KEYS, NUMERIC_LIMITS

from .forms import ReportForm
from .models import AccessibilityValue, Report


class ReportIdValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        region = make_region("validation")
        cls.place = make_place(region, pk=123)
        cls.building = Building.objects.create(pk=123, region=region, address="검증 건물", lat=37.62, lng=127.05)
        cls.user = User.objects.create_user(username="validation")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("reports:new")

    def test_existing_ascii_ids(self):
        for key in ("place", "building"):
            with self.subTest(key=key):
                response = self.client.get(self.url, {key: "123"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context[key].pk, 123)

    def test_missing_numeric_ids_are_404(self):
        for key in ("place", "building"):
            for raw in ("1", str(MAX_PK)):
                with self.subTest(key=key, raw=raw):
                    self.assertEqual(self.client.get(self.url, {key: raw}).status_code, 404)

    def test_invalid_get_ids_are_404(self):
        for key in ("place", "building"):
            for raw in INVALID_IDS:
                if not raw:
                    continue  # 빈 값은 기존처럼 새 장소 제안
                with self.subTest(key=key, raw=raw[:25]):
                    self.assertEqual(self.client.get(self.url, {key: raw}).status_code, 404)

    def test_invalid_post_ids_are_404_without_saving(self):
        before = Report.objects.count()
        for key in ("place", "building"):
            for raw in INVALID_IDS:
                if not raw:
                    continue
                with self.subTest(key=key, raw=raw[:25]):
                    self.assertEqual(self.client.post(self.url, {key: raw, "note": "검증"}).status_code, 404)
        self.assertEqual(Report.objects.count(), before)

    def test_empty_ids_keep_new_place_flow(self):
        for query in ({}, {"place": ""}, {"building": ""}):
            response = self.client.get(self.url, query)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context["place"])
            self.assertIsNone(response.context["building"])


class AccessibilityValueValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        cls.place = make_place(make_region("numeric-validation"))
        cls.entrance = Entrance.objects.create(place=cls.place)

    def report_for(self, key):
        definition = FieldDefinition.objects.get(pk=key)
        if definition.scope == "FACILITY":
            kind = next(kind for kind, keys in KIND_FIELDS.items() if kind != "ENTRANCE" and key in keys)
            facility = AccessFacility.objects.create(place=self.place, kind=kind, name="검증 시설")
            target = {"facility": facility}
        else:
            target = {"entrance": self.entrance} if definition.scope == "ENTRANCE" else {"place": self.place}
        return Report.objects.create(source="TEAM_SURVEY", **target)

    def test_all_current_numeric_definitions_have_rules(self):
        self.assertEqual(set(FieldDefinition.objects.filter(value_type="NUMBER").values_list("pk", flat=True)), set(NUMERIC_LIMITS))

    def test_minimum_and_maximum_are_saved_directly(self):
        for key, (minimum, maximum) in NUMERIC_LIMITS.items():
            for raw in (minimum, maximum):
                with self.subTest(key=key, raw=raw):
                    value = AccessibilityValue.objects.create(report=self.report_for(key), field_id=key, value_number=raw)
                    value.refresh_from_db()
                    self.assertEqual(value.value, Decimal(str(raw)))

    def test_out_of_range_direct_create_and_full_clean(self):
        for key, (minimum, maximum) in NUMERIC_LIMITS.items():
            report = self.report_for(key)
            for raw in (minimum - 1, maximum + 1):
                with self.subTest(key=key, raw=raw):
                    with self.assertRaises(ValidationError):
                        AccessibilityValue(report=report, field_id=key, value_number=raw).full_clean()
                    with self.assertRaises(ValidationError):
                        AccessibilityValue.objects.create(report=report, field_id=key, value_number=raw)
            self.assertFalse(report.values.exists())

    def test_setter_rejects_out_of_range_and_non_finite(self):
        for raw in ("9999", "-1", "NaN", "Infinity", "-Infinity", None, ""):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                AccessibilityValue(field_id="step_height_cm").set_value(raw)

    def test_direct_save_rejects_invalid_update_and_preserves_db_value(self):
        value = AccessibilityValue.objects.create(report=self.report_for("step_height_cm"), field_id="step_height_cm", value_number=2)
        value.value_number = 9999
        with self.assertRaises(ValidationError):
            value.save(update_fields=["value_number"])
        value.refresh_from_db()
        self.assertEqual(value.value_number, Decimal("2"))
        value.value_number = 500
        value.save(update_fields=["value_number"])
        value.refresh_from_db()
        self.assertEqual(value.value_number, Decimal("500"))

    def test_count_fields_reject_fractions(self):
        for key in INTEGER_KEYS:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                AccessibilityValue.objects.create(report=self.report_for(key), field_id=key, value_number="1.5")

    def test_valid_boolean_tokens_keep_compatibility(self):
        true_values = (True, 1, "true", "1", "yes", "y", "있음", "예", " TRUE ")
        false_values = (False, 0, "false", "0", "no", "n", "없음", "아니오", "아니요", " FALSE ")
        for expected, tokens in ((True, true_values), (False, false_values)):
            for raw in tokens:
                with self.subTest(raw=raw):
                    value = AccessibilityValue(report=self.report_for("has_ramp"), field_id="has_ramp")
                    value.set_value(raw)
                    value.save()
                    value.refresh_from_db()
                    self.assertIs(value.value_bool, expected)

    def test_invalid_boolean_setter_values_raise(self):
        for raw in ("perhaps", "", "unknown", "2", 2, -1, None, [], {}):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                AccessibilityValue(field_id="has_ramp").set_value(raw)

    def test_direct_boolean_create_and_update_are_validated(self):
        report = self.report_for("has_ramp")
        with self.assertRaises(ValidationError):
            AccessibilityValue.objects.create(report=report, field_id="has_ramp", value_bool="perhaps")
        self.assertFalse(report.values.exists())
        value = AccessibilityValue.objects.create(report=report, field_id="has_ramp", value_bool=True)
        value.value_bool = "perhaps"
        with self.assertRaises(ValidationError):
            value.save()
        value.refresh_from_db()
        self.assertIs(value.value_bool, True)
        value.value_bool = False
        value.save()
        value.refresh_from_db()
        self.assertIs(value.value_bool, False)

    def test_form_and_model_numeric_boundaries_agree(self):
        fields = {key: ReportForm().fields[key] for key in ("step_height_cm", "step_count", "door_width_cm")}
        fields["portable_ramp_length_cm"] = PlaceForm().fields["portable_ramp_length_cm"]
        for kind, keys in KIND_FIELDS.items():
            if kind != "ENTRANCE":
                form = ReportForm(kind=kind)
                fields.update({key: form.fields[key] for key in keys if key in NUMERIC_LIMITS})
        self.assertEqual(set(fields), set(NUMERIC_LIMITS))
        for key, field in fields.items():
            minimum, maximum = NUMERIC_LIMITS[key]
            self.assertEqual((field.min_value, field.max_value), (minimum, maximum))
            for raw in (minimum, maximum):
                with self.subTest(key=key, raw=raw):
                    field.clean(str(raw))
                    AccessibilityValue(report=self.report_for(key), field_id=key, value_number=raw).full_clean()
            for raw in (minimum - 1, maximum + 1):
                with self.subTest(key=key, raw=raw), self.assertRaises(ValidationError):
                    field.clean(str(raw))

    def test_operator_numeric_fields_use_same_limits(self):
        fields = PlaceForm().fields
        for key in ("step_height_cm", "step_count", "door_width_cm", "portable_ramp_length_cm"):
            self.assertEqual((fields[key].min_value, fields[key].max_value), NUMERIC_LIMITS[key])
        for key, spec in FIELD_SPECS.items():
            if spec[1] == "NUMBER":
                self.assertEqual(spec[4], NUMERIC_LIMITS[key][1])
