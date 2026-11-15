from django.contrib import admin

from apps.accounts.admin import moderator_admin

from .models import AccessLog


class ReadOnlyAdmin(admin.ModelAdmin):
    """Records are evidence: nobody adds, edits or deletes them through the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and getattr(request.user, "role", None) == "moderator"

    def has_module_permission(self, request):
        return self.has_view_permission(request)


@admin.register(AccessLog, site=moderator_admin)
class AccessLogAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "role", "actor", "target_type", "target_id", "basis")
    list_filter = ("basis", "role", "target_type")
    readonly_fields = list_display + ("case_id",)
    actions = None
