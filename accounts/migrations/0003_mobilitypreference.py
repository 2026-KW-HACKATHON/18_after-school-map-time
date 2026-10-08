from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_notification")]
    operations = [migrations.CreateModel(
        name="MobilityPreference",
        fields=[
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True,
                                          related_name="mobility_preference", serialize=False,
                                          to=settings.AUTH_USER_MODEL, verbose_name="회원")),
            ("data", models.JSONField(default=dict, verbose_name="선택 및 개인화 설정")),
            ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정 시각")),
        ],
        options={"verbose_name": "내 이동 조건 설정", "verbose_name_plural": "내 이동 조건 설정"},
    )]
