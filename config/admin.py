from django.http import HttpRequest


class ReadOnlyProductionAdmin:
    """Keep operational inspection separate from privileged mutation commands."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def get_readonly_fields(self, request: HttpRequest, obj: object = None) -> tuple[str, ...]:
        return tuple(field.name for field in self.model._meta.fields)  # type: ignore[attr-defined]
