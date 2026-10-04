import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # 아이폰 기본 사진 형식(HEIC/HEIF)을 Pillow가 열 수 있게 등록한다.
        # 등록하면 Django ImageField 검사와 사진 정리(core/images.py)가 HEIC도 받아서 JPEG로 저장한다.
        try:
            from pi_heif import register_heif_opener
        except ImportError as e:  # 패키지가 없는 환경이면 HEIC만 못 받고 나머지는 그대로
            logger.warning("HEIC 사진을 열 수 없어요: %s", e)
        else:
            register_heif_opener()
