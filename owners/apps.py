from django.apps import AppConfig


class OwnersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "owners"
    verbose_name = "사장님·건물주"
