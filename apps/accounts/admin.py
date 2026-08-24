from django.contrib import admin

from apps.accounts.models import GuestIdentity


@admin.register(GuestIdentity)
class GuestIdentityAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "display_name", "avatar_id", "created_at", "expires_at", "revoked_at")
    readonly_fields = ("id", "token_digest", "created_at", "last_seen_at", "expires_at")
    search_fields = ("id", "display_name")
