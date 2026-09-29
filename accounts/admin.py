from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class TeokeopneUserAdmin(UserAdmin):
    list_display = ("username", "nickname", "is_staff", "date_joined")
    search_fields = ("username", "nickname")
    fieldsets = UserAdmin.fieldsets + (("턱없네", {"fields": ("nickname",)}),)
