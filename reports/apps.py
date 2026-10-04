from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "제보"

    def ready(self):
        from . import ai  # noqa: F401 — 제보 삭제 때 AI 기록 내용을 비우는 신호 연결
