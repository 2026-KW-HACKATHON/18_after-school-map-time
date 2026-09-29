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


class StaticStorageTests(TestCase):
    def test_uncollected_file_falls_back_to_original_name(self):
        # 배포 중 collectstatic 전에 새 파일을 요청해도 500 대신 원래 이름 (config/storage.py)
        import tempfile

        from config.storage import CacheBustingStaticStorage

        with tempfile.TemporaryDirectory() as root:
            storage = CacheBustingStaticStorage(location=root, base_url="/static/")
            self.assertEqual(storage.url("js/new.js"), "/static/js/new.js")
