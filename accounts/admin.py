from django.contrib import admin
from .models import CustomUser, City


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "country", "is_active")
    search_fields = ("name", "state", "country")
    list_filter = ("country", "is_active")


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "city", "is_approved", "is_staff")
    list_filter = ("role", "is_approved", "is_staff", "city")
    search_fields = ("email", "full_name")
    actions = ["approve_users"]

    def approve_users(self, request, queryset):
        queryset.update(is_approved=True)

    approve_users.short_description = "Approve selected users"
