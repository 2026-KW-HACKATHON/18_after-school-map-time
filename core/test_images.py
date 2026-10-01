"""사진 정리 — EXIF 삭제·크기 줄이기·얼굴 자동 가림 (실제 OpenCV 검출기로 그린 얼굴을 찾게 함)"""

import io
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
