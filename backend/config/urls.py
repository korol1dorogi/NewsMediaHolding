from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.cases.urls")),
    path("api/", include("apps.core.urls")),
]
