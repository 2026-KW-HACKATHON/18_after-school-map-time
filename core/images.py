"""
사진 정리 (제보·사장님 요청·답사 가져오기 공통).

폰 사진에는 EXIF 정보(촬영 위치 GPS, 촬영 시각, 기기)가 들어 있고, 올린 사진은 /media/ 로 누구나 받을 수 있다.
저장 전에 이미지를 다시 그려서 EXIF를 모두 지우고, 방향을 바로잡고, 크기를 줄인다 (저장 공간·모바일 데이터 절약).
"""

import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

PHOTO_MAX_PX = 1600   # 긴 변 기준. 입구 구조를 알아보기에 충분
JPEG_QUALITY = 85


def normalize_photo(source, name=None):
    """
    이미지 파일(경로 또는 업로드 파일) → EXIF 없는 JPEG ContentFile.
    name 을 안 주면 원래 파일 이름에 .jpg 를 붙인다.
    """
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)  # 폰에서 세로로 찍은 사진이 눕지 않게 (EXIF 방향값 적용 후 버림)
        im.thumbnail((PHOTO_MAX_PX, PHOTO_MAX_PX))
        buffer = io.BytesIO()
        im.convert("RGB").save(buffer, "JPEG", quality=JPEG_QUALITY)  # 새로 저장 → 메타데이터가 따라오지 않음
    stem = Path(name or getattr(source, "name", "") or "photo").stem
    return ContentFile(buffer.getvalue(), name=f"{stem}.jpg")
