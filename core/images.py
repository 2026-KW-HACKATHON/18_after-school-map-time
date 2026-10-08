"""
사진 정리 (제보·사장님 요청·답사 가져오기 공통).

폰 사진에는 EXIF 정보(촬영 위치 GPS, 촬영 시각, 기기)가 들어 있고, 올린 사진은 /media/ 로 누구나 받을 수 있다.
저장 전에 이미지를 다시 그려서 EXIF를 모두 지우고, 방향을 바로잡고, 크기를 줄인다 (저장 공간·모바일 데이터 절약).

아이폰 HEIC/HEIF 사진도 받는다 (core/apps.py에서 pi-heif를 Pillow에 등록). 저장은 항상 JPEG라 어느 브라우저에서나 보인다.

사람 얼굴은 자동으로 흐리게 한다 (기획 v2 4.4). OpenCV 얼굴 인식(Haar, 정면 얼굴)을 서버 안에서 돌리므로
외부 전송·비용이 없다. 번호판은 무료 모델의 정확도가 낮아 자동으로 하지 않고 운영자 검수로 거른다.
OpenCV를 불러오지 못하는 환경이면 얼굴 가림만 건너뛰고 나머지 정리는 그대로 한다.
"""

import io
import logging
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

PHOTO_MAX_PX = 1600   # 긴 변 기준. 입구 구조를 알아보기에 충분
JPEG_QUALITY = 85
FACE_MIN_RATIO = 0.04  # 얼굴로 볼 최소 크기 = 사진 짧은 변의 4% (멀리 작게 찍힌 무늬를 얼굴로 착각하지 않게)
FACE_PADDING = 0.15    # 얼굴 테두리보다 15% 넓게 가림 (머리카락·귀까지)

_detector = None       # 처음 한 번만 불러옴. 못 불러오면 False


def _face_detector():
    """OpenCV 정면 얼굴 검출기. 경로에 한글이 있어도 되게 XML을 파이썬으로 읽어서 메모리로 넘긴다"""
    global _detector
    if _detector is None:
        try:
            import cv2

            xml = Path(cv2.data.haarcascades, "haarcascade_frontalface_default.xml").read_text(encoding="utf-8")
            storage = cv2.FileStorage(xml, cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
            detector = cv2.CascadeClassifier()
            _detector = detector if detector.read(storage.getFirstTopLevelNode()) and not detector.empty() else False
        except (ImportError, OSError) as e:  # OpenCV가 없거나 깨진 환경
            logger.warning("얼굴 자동 가림을 쓸 수 없어요: %s", e)
            _detector = False
    return _detector or None


def detect_faces(im):
    """[(x, y, 너비, 높이)] — 사진 속 정면 얼굴 위치"""
    detector = _face_detector()
    if detector is None:
        return []
    import cv2
    import numpy as np

    gray = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
    min_px = max(24, int(min(im.size) * FACE_MIN_RATIO))
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_px, min_px))
    return [tuple(int(v) for v in face) for face in faces]


def blur_faces(im):
    """얼굴을 흐리게 한 이미지와 가린 얼굴 수"""
    faces = detect_faces(im)
    for x, y, w, h in faces:
        pad = int(max(w, h) * FACE_PADDING)
        box = (max(0, x - pad), max(0, y - pad), min(im.width, x + w + pad), min(im.height, y + h + pad))
        region = im.crop(box).filter(ImageFilter.GaussianBlur(radius=max(8, (box[2] - box[0]) // 6)))
        im.paste(region, box)
    return im, len(faces)


def normalize_photo(source, name=None):
    """
    이미지 파일(경로 또는 업로드 파일) → EXIF 없고 얼굴이 가려진 JPEG ContentFile.
    name 을 안 주면 원래 파일 이름에 .jpg 를 붙인다. 가린 얼굴 수는 .blurred_faces 에 담긴다.
    """
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)  # 폰에서 세로로 찍은 사진이 눕지 않게 (EXIF 방향값 적용 후 버림)
        im.thumbnail((PHOTO_MAX_PX, PHOTO_MAX_PX))
        im, blurred = blur_faces(im.convert("RGB"))
        buffer = io.BytesIO()
        im.save(buffer, "JPEG", quality=JPEG_QUALITY)  # 새로 저장 → 메타데이터가 따라오지 않음
    stem = Path(name or getattr(source, "name", "") or "photo").stem
    content = ContentFile(buffer.getvalue(), name=f"{stem}.jpg")
    content.blurred_faces = blurred
    if blurred:
        logger.info("사진 %s: 얼굴 %d곳을 자동으로 가렸어요", content.name, blurred)
    return content
