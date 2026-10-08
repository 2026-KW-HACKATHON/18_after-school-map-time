from datetime import timedelta

from accounts.models import MobilityPreference
from places.models import AccessFacility, Building, Entrance, FieldDefinition
from reports.models import AccessibilityValue, Report

from .models import Judgment
from .place_reference import place_reference
from .tests import JudgmentTestBase


class PlaceReferenceTests(JudgmentTestBase):
    def url(self, pk=None):
        return f"/api/v1/mobility/places/{self.place.pk if pk is None else pk}/reference/"

    def test_confirmed_numbers_and_dates_without_settings_or_fact_writes(self):
        report = self.values(self.door, step_height_cm="3.0", door_width_cm=90, step_count=0, has_ramp=False)
        counts = [m.objects.count() for m in (Report, AccessibilityValue, Judgment, MobilityPreference)]
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        route = response.json()["routes"][0]
        self.assertEqual(route["values"], {"max_step_height_cm": "3", "min_door_width_cm": "90"})
        self.assertEqual(route["entrances"][0]["fields"][0]["checked_at"], report.observed_at.isoformat())
        self.assertNotIn("can_use_stairs", route["values"])
        self.assertEqual(counts, [m.objects.count() for m in (Report, AccessibilityValue, Judgment, MobilityPreference)])

    def test_latest_verified_observation_wins_not_latest_creation(self):
        newer = self.values(self.door, step_height_cm=4, door_width_cm=80)
        older = self.values(self.door, step_height_cm=1, door_width_cm=90)
        Report.objects.filter(pk=older.pk).update(observed_at=newer.observed_at - timedelta(days=1))
        self.assertEqual(place_reference(self.place)["routes"][0]["values"], {"max_step_height_cm": "4", "min_door_width_cm": "80"})

    def test_pending_only_or_new_pending_measurement_is_not_proposed(self):
        self.values(self.door, status=Report.Status.PENDING, step_height_cm=7)
        self.assertEqual(place_reference(self.place)["routes"][0]["values"], {})
        self.values(self.door, step_height_cm=3, door_width_cm=90)
        route = place_reference(self.place)["routes"][0]
        self.assertEqual(route["values"], {"min_door_width_cm": "90"})
        self.assertTrue(route["entrances"][0]["fields"][0]["pending"])
        self.assertTrue(route["warnings"])

    def test_inactive_definition_does_not_supply_reference_value(self):
        self.values(self.door, step_height_cm=3, door_width_cm=90)
        FieldDefinition.objects.filter(pk="step_height_cm").update(is_active=False)
        route = place_reference(self.place)["routes"][0]
        self.assertEqual(route["values"], {"min_door_width_cm": "90"})
        self.assertNotIn("step_height_cm", [f["key"] for f in route["entrances"][0]["fields"]])
        self.values(self.door, entrance_available=False)
        FieldDefinition.objects.filter(pk="entrance_available").update(is_active=False)
        route = place_reference(self.place)["routes"][0]
        self.assertFalse(route["unavailable"])
        self.assertEqual(route["values"], {"min_door_width_cm": "90"})

    def test_alternative_entrances_are_not_mixed(self):
        self.values(self.door, step_height_cm=1, door_width_cm=70)
        other = Entrance.objects.create(place=self.place, name="다른 문")
        self.values(other, step_height_cm=7, door_width_cm=90)
        routes = place_reference(self.place)["routes"]
        self.assertEqual(len(routes), 2)
        self.assertEqual({r["id"]: r["values"] for r in routes}, {
            f"entrance:{self.door.pk}": {"max_step_height_cm": "1", "min_door_width_cm": "70"},
            f"entrance:{other.pk}": {"max_step_height_cm": "7", "min_door_width_cm": "90"},
        })

    def building(self):
        self.place.floor = 2
        self.place.building = Building.objects.create(region=self.region, name="공용 건물", address="주소", lat=37.62, lng=127.05)
        self.place.save()
        return Entrance.objects.create(building=self.place.building, name="건물 문")

    def test_common_and_store_entrances_use_same_complete_route(self):
        common = self.building()
        self.values(common, step_height_cm=5, door_width_cm=85)
        self.values(self.door, step_height_cm=2, door_width_cm=80)
        route = place_reference(self.place)["routes"][0]
        self.assertFalse(route["incomplete"])
        self.assertEqual(route["values"], {"max_step_height_cm": "5", "min_door_width_cm": "80"})
        self.assertEqual(route["id"], f"entrance:{common.pk}/floor:2/entrance:{self.door.pk}")
        self.assertEqual([e["entrance_id"] for e in route["entrances"]], [common.pk, self.door.pk])

    def test_missing_common_measurement_is_not_substituted_with_store_value(self):
        common = self.building()
        self.values(common, step_height_cm=5)
        self.values(self.door, step_height_cm=2, door_width_cm=80)
        self.assertEqual(place_reference(self.place)["routes"][0]["values"], {"max_step_height_cm": "5"})

    def test_incomplete_upper_floor_route_does_not_propose_global_constraints(self):
        common = self.building()
        self.values(self.door, step_height_cm=2, door_width_cm=80)
        common.delete()
        route = place_reference(self.place)["routes"][0]
        self.assertTrue(route["incomplete"])
        self.assertEqual(route["values"], {})
        self.assertTrue(route["warnings"])
        self.place.building = None
        self.place.save()
        self.assertTrue(place_reference(self.place)["routes"][0]["incomplete"])

    def test_missing_store_entrance_or_all_entrances_is_empty_or_incomplete(self):
        self.door.delete()
        self.assertEqual(place_reference(self.place)["routes"], [])
        common = self.building()
        self.values(common, step_height_cm=2, door_width_cm=80)
        route = place_reference(self.place)["routes"][0]
        self.assertTrue(route["incomplete"])
        self.assertEqual(route["values"], {})

    def test_current_unavailable_entrance_does_not_propose_values(self):
        self.values(self.door, step_height_cm=2, door_width_cm=80, entrance_available=False)
        route = place_reference(self.place)["routes"][0]
        self.assertTrue(route["unavailable"])
        self.assertEqual(route["values"], {})

    def test_ramp_warnings_do_not_infer_slope_or_personal_boolean(self):
        self.values(self.door, step_height_cm=7, door_width_cm=80, has_ramp=True)
        AccessFacility.objects.create(place=self.place, kind="RAMP", name="위치 연결 없는 경사로")
        route = place_reference(self.place)["routes"][0]
        self.assertTrue(route["warnings"])
        self.assertEqual(set(route["values"]), {"max_step_height_cm", "min_door_width_cm"})

    def test_precision_not_rounded_and_zero_is_preserved(self):
        self.values(self.door, step_height_cm="3.25", door_width_cm=80)
        self.assertNotIn("max_step_height_cm", place_reference(self.place)["routes"][0]["values"])
        self.values(self.door, step_height_cm=0)
        self.assertEqual(place_reference(self.place)["routes"][0]["values"]["max_step_height_cm"], "0")

    def test_invalid_legacy_number_not_copied_or_rewritten(self):
        report = self.values(self.door, step_height_cm=3, door_width_cm=80)
        AccessibilityValue.objects.filter(report=report, field_id="step_height_cm").update(value_number=9999)
        self.assertNotIn("max_step_height_cm", place_reference(self.place)["routes"][0]["values"])
        self.assertEqual(AccessibilityValue.objects.get(report=report, field_id="step_height_cm").value_number, 9999)

    def test_bad_ids_nonexistent_closed_inactive_and_method_handling(self):
        for pk in ("abc", "²", "１２３", "-1", " 1", "0", "9" * 5000):
            with self.subTest(pk=pk[:20]):
                response = self.client.get(self.url(pk))
                self.assertEqual(response.status_code, 400)
                self.assertIn("detail", response.json())
        self.assertEqual(self.client.get(self.url("999999")).status_code, 404)
        self.assertEqual(self.client.post(self.url()).status_code, 405)
        self.place.is_closed = True
        self.place.save()
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.place.is_closed = False
        self.place.save()
        self.region.is_active = False
        self.region.save()
        self.assertEqual(self.client.get(self.url()).status_code, 404)
