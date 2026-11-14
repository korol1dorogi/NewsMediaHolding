from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    """Keep Django sessions/CSRF; advertise the challenge needed for DRF HTTP 401."""

    def authenticate_header(self, request):
        return "Session"
