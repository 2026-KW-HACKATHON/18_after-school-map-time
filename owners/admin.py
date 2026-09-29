from django.contrib import admin

from .models import ClaimCode, OwnerClaim, OwnerResponse, PlaceViewStat, SupportProgram, VisitWish


@admin.register(ClaimCode)
class ClaimCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "place", "building", "created_at", "used_at"]
    search_fields = ["code", "place__name", "building__name"]
    readonly_fields = ["code", "used_at"]


@admin.register(OwnerClaim)
class OwnerClaimAdmin(admin.ModelAdmin):
    list_display = ["user", "place", "building", "role", "status", "created_at"]
    list_filter = ["status", "role"]


@admin.register(OwnerResponse)
class OwnerResponseAdmin(admin.ModelAdmin):
    list_display = ["place", "owner_comment", "updated_at"]


@admin.register(SupportProgram)
class SupportProgramAdmin(admin.ModelAdmin):
    # 지원사업 정보는 매년 바뀌므로 여기서 고친다 (기획 v2 6.3)
    list_display = ["title", "region", "period", "is_active", "order"]
    list_editable = ["is_active", "order"]


@admin.register(VisitWish)
class VisitWishAdmin(admin.ModelAdmin):
    list_display = ["place", "profile", "created_at"]


@admin.register(PlaceViewStat)
class PlaceViewStatAdmin(admin.ModelAdmin):
    list_display = ["place", "profile", "date", "count"]
    list_filter = ["date"]
