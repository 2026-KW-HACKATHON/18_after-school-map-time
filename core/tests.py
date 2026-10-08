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
    def test_home_goes_to_map(self):
        res = self.client.get(reverse("core:home"))
        self.assertRedirects(res, reverse("places:map"))


class StaticStorageTests(TestCase):
    def test_static_collection_publishes_valid_manifest_and_hashed_css(self):
        import json
        import tempfile
        from pathlib import Path

        from config.storage import CacheBustingStaticStorage

        with tempfile.TemporaryDirectory() as root, self.settings(DEBUG=False):
            Path(root, "common.css").write_text("body { color: black; }", encoding="utf8")
            storage = CacheBustingStaticStorage(location=root, base_url="/static/")
            processed = list(storage.post_process({"common.css": (storage, "common.css")}))
            self.assertFalse(any(isinstance(result[2], Exception) for result in processed))
            manifest = json.loads(Path(root, "staticfiles.json").read_text(encoding="utf8"))
            self.assertEqual(manifest["version"], "1.1")
            hashed = manifest["paths"]["common.css"]
            self.assertNotEqual(hashed, "common.css")
            self.assertTrue(Path(root, hashed).exists())
            worker = CacheBustingStaticStorage(location=root, base_url="/static/")
            self.assertEqual(worker.url("common.css"), "/static/" + hashed)

    def test_existing_workers_refresh_manifest_after_static_collection(self):
        import json
        import tempfile
        from pathlib import Path

        from config.storage import CacheBustingStaticStorage

        with tempfile.TemporaryDirectory() as root, self.settings(DEBUG=False):
            manifest = Path(root) / "staticfiles.json"
            def publish(name):
                # 실제 collectstatic의 manifest 형식, 새 해시 파일은 이전 파일을 지우지 않는다.
                Path(root, name).write_text("body {}", encoding="utf8")
                manifest.write_text(json.dumps({"version": "1.1", "hash": name,
                                               "paths": {"common.css": name}}), encoding="utf8")
            publish("common.old.css")
            workers = [CacheBustingStaticStorage(location=root, base_url="/static/") for _ in range(3)]
            self.assertTrue(all(w.url("common.css") == "/static/common.old.css" for w in workers))
            publish("common.updated.css")
            self.assertTrue(all(w.url("common.css") == "/static/common.updated.css" for w in workers))
            self.assertTrue(Path(root, "common.old.css").exists())  # 뒤로가기한 이전 HTML도 유효
            cold_worker = CacheBustingStaticStorage(location=root, base_url="/static/")
            self.assertEqual(cold_worker.url("common.css"), "/static/common.updated.css")

    def test_worker_started_before_manifest_exists_recovers_and_rollback_refreshes(self):
        import json
        import tempfile
        from pathlib import Path

        from config.storage import CacheBustingStaticStorage

        with tempfile.TemporaryDirectory() as root, self.settings(DEBUG=False):
            storage = CacheBustingStaticStorage(location=root, base_url="/static/")
            self.assertEqual(storage.url("js/app.js"), "/static/js/app.js")
            manifest = Path(root) / "staticfiles.json"
            for hashed in ("js/app.current.js", "js/app.previous-release.js"):
                manifest.write_text(json.dumps({"version": "1.1", "hash": hashed,
                                               "paths": {"js/app.js": hashed}}), encoding="utf8")
                self.assertEqual(storage.url("js/app.js"), "/static/" + hashed)

    def test_uncollected_file_falls_back_to_original_name(self):
        # 배포 중 collectstatic 전에 새 파일을 요청해도 500 대신 원래 이름 (config/storage.py)
        import tempfile

        from config.storage import CacheBustingStaticStorage

        with tempfile.TemporaryDirectory() as root:
            storage = CacheBustingStaticStorage(location=root, base_url="/static/")
            self.assertEqual(storage.url("js/new.js"), "/static/js/new.js")


class NotFoundTests(TestCase):
    def test_api_paths_answer_json_404(self):
        # 없는 숫자 ID, 글자·음수·위첨자 숫자·공백·빈 ID, 아주 큰 숫자, 없는 API 경로 (#44)
        for path in ("/api/v1/places/abc/", "/api/v1/nope/", "/api/v1/places/999999/", "/api/v1/places/-1/",
                     "/api/v1/places/%C2%B2/", "/api/v1/places/%20/", "/api/v1/places//",
                     "/api/v1/places/" + "9" * 30 + "/", "/api/v2/places/"):
            with self.subTest(path=path):
                res = self.client.get(path)
                self.assertEqual(res.status_code, 404)
                self.assertEqual(res["Content-Type"], "application/json")
                self.assertIn("detail", res.json())

    def test_api_without_trailing_slash_still_redirects(self):
        res = self.client.get("/api/v1/places")
        self.assertEqual(res.status_code, 301)
        self.assertEqual(res["Location"], "/api/v1/places/")

    def test_logged_in_users_and_json_accept_get_same_json_404(self):
        from accounts.models import User

        self.client.force_login(User.objects.create_user(username="staff404", is_staff=True))
        res = self.client.get("/api/v1/places/abc/", HTTP_ACCEPT="text/html")
        self.assertEqual((res.status_code, res["Content-Type"]), (404, "application/json"))

    def test_pages_keep_html_404(self):
        res = self.client.get("/places/abc/")
        self.assertEqual(res.status_code, 404)
        self.assertIn("text/html", res["Content-Type"])


class PhotoRightsNoticeTests(TestCase):
    """사진 칸이 있는 모든 폼에 '직접 찍은 사진만' 저작권 안내가 붙는다"""

    def test_every_photo_form_shows_notice(self):
        from core.uploads import PHOTO_RIGHTS_NOTICE
        from owners.forms import DeclarationForm, PhotoRequestForm
        from reports.forms import PhotoFixForm

        for form_class in (PhotoFixForm, PhotoRequestForm, DeclarationForm):
            with self.subTest(form=form_class.__name__):
                help_text = form_class().fields["photo"].help_text
                self.assertEqual(help_text.count(PHOTO_RIGHTS_NOTICE), 1)  # 원래 안내 + 저작권 안내 한 번
