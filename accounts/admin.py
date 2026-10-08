from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Notification, User


@admin.register(User)
class TeokeopneUserAdmin(UserAdmin):
    list_display = ("username", "nickname", "is_staff", "date_joined")
    search_fields = ("username", "nickname")
    fieldsets = UserAdmin.fieldsets + (("턱없네", {"fields": ("nickname",)}),)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    # 알림은 서비스가 자동으로 만든다 — 관리자 화면은 확인용
    list_display = ["user", "kind", "message", "created_at", "read_at"]
    list_filter = ["kind", "read_at"]
    search_fields = ["user__username", "user__nickname", "message"]
