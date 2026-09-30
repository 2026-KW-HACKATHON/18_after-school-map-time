from django.contrib import admin

from .models import ConditionProfile, Judgment, Rule, RuleCondition, RuleSet


@admin.register(ConditionProfile)
class ConditionProfileAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "order", "is_active"]
    list_editable = ["order", "is_active"]


class RuleConditionInline(admin.TabularInline):
    model = RuleCondition
    fk_name = "rule"
    extra = 0


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ["__str__", "profile", "stage", "priority", "outcome", "basis", "conditions_text"]
    list_filter = ["rule_set", "profile", "stage", "basis"]
    inlines = [RuleConditionInline]

    @admin.display(description="조건 (모두 만족)")
    def conditions_text(self, obj):
        return " 그리고 ".join(str(c) for c in obj.conditions.all())


@admin.register(RuleSet)
class RuleSetAdmin(admin.ModelAdmin):
    list_display = ["__str__", "note", "created_at"]


@admin.register(Judgment)
class JudgmentAdmin(admin.ModelAdmin):
    # 판정 결과는 계산값이라 직접 고치지 않는다 (값·규칙을 고친 뒤 recompute_judgments)
    list_display = ["place", "profile", "result", "reason", "rule_version", "computed_at"]
    list_filter = ["profile", "result", "rule_version"]
    search_fields = ["place__name"]
    readonly_fields = [f.name for f in Judgment._meta.fields]

    def has_add_permission(self, request):
        return False
