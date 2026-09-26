from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_ok(self):
        res = self.client.get(reverse("core:health"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "db": True})

    def test_health_db_down_returns_503(self):
        # DB 연결이 실패하는 상황을 흉내 냄
        with patch.object(connection, "cursor", side_effect=Exception("db down")):
            res = self.client.get(reverse("core:health"))
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["db"], False)


class HomeTests(TestCase):
    def test_home(self):
        res = self.client.get(reverse("core:home"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "턱없네")
