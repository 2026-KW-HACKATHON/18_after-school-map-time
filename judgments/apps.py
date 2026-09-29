from django.apps import AppConfig


class JudgmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "judgments"
    verbose_name = "판정"

    def ready(self):
        from . import receivers  # noqa: F401  제보 반영 신호 → 재판정 연결
