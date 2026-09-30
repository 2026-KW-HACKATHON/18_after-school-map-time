from django.contrib import admin, messages

from .models import AccessibilityValue, Reconfirmation, Report, ReportConfirmation
from .services import reject_report, verify_report


class AccessibilityValueInline(admin.TabularInline):
    model = AccessibilityValue
    extra = 1
    autocomplete_fields = ["field"]


class ReportConfirmationInline(admin.TabularInline):
    model = ReportConfirmation
    extra = 0
    readonly_fields = ["user", "created_at"]
    can_delete = False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["__str__", "source", "status", "created_by", "created_at"]
    list_filter = ["status", "source", "place__region"]
    search_fields = ["place__name", "building__name", "building__address", "note"]
    autocomplete_fields = ["place", "building", "entrance"]
    readonly_fields = ["created_by", "created_at", "reviewed_by", "reviewed_at"]
    inlines = [AccessibilityValueInline, ReportConfirmationInline]
    actions = ["action_verify", "action_reject"]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="선택한 제보 반영 (판정에 사용)")
    def action_verify(self, request, queryset):
        for report in queryset.exclude(status=Report.Status.VERIFIED):
            verify_report(report, by=request.user)
        messages.success(request, "반영했습니다. 해당 장소 판정이 다시 계산됩니다.")

    @admin.action(description="선택한 제보 반려")
    def action_reject(self, request, queryset):
        for report in queryset.exclude(status=Report.Status.REJECTED):
            reject_report(report, by=request.user, reason="관리자 반려")
        messages.success(request, "반려했습니다.")


@admin.register(Reconfirmation)
class ReconfirmationAdmin(admin.ModelAdmin):
    # "지금도 맞아요" 기록 — 신뢰도 표시에만 쓰므로 조회만
    list_display = ["place", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["place__name"]
    readonly_fields = ["place", "user", "created_at"]
