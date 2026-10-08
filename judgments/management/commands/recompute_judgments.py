"""
전체(또는 한 지역) 장소를 사용 중인 규칙으로 다시 판정한다. 규칙을 바꾼 뒤 실행.

    python manage.py recompute_judgments
    python manage.py recompute_judgments --region wolgye1
"""

from django.core.management.base import BaseCommand

from judgments.engine import recompute_place
from judgments.models import RuleSet
from places.models import Place


class Command(BaseCommand):
    help = "장소 판정을 다시 계산한다"

    def add_arguments(self, parser):
        parser.add_argument("--region", help="지역 코드 (없으면 전체)")

    def handle(self, region=None, **options):
        rule_set = RuleSet.active()
        if rule_set is None:
            self.stdout.write(self.style.WARNING("사용 중인 규칙이 없습니다. 먼저 load_rules 를 실행하세요."))
            return
        places = Place.objects.filter(is_closed=False).select_related("building")
        if region:
            places = places.in_region(region)
        count = 0
        for place in places:
            recompute_place(place, rule_set)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"장소 {count}곳을 규칙 v{rule_set.version}로 다시 판정했습니다."))
