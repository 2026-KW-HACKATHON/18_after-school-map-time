from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.test_validation import INVALID_IDS
from core.validation import MAX_PK
from places.models import Building, Entrance
from places.tests import make_place, make_region
from reports.models import Report


class OperatorIdValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        region = make_region("ops-id")
        cls.building = Building.objects.create(region=region, address="검증 건물", lat=37.62, lng=127.05)
        cls.place = make_place(region, pk=123, building=cls.building)
        cls.entrance = Entrance.objects.create(place=cls.place)
        cls.report = Report.objects.create(entrance=cls.entrance, source="USER_REPORT")
        cls.staff = User.objects.create_user(username="id-staff", is_staff=True)

    def setUp(self):
        self.client.force_login(self.staff)

    def test_invalid_report_ids_do_not_delete_or_error(self):
        for raw in (*INVALID_IDS, str(MAX_PK)):
            with self.subTest(raw=raw[:25]):
                response = self.client.post(reverse("ops:reports-delete"), {"ids": [raw], "confirm_step": "1", "confirm": "on"})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(Report.objects.filter(pk=self.report.pk).exists())

    def test_mixed_ids_keep_valid_confirmation_selection(self):
        response = self.client.post(reverse("ops:reports-delete"), {"ids": ["²", "１２３", "9" * 10000, str(self.report.pk)]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r.pk for r in response.context["reports"]], [self.report.pk])
        self.assertTrue(Report.objects.filter(pk=self.report.pk).exists())

    def test_invalid_place_ids_use_existing_fallback(self):
        url = reverse("ops:building-claim-code", args=[self.building.pk])
        for raw in (*INVALID_IDS, str(MAX_PK)):
            with self.subTest(raw=raw[:25]):
                response = self.client.post(url, {"place": raw})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("ops:places"))

    def test_valid_place_id_redirects_to_editor(self):
        response = self.client.post(reverse("ops:building-claim-code", args=[self.building.pk]), {"place": "123"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ops:place-edit", args=[self.place.pk]))

    def test_valid_but_missing_or_unrelated_place_uses_fallback(self):
        other = make_place(self.place.region)
        for raw in (str(MAX_PK), str(other.pk)):
            response = self.client.post(reverse("ops:building-claim-code", args=[self.building.pk]), {"place": raw})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("ops:places"))
