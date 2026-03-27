from django.contrib import admin
from .models import Area, CustomUser, City
from django.utils import timezone

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "country", "is_active")
    search_fields = ("name", "state", "country")
    list_filter = ("country", "is_active")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city__name")


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "city", "area", "is_approved", "is_staff")
    list_filter = ("role", "is_approved", "is_staff", "city", "area")
    search_fields = ("email", "full_name")
    actions = ["approve_users"]

    def approve_users(self, request, queryset):
        for user in queryset:
            user.is_approved = True
            user.approved_by = request.user
            user.approved_at = timezone.now()
            user.save()

    approve_users.short_description = "Approve selected users"
