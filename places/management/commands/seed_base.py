"""
기본 데이터 넣기: 지역(월계1동)과 접근성 필드 정의.
여러 번 실행해도 같은 결과 (있으면 갱신, 없으면 생성). 데이터는 places/data/*.json 에서 수정한다.

    python manage.py seed_base
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from places.models import FieldDefinition, Region

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


class Command(BaseCommand):
    help = "지역과 접근성 필드 정의 기본 데이터를 넣는다 (places/data/*.json)"

    @transaction.atomic
    def handle(self, *args, **options):
        for row in load("regions.json"):
            code = row.pop("code")
            _, created = Region.objects.update_or_create(code=code, defaults=row)
            self.stdout.write(f"지역 {code}: {'생성' if created else '갱신'}")

        count = 0
        for row in load("field_definitions.json"):
            key = row.pop("key")
            FieldDefinition.objects.update_or_create(key=key, defaults=row)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"필드 정의 {count}개 반영"))
