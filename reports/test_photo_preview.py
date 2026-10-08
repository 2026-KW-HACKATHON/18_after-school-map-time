"""미리보기는 임시 테스트 DB에서도 제보나 업로드 파일을 저장하지 않는다."""
import io
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from accounts.models import User
from .models import Report


class PhotoPreviewTests(TestCase):
    url = reverse("reports:photo-preview")

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="preview-test")
        self.client.force_login(self.user)

    def upload(self, name="sample.heic", content=None):
        if content is None:
            content = (Path(__file__).parent.parent / "core/testdata/sample.heic").read_bytes()
        return SimpleUploadedFile(name, content, content_type="image/heic")

    def test_heic_heif_preview_is_upright_jpeg_no_metadata_or_storage(self):
        for name in ("sample.heic", "sample.HEIF"):
            with self.subTest(name=name), patch("django.core.files.storage.default_storage.save") as save:
                response = self.client.post(self.url, {"photo": self.upload(name)})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/jpeg")
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                with Image.open(io.BytesIO(response.content)) as image:
                    self.assertEqual(image.size, (80, 120))
                    self.assertFalse(image.getexif())
                save.assert_not_called()
        self.assertFalse(Report.objects.exists())

    def test_jpeg_and_png_still_convert(self):
        for fmt in ("JPEG", "PNG"):
            buffer = io.BytesIO(); Image.new("RGB", (12, 16)).save(buffer, fmt)
            self.assertEqual(self.client.post(self.url, {"photo": self.upload(f"door.{fmt.lower()}", buffer.getvalue())}).status_code, 200)

    def test_invalid_missing_and_large_files(self):
        for data in ({}, {"photo": self.upload(content=b"invalid")},
                     {"photo": self.upload(content=b"x" * (10 * 1024 * 1024 + 1))}):
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 400)
            self.assertIn("detail", response.json())

    def test_requires_login_post_and_csrf(self):
        self.assertEqual(Client().post(self.url, {"photo": self.upload()}).status_code, 302)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        secure = Client(enforce_csrf_checks=True); secure.force_login(self.user)
        self.assertEqual(secure.post(self.url, {"photo": self.upload()}).status_code, 403)

    def test_rate_limit(self):
        for _ in range(20): self.client.post(self.url, {})
        self.assertEqual(self.client.post(self.url, {}).status_code, 429)

    def test_decompression_bomb_is_rejected(self):
        with patch("core.images.normalize_photo", side_effect=Image.DecompressionBombError("too big")):
            self.assertEqual(self.client.post(self.url, {"photo": self.upload()}).status_code, 400)
