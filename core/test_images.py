"""사진 정리 — EXIF 삭제·크기 줄이기·얼굴 자동 가림 (실제 OpenCV 검출기로 그린 얼굴을 찾게 함)"""

import io
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image, ImageDraw, ImageFilter, ImageStat

from core import images


def drawn_face(size=600, background=200):
    """사람 얼굴처럼 그린 그림 (정면 얼굴 검출기가 찾는 눈·코·입 배치)"""
    im = Image.new("L", (size, size), background)
    d = ImageDraw.Draw(im)
    s = size / 400
    d.ellipse([100 * s, 60 * s, 300 * s, 330 * s], fill=170)
    for x in (150, 250):
        d.ellipse([(x - 28) * s, 145 * s, (x + 28) * s, 175 * s], fill=60)
        d.rectangle([(x - 35) * s, 120 * s, (x + 35) * s, 130 * s], fill=80)
    d.polygon([(200 * s, 175 * s), (185 * s, 235 * s), (215 * s, 235 * s)], fill=140)
    d.ellipse([160 * s, 255 * s, 240 * s, 280 * s], fill=90)
    return im.filter(ImageFilter.GaussianBlur(4)).convert("RGB")


def as_upload(im, name="door.jpg"):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    buf.seek(0)
    buf.name = name
    return buf


class FaceBlurTests(SimpleTestCase):
    def test_face_is_found_and_blurred(self):
        original = drawn_face()
        result = images.normalize_photo(as_upload(original))
        self.assertEqual(result.blurred_faces, 1)
        with Image.open(io.BytesIO(result.read())) as out:
            eyes = (180, 200, 420, 270)                         # 두 눈이 있는 띠: 흐려지면 명암 차이가 줄어듦
            before = ImageStat.Stat(original.crop(eyes).convert("L")).stddev[0]
            after = ImageStat.Stat(out.crop(eyes).convert("L")).stddev[0]
            self.assertLess(after, before * 0.6)

    def test_no_face_no_change_in_count(self):
        plain = Image.new("RGB", (800, 600), "gray")
        ImageDraw.Draw(plain).rectangle([300, 200, 500, 600], fill="black")   # 문처럼 생긴 사각형
        self.assertEqual(images.normalize_photo(as_upload(plain)).blurred_faces, 0)

    def test_without_opencv_other_cleanup_still_works(self):
        with mock.patch.object(images, "_detector", False):
            result = images.normalize_photo(as_upload(drawn_face()))
        self.assertEqual(result.blurred_faces, 0)
        self.assertTrue(result.name.endswith(".jpg"))


class HeicTests(SimpleTestCase):
    """아이폰 HEIC 사진: 열리고, 방향을 바로잡고, EXIF 없는 JPEG로 바뀐다 (core/apps.py 등록)"""

    SAMPLE = Path(__file__).parent / "testdata" / "sample.heic"  # 120×80, EXIF 방향=6(세로), 제조사 정보 포함

    def test_heic_becomes_upright_jpeg_without_exif(self):
        with self.SAMPLE.open("rb") as f:
            out = images.normalize_photo(f, name="IMG_0001.HEIC")
        self.assertEqual(out.name, "IMG_0001.jpg")
        im = Image.open(io.BytesIO(out.read()))
        self.assertEqual(im.format, "JPEG")
        self.assertEqual(im.size, (80, 120))  # EXIF 방향값대로 세워짐
        self.assertFalse(im.getexif())

    def test_django_image_field_accepts_heic(self):
        from django import forms
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("IMG_0001.HEIC", self.SAMPLE.read_bytes(), content_type="image/heic")
        field = forms.ImageField()
        self.assertEqual(field.clean(upload).image.format, "HEIF")
