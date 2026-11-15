from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginInput, UserOutput
from .throttling import enforce_login_account_limit, enforce_login_ip_limit


class AuthView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(AuthView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(AuthView):
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        enforce_login_ip_limit(request)
        return super().initial(request, *args, **kwargs)

    def post(self, request):
        data = request.data
        serializer = LoginInput(data=data)
        serializer.is_valid(raise_exception=True)
        enforce_login_account_limit(serializer.validated_data["username"])
        user = authenticate(request=request, **serializer.validated_data)
        if user is None or not user.is_active:
            raise AuthenticationFailed
        login(request, user)
        return Response(UserOutput(user).data)


class LogoutView(AuthView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"status": "logged_out"})


class MeView(AuthView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = get_user_model().objects.get(pk=request.user.pk)
        return Response(UserOutput(user).data)
