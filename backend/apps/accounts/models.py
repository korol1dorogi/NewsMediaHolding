import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "user", "Пользователь"
        LAWYER = "lawyer", "Юрист"
        MODERATOR = "moderator", "Модератор"
        EDITOR = "editor", "Редактор"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.USER)
    is_demo = models.BooleanField(default=False)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["user", "lawyer", "moderator", "editor"]),
                name="accounts_user_known_role",
            )
        ]


class LawyerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(default=0)

    def __str__(self):
        return str(self.user_id)
