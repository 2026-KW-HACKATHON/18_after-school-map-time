from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "회원"

    def ready(self):
        from . import receivers  # noqa: F401  제보 처리 결과 → 작성자 알림 연결
