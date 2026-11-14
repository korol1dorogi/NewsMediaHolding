from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError


class ModeratorAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role != "moderator":
            raise ValidationError("Доступ разрешён только модератору.", code="invalid_login")


class ModeratorAdminSite(AdminSite):
    login_form = ModeratorAuthenticationForm

    def has_permission(self, request):
        user = request.user
        return bool(user.is_active and user.is_staff and user.role == "moderator")


# No UserAdmin/Group registration: role alone must never grant role/permission editing.
# Domain tasks register only their scoped moderation models on this site.
moderator_admin = ModeratorAdminSite(name="moderator_admin")
