from django.apps import AppConfig


class OwnersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "owners"
    verbose_name = "사장님·건물주"

    def ready(self):
        from . import receivers  # noqa: F401  판정 개선 → 가고 싶어요 누른 주민 알림 연결
