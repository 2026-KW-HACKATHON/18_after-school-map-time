from django.contrib import admin

from .models import AccessFacility, Building, Entrance, FieldDefinition, Place, Region


class EntranceInline(admin.TabularInline):
    model = Entrance
    extra = 0
    fields = ["name", "is_main", "description"]


class AccessFacilityInline(admin.TabularInline):
    model = AccessFacility
    extra = 0
    fields = ["kind", "name"]


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active"]


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ["__str__", "address", "region"]
    list_filter = ["region"]
    search_fields = ["name", "address"]
    inlines = [EntranceInline, AccessFacilityInline]


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "building", "floor", "region", "is_closed"]
    list_filter = ["region", "category", "is_closed"]
    search_fields = ["name", "address"]
    autocomplete_fields = ["building"]
    inlines = [EntranceInline, AccessFacilityInline]


@admin.register(Entrance)
class EntranceAdmin(admin.ModelAdmin):
    # 제보 화면의 출입구 검색(autocomplete)용
    list_display = ["__str__", "is_main"]
    search_fields = ["name", "place__name", "building__name", "building__address"]


@admin.register(FieldDefinition)
class FieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "unit", "scope", "value_type", "order", "is_active"]
    list_filter = ["scope", "value_type", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["key", "label"]


@admin.register(AccessFacility)
class AccessFacilityAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "place", "building"]
    list_filter = ["kind"]
    search_fields = ["name", "place__name", "building__name", "building__address"]
    autocomplete_fields = ["place", "building"]
