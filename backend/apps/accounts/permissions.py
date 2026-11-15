from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    role = None

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == self.role)


class IsUser(HasRole):
    role = "user"


class IsLawyer(HasRole):
    role = "lawyer"


class IsModerator(HasRole):
    role = "moderator"


class IsEditor(HasRole):
    role = "editor"
