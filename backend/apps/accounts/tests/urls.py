from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsEditor, IsLawyer, IsModerator, IsUser


class RoleView(APIView):
    def get(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("test/user", RoleView.as_view(permission_classes=[IsUser])),
    path("test/lawyer", RoleView.as_view(permission_classes=[IsLawyer])),
    path("test/moderator", RoleView.as_view(permission_classes=[IsModerator])),
    path("test/editor", RoleView.as_view(permission_classes=[IsEditor])),
    path("", include("config.urls")),
]
