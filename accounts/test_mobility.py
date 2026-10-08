import json
from copy import deepcopy
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase

from judgments.mobility import default_settings
from places.tests import make_place, make_region
from .models import MobilityPreference


class MobilityAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())
        cls.user = get_user_model().objects.create_user(username="mobility-test-member")
        cls.other = get_user_model().objects.create_user(username="mobility-test-other")
        cls.region = make_region("mobility-api-test")
        cls.place = make_place(cls.region, "개인화 테스트 장소")

    def setUp(self):
        self.data = default_settings()
        self.data["overrides"] = {"WHEELCHAIR": {"max_step_height_cm": "4"}}

    def put(self, data=...):
        return self.client.put("/api/v1/mobility/preferences/", json.dumps(self.data if data is ... else data), content_type="application/json")

    def evaluate(self, **kwargs):
        return self.client.post("/api/v1/mobility/places/", json.dumps({"settings": self.data, "region": self.region.code, **kwargs}), content_type="application/json")

    def test_guest_catalogue_and_evaluation_do_not_save(self):
        response = self.client.get("/api/v1/mobility/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["presets"]), 7)
        self.assertFalse(response.json()["authenticated"])
        self.assertEqual(self.evaluate().status_code, 200)
        self.assertFalse(MobilityPreference.objects.exists())

    def test_guest_cannot_read_or_write_member_settings(self):
        self.assertEqual(self.put().status_code, 403)
        self.assertEqual(self.client.get("/api/v1/mobility/preferences/").status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/mobility/preferences/").status_code, 403)

    def test_member_roundtrip_reset_and_other_user_isolation(self):
        self.client.force_login(self.user)
        self.assertEqual(self.put().status_code, 200)
        response = self.client.get("/api/v1/mobility/preferences/")
        self.assertEqual(response.json()["settings"]["overrides"], self.data["overrides"])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/api/v1/mobility/preferences/").json()["settings"]["overrides"], {})
        self.client.delete("/api/v1/mobility/preferences/")
        self.assertTrue(MobilityPreference.objects.filter(user=self.user).exists())
        self.client.force_login(self.user)
        self.assertEqual(self.client.delete("/api/v1/mobility/preferences/").json()["settings"]["overrides"], {})
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_wrong_user_id_not_accepted(self):
        self.client.force_login(self.user)
        data = deepcopy(self.data)
        data["user"] = self.other.pk
        self.assertEqual(self.put(data).status_code, 400)
        self.assertFalse(MobilityPreference.objects.exists())

    def test_direct_model_validation_and_invalid_update_preserves_row(self):
        preference = MobilityPreference.objects.create(user=self.user, data=self.data)
        preference.data["overrides"]["WHEELCHAIR"]["can_use_stairs"] = "perhaps"
        with self.assertRaises(ValidationError):
            preference.save()
        preference.refresh_from_db()
        self.assertEqual(preference.data["overrides"], self.data["overrides"])

    def test_damaged_saved_settings_and_changed_rule_version(self):
        preference = MobilityPreference.objects.create(user=self.user, data=self.data)
        self.client.force_login(self.user)
        MobilityPreference.objects.filter(user=self.user).update(data={"version": 999})  # 손상된 저장값을 test DB에서만 재현
        response = self.client.get("/api/v1/mobility/").json()
        self.assertEqual(response["settings"]["overrides"], {})
        self.assertTrue(response["warning"])
        self.assertEqual(MobilityPreference.objects.get(user=self.user).data, {"version": 999})
        data = deepcopy(self.data)
        data["rule_version"] = 123
        MobilityPreference.objects.filter(user=self.user).update(data=data)
        response = self.client.get("/api/v1/mobility/").json()
        self.assertEqual(response["settings"]["overrides"], self.data["overrides"])
        self.assertIn("기본 판정 기준", response["warning"])

    def test_invalid_json_data_and_numeric_inputs(self):
        self.client.force_login(self.user)
        for value in ([], None, {"version": 1}, {**self.data, "selected": ["bad"]},
                      {**self.data, "overrides": {"WHEELCHAIR": {"max_step_height_cm": 9999}}}):
            with self.subTest(value=value):
                self.assertEqual(self.put(value).status_code, 400)
        self.assertFalse(MobilityPreference.objects.exists())

    def test_evaluation_ids_region_search_and_unknown_information(self):
        response = self.evaluate(place_ids=[self.place.pk])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["judgment"]["code"], "UNKNOWN")
        for value in ("²", "１２３", "-1", " 1", "9" * 5000, {}, True):
            with self.subTest(value=str(value)[:25]):
                self.assertEqual(self.evaluate(place_ids=[value]).status_code, 400)
        self.assertEqual(self.evaluate(place_ids=[999999]).status_code, 404)
        self.assertEqual(self.evaluate(region="missing-region").status_code, 404)
        self.assertEqual(self.evaluate(q="개인화").json()["count"], 1)
        self.assertEqual(self.evaluate(q="존재하지 않는 이름").json()["count"], 0)
        self.assertEqual(self.evaluate(q="\x00").status_code, 400)
        self.assertEqual(self.evaluate(all=False).json()["count"], 0)

    def test_member_csrf_and_logout_does_not_expose_settings(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.put("/api/v1/mobility/preferences/", json.dumps(self.data), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        MobilityPreference.objects.create(user=self.user, data=self.data)
        client.logout()
        self.assertEqual(client.get("/api/v1/mobility/").json()["settings"]["overrides"], {})

    def test_existing_public_api_response_remains_compatible(self):
        response = self.client.get(f"/api/v1/places/?region={self.region.code}&all=1&profile=WHEELCHAIR")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"], "WHEELCHAIR")
        self.assertNotIn("personalized", response.json()["results"][0]["judgment"])

    def test_only_selected_preferences_apply_and_search_keeps_information_summary(self):
        self.data["overrides"]["LIMITED_WALKING"] = {"prefers_rest_seat": True}
        response = self.evaluate(q="개인화").json()
        self.assertEqual(response["preferences"], [])
        self.assertIn("facts", response["results"][0])
        self.assertIn("last_checked", response["results"][0])
        self.data["selected"] = ["LIMITED_WALKING"]
        self.assertTrue(self.evaluate().json()["preferences"])
