"""
판정 규칙 파일을 DB에 넣는다. 같은 버전이 이미 있으면 그 버전의 규칙을 파일 내용으로 교체한다.
"activate": true 면 이 버전을 사용 중으로 바꾸고 전체 장소를 다시 판정한다.

    python manage.py load_rules                          # judgments/data/rules_v1.json
    python manage.py load_rules judgments/data/rules_v2.json
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from judgments.models import ConditionProfile, Rule, RuleCondition, RuleSet
from places.models import FieldDefinition

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "rules_v1.json"


class Command(BaseCommand):
    help = "판정 규칙 JSON 파일을 불러온다 (기본: judgments/data/rules_v1.json)"

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_FILE))

    def handle(self, path, **options):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rule_set = self.load(data)
        self.stdout.write(self.style.SUCCESS(f"규칙 v{rule_set.version}: {rule_set.rules.count()}개 반영"))
        if rule_set.is_active:
            from django.core.management import call_command

            call_command("recompute_judgments", stdout=self.stdout)

    @transaction.atomic
    def load(self, data):
        for p in data["profiles"]:
            ConditionProfile.objects.update_or_create(key=p["key"], defaults={"label": p["label"], "order": p["order"]})

        rule_set, _ = RuleSet.objects.update_or_create(
            version=data["version"], defaults={"note": data.get("note", "")}
        )
        rule_set.rules.all().delete()
        fields = {f.key: f for f in FieldDefinition.objects.all()}
        for r in data["rules"]:
            rule = Rule.objects.create(
                rule_set=rule_set,
                profile_id=r["profile"],
                outcome=r["outcome"],
                priority=r["priority"],
                basis=r["basis"],
                note=r.get("note", ""),
            )
            for c in r["conditions"]:
                cond = RuleCondition(
                    rule=rule,
                    field=fields[c["field"]],
                    operator=c["operator"],
                    threshold=c.get("threshold"),
                    threshold_text=c.get("threshold_text", ""),
                    ref_field=fields.get(c.get("ref_field")),
                    ref_factor=c.get("ref_factor", "1"),
                    if_missing=c.get("if_missing", RuleCondition.IfMissing.UNKNOWN),
                )
                cond.full_clean(exclude=["rule"])
                cond.save()

        if data.get("activate"):
            RuleSet.objects.exclude(pk=rule_set.pk).update(is_active=False)
            rule_set.is_active = True
            rule_set.save(update_fields=["is_active"])
        return rule_set
