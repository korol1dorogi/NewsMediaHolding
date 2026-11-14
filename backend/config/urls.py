from django.urls import include, path

from apps.accounts.admin import moderator_admin

urlpatterns = [
    path("admin/", moderator_admin.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.core.urls")),
]

handler404 = "apps.accounts.errors.not_found"
