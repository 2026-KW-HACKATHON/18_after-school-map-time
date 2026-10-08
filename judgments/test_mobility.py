from copy import deepcopy
from decimal import Decimal

from django.core.exceptions import ValidationError

from places.models import AccessFacility, Building, Entrance
from reports.models import AccessibilityValue, Report
from .engine import judge, judge_profiles
from .mobility import catalogue, default_settings, merged_constraints, normalize_settings, profile_key, requirements
from .models import ConditionProfile, Judgment, Outcome
from .tests import JudgmentTestBase


class MobilityTests(JudgmentTestBase):
    def settings(self, key="WHEELCHAIR", **overrides):
        data = default_settings()
        data["selected"] = [key]
        data["overrides"] = {key: overrides} if overrides else {}
        return normalize_settings(data)

    def personal(self, data):
        return judge_profiles(self.place, requirements(data))

    def facility_values(self, kind, owner=None, **values):
        target = AccessFacility.objects.create(kind=kind, name=kind, **(owner or {"place": self.place}))
        report = Report.objects.create(source=Report.Source.TEAM_SURVEY, status=Report.Status.VERIFIED, facility=target)
        for key, raw in values.items():
            value = AccessibilityValue(report=report, field_id=key)
            value.set_value(raw)
            value.save()
        return target

    def test_original_four_profiles_match_unmodified_engine(self):
        for values in ({}, {"step_height_cm": 1, "has_ramp": False, "door_width_cm": 90, "step_count": 0},
                       {"step_height_cm": 7, "has_ramp": True, "door_width_cm": 70, "step_count": 0},
                       {"step_height_cm": 30, "has_ramp": False, "door_width_cm": 90, "step_count": 4}):
            self.values(self.door, **values)
            for profile in ConditionProfile.objects.filter(is_active=True):
                with self.subTest(profile=profile.key, values=values):
                    self.assertEqual(self.personal(self.settings(profile.key)).outcome, judge(self.place, profile).outcome)

    def test_new_presets_are_recommendations_not_demographic_rules(self):
        meta = catalogue()
        for preset in (p for p in meta["presets"] if p["key"] in ("LIMITED_WALKING", "WITH_CHILD", "ASSISTED_COMPANION")):
            self.assertIn("recommendation", preset)
            self.assertEqual(preset["defaults"]["max_step_height_cm"], "2")
        self.assertEqual(profile_key("WITH_CHILD", {"WITH_CHILD": "CRUTCH"}), "CRUTCH")
        self.assertEqual(profile_key("ASSISTED_COMPANION", {"ASSISTED_COMPANION": "LIMITED_WALKING"}), "WALKER")

    def test_custom_threshold_changes_result_without_writing_shared_data(self):
        self.values(self.door, step_height_cm=3, door_width_cm=90, has_ramp=False, step_count=0)
        self.assertEqual(self.personal(self.settings()).outcome, Outcome.DIFFICULT)
        self.assertEqual(self.personal(self.settings(max_step_height_cm=4)).outcome, Outcome.ACCESSIBLE)
        self.assertEqual(judge(self.place, self.wheelchair).outcome, Outcome.DIFFICULT)
        self.assertEqual(Judgment.objects.filter(place=self.place).count(), 0)

    def test_unified_companion_has_no_forced_profile_or_numeric_defaults(self):
        p = next(p for p in catalogue()["presets"] if p["key"] == "COMPANION")
        self.assertEqual(p["label"], "동반자/보호자")
        self.assertIsNone(p["profile"])
        self.assertEqual(p["fields"], [])
        self.assertTrue(all(v is None for v in p["defaults"].values()))
        raw=default_settings(); raw["selected"]=["COMPANION"]
        with self.assertRaisesMessage(ValidationError,"동반자의 실제 이동 조건"):
            normalize_settings(raw)

    def test_unified_companion_can_choose_each_actual_condition_without_changing_rules(self):
        self.values(self.door, step_height_cm=7, step_count=2, has_ramp=False, door_width_cm=90)
        for key in ("WHEELCHAIR","STROLLER","WALKER","CRUTCH","LIMITED_WALKING"):
            raw=default_settings(); raw["selected"]=["COMPANION"]; raw["companions"]={"COMPANION":key}
            data=normalize_settings(raw)
            actual=ConditionProfile.objects.get(key="WALKER" if key=="LIMITED_WALKING" else key)
            self.assertEqual(self.personal(data).outcome,judge(self.place,actual).outcome)

    def test_legacy_companion_settings_and_two_people_keep_original_values(self):
        raw=default_settings(); raw["selected"]=["WITH_CHILD","ASSISTED_COMPANION"]
        raw["companions"]={"WITH_CHILD":"STROLLER","ASSISTED_COMPANION":"CRUTCH"}
        raw["overrides"]={"WITH_CHILD":{"max_step_height_cm":"5","min_door_width_cm":"80"},
                          "ASSISTED_COMPANION":{"max_step_height_cm":"1","can_use_stairs":False}}
        before=deepcopy(raw); clean=normalize_settings(raw)
        self.assertEqual(clean,raw); self.assertEqual(raw,before)
        self.assertEqual(len(requirements(clean)),2)
        self.assertEqual(merged_constraints(clean)["max_step_height_cm"],"1")
        self.assertFalse(merged_constraints(clean)["can_use_stairs"])

    def test_legacy_missing_actual_choice_keeps_historical_profile(self):
        for key,actual in (("WITH_CHILD","STROLLER"),("ASSISTED_COMPANION","WHEELCHAIR")):
            data=self.settings(key,max_step_height_cm=4)
            self.assertEqual(requirements(data)[0][0].key,actual)
            self.assertEqual(data["overrides"][key]["max_step_height_cm"],"4")

    def test_unified_companion_override_and_multiple_merge_use_same_domain(self):
        raw=default_settings();raw["selected"]=["WHEELCHAIR","COMPANION"]
        raw["companions"]={"COMPANION":"CRUTCH"}
        raw["overrides"]={"WHEELCHAIR":{"max_step_height_cm":"4","min_door_width_cm":"90"},
                          "COMPANION":{"max_step_height_cm":"1","can_use_stairs":False}}
        clean=normalize_settings(raw);before=deepcopy(clean)
        self.values(self.door,step_height_cm=3,step_count=0,door_width_cm=95,has_ramp=False)
        self.assertEqual(self.personal(clean).outcome,Outcome.DIFFICULT)
        self.assertEqual(merged_constraints(clean)["max_step_height_cm"],"1")
        self.assertEqual(clean,before)

    def test_threshold_4_does_not_allow_7_but_other_entrance_can(self):
        self.values(self.door, step_height_cm=7, door_width_cm=90, has_ramp=False)
        state = self.settings(max_step_height_cm=4)
        self.assertEqual(self.personal(state).outcome, Outcome.DIFFICULT)
        other = Entrance.objects.create(place=self.place, name="다른 입구")
        self.values(other, step_height_cm=1, door_width_cm=90, has_ramp=False)
        self.assertEqual(self.personal(state).outcome, Outcome.ACCESSIBLE)

    def test_minimum_width_and_missing_width(self):
        self.values(self.door, step_height_cm=1, door_width_cm=75, has_ramp=False)
        self.assertEqual(self.personal(self.settings(min_door_width_cm=70)).outcome, Outcome.ACCESSIBLE)
        self.assertEqual(self.personal(self.settings(min_door_width_cm=80)).outcome, Outcome.DIFFICULT)
        self.values(self.door, door_width_cm=90)
        self.assertEqual(self.personal(self.settings(min_door_width_cm=90)).outcome, Outcome.ACCESSIBLE)
        AccessibilityValue.objects.filter(report__entrance=self.door, field_id="door_width_cm").delete()
        self.assertEqual(self.personal(self.settings(min_door_width_cm=90)).outcome, Outcome.UNKNOWN)

    def test_numeric_boundaries_and_invalid_types(self):
        for key, low, high in (("max_step_height_cm", 0, 500), ("min_door_width_cm", 0, 1000), ("max_slope_deg", 0, 90)):
            for value in (low, high, Decimal("0.1")):
                with self.subTest(key=key, value=value):
                    self.assertIn(key, self.settings(**{key: value})["overrides"]["WHEELCHAIR"])
            for value in (low - 1, high + 1, "NaN", "Infinity", "abc", True, "", "0.11"):
                with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                    self.settings(**{key: value})

    def test_invalid_boolean_and_unknown_field(self):
        for value in ("perhaps", "false", 0, 1, [], {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.settings(can_use_stairs=value)
        with self.assertRaises(ValidationError):
            self.settings(unknown=1)
        with self.assertRaises(ValidationError):
            self.settings("CRUTCH", min_door_width_cm=70)

    def test_reset_and_preset_change_do_not_mix_overrides(self):
        data = self.settings(max_step_height_cm=4)
        data["selected"] = ["STROLLER"]
        normalized = normalize_settings(data)
        self.assertEqual(normalized["overrides"]["WHEELCHAIR"]["max_step_height_cm"], "4")
        self.assertEqual(self.personal(normalized).outcome, judge(self.place, self.stroller).outcome)
        normalized["selected"] = ["WHEELCHAIR"]
        normalized["overrides"]["WHEELCHAIR"] = {"max_step_height_cm": None}
        self.assertEqual(normalize_settings(normalized)["overrides"], {})

    def test_multi_merge_preserves_original_settings(self):
        data = self.settings(max_step_height_cm=4, min_door_width_cm=85, can_use_stairs=True)
        data["selected"].append("STROLLER")
        data["overrides"]["STROLLER"] = {"max_step_height_cm": "1", "min_door_width_cm": "90", "can_use_stairs": False}
        original = deepcopy(data)
        merged = merged_constraints(data)
        self.assertEqual(merged["max_step_height_cm"], "1")
        self.assertEqual(merged["min_door_width_cm"], "90")
        self.assertIs(merged["can_use_stairs"], False)
        self.assertEqual(data, original)

    def test_people_must_share_same_route(self):
        self.values(self.door, step_height_cm=1, door_width_cm=70, has_ramp=False, step_count=0)
        other = Entrance.objects.create(place=self.place, name="넓지만 높은 입구")
        self.values(other, step_height_cm=7, door_width_cm=90, has_ramp=False, step_count=2)
        data = self.settings("WHEELCHAIR", max_step_height_cm=10)
        data["selected"].append("STROLLER")
        self.assertEqual(self.personal(self.settings("WHEELCHAIR", max_step_height_cm=10)).outcome, Outcome.ACCESSIBLE)
        self.assertEqual(self.personal(self.settings("STROLLER")).outcome, Outcome.ACCESSIBLE)
        self.assertEqual(self.personal(data).outcome, Outcome.DIFFICULT)

    def test_companion_is_separate_from_own_wheelchair_values(self):
        data = self.settings(max_step_height_cm=4)
        data["selected"].append("ASSISTED_COMPANION")
        data["companions"]["ASSISTED_COMPANION"] = "CRUTCH"
        data["overrides"]["ASSISTED_COMPANION"] = {"max_step_height_cm": "1"}
        original = deepcopy(data)
        self.assertEqual([p.key for p, _ in requirements(data)], ["WHEELCHAIR", "CRUTCH"])
        self.personal(data)
        self.assertEqual(data, original)

    def test_missing_required_facility_is_unknown_not_absent(self):
        self.values(self.door, step_height_cm=1, door_width_cm=90, has_ramp=False)
        self.assertEqual(self.personal(self.settings(needs_accessible_toilet=True)).outcome, Outcome.UNKNOWN)
        self.values(self.place, accessible_toilet=False)
        self.assertEqual(self.personal(self.settings(needs_accessible_toilet=True)).outcome, Outcome.DIFFICULT)
        self.facility_values("TOILET", facility_available=True, facility_wheelchair=True)
        self.assertEqual(self.personal(self.settings(needs_accessible_toilet=True)).outcome, Outcome.ACCESSIBLE)

    def test_preference_does_not_block_and_uncollected_passage_is_unknown(self):
        self.values(self.door, step_height_cm=1, door_width_cm=90, has_ramp=False)
        self.assertEqual(self.personal(self.settings("LIMITED_WALKING", prefers_rest_seat=True)).outcome, Outcome.ACCESSIBLE)
        self.assertEqual(self.personal(self.settings("WALKER", min_passage_width_cm=70)).outcome, Outcome.UNKNOWN)

    def test_ramp_measurement_without_entrance_link_not_assumed(self):
        self.values(self.door, step_height_cm=7, has_ramp=True, door_width_cm=90)
        self.facility_values("RAMP", facility_available=True, facility_slope_deg=3)
        self.assertEqual(self.personal(self.settings(max_slope_deg=5)).outcome, Outcome.UNKNOWN)

    def test_handrail_required_on_stairs_not_flat(self):
        self.values(self.door, step_height_cm=1, has_ramp=False, step_count=0)
        self.assertEqual(self.personal(self.settings("CRUTCH", needs_handrail=True)).outcome, Outcome.ACCESSIBLE)
        self.values(self.door, step_height_cm=3, step_count=1)
        self.assertEqual(self.personal(self.settings("CRUTCH", needs_handrail=True)).outcome, Outcome.UNKNOWN)

    def test_stairs_disallowed_uses_alternative_ramp(self):
        self.values(self.door, step_height_cm=1, step_count=1, has_ramp=False, door_width_cm=90)
        self.assertEqual(self.personal(self.settings(can_use_stairs=False)).outcome, Outcome.DIFFICULT)
        self.values(self.door, has_ramp=True)
        self.assertEqual(self.personal(self.settings(can_use_stairs=False)).outcome, Outcome.ACCESSIBLE)

    def test_registered_elevator_requires_known_connection(self):
        self.place.floor = 2
        self.place.building = Building.objects.create(region=self.region, name="건물", address="테스트", lat=37.62, lng=127.05)
        self.place.save()
        self.values(self.door, step_height_cm=1, door_width_cm=90, has_ramp=False)
        state = self.settings(needs_elevator=True)
        elevator = self.facility_values("ELEVATOR", owner={"building": self.place.building}, facility_available=True)
        self.assertEqual(self.personal(state).outcome, Outcome.UNKNOWN)
        report = Report.objects.create(facility=elevator, source=Report.Source.TEAM_SURVEY, status=Report.Status.VERIFIED)
        value = AccessibilityValue(report=report, field_id="facility_connected_floors")
        value.set_value("1층 → 2층")
        value.save()
        self.assertEqual(self.personal(state).outcome, Outcome.ACCESSIBLE)

    def test_unknown_preset_or_companion_is_validation_error(self):
        data = default_settings()
        for mutate in (lambda d: d.update(selected=["bad"]), lambda d: d.update(selected=[[]]),
                       lambda d: d.update(companions={"WITH_CHILD": []}), lambda d: d.update(version=True)):
            broken = deepcopy(data)
            mutate(broken)
            with self.assertRaises(ValidationError):
                normalize_settings(broken)

    def test_explicit_crutch_threshold_also_limits_conditional_stairs_rule(self):
        self.values(self.door, step_height_cm=7, step_count=1, has_ramp=False)
        self.assertEqual(self.personal(self.settings("CRUTCH")).outcome, Outcome.CONDITIONAL)
        self.assertEqual(self.personal(self.settings("CRUTCH", max_step_height_cm=4)).outcome, Outcome.DIFFICULT)

    def test_new_recommendations_match_underlying_rules_until_edited(self):
        self.values(self.door, step_height_cm=7, step_count=2, has_ramp=False, door_width_cm=90)
        for key, profile in (("LIMITED_WALKING", ConditionProfile.objects.get(key="WALKER")), ("WITH_CHILD", self.stroller), ("ASSISTED_COMPANION", self.wheelchair)):
            with self.subTest(key=key):
                self.assertEqual(self.personal(self.settings(key)).outcome, judge(self.place, profile).outcome)
        data = self.settings("WITH_CHILD")
        data["companions"] = {"WITH_CHILD": "CRUTCH"}
        self.assertEqual(self.personal(data).outcome, Outcome.CONDITIONAL)

    def test_no_elevator_required_needs_confirmed_stairs_route(self):
        self.place.floor = 2
        self.place.building = Building.objects.create(region=self.region, name="계단 건물", address="테스트", lat=37.62, lng=127.05)
        self.place.save()
        self.values(self.door, step_height_cm=1, door_width_cm=90, step_count=0, has_ramp=False)
        state = self.settings(needs_elevator=False, can_use_stairs=True)
        self.assertEqual(self.personal(state).outcome, Outcome.UNKNOWN)
        self.facility_values("STAIRS", owner={"building": self.place.building}, facility_available=True, facility_connected_floors="1층 → 2층")
        self.assertEqual(self.personal(state).outcome, Outcome.ACCESSIBLE)

    def test_missing_handrail_route_information_is_unknown(self):
        self.values(self.door, step_height_cm=1, has_ramp=False)
        self.assertEqual(self.personal(self.settings("CRUTCH", needs_handrail=True)).outcome, Outcome.UNKNOWN)

    def test_stairs_disallowed_keeps_verified_portable_ramp_help_route(self):
        self.values(self.door, step_height_cm=7, step_count=1, has_ramp=False, door_width_cm=90)
        self.values(self.place, portable_ramp=True, portable_ramp_length_cm=100, assistance_offered=True)
        self.assertEqual(self.personal(self.settings(can_use_stairs=False, max_step_height_cm=4)).outcome, Outcome.CONDITIONAL)
        self.assertEqual(self.personal(self.settings(can_use_stairs=False, max_slope_deg=5)).outcome, Outcome.UNKNOWN)
