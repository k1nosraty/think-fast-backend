from django.contrib import admin

from apps.accounts.models import GuestIdentity
from config.admin import ReadOnlyProductionAdmin


@admin.register(GuestIdentity)
class GuestIdentityAdmin(ReadOnlyProductionAdmin, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "display_name", "avatar_id", "created_at", "expires_at", "revoked_at")
    search_fields = ("id", "display_name")
