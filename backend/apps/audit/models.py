import uuid

from django.conf import settings
from django.db import models


class AccessLog(models.Model):
    """Who opened a user's personal data, when and why. Never stores the data itself."""

    class Basis(models.TextChoices):
        REVIEW_ASSIGNMENT = "review_assignment", "Проверка претензии"
        ACCEPTED_OFFER = "accepted_offer", "Принятое предложение"
        MODERATION = "moderation", "Модерация"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    role = models.CharField(max_length=16)
    target_type = models.CharField(max_length=32)
    target_id = models.UUIDField()
    case_id = models.UUIDField(null=True)
    basis = models.CharField(max_length=32, choices=Basis.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.role} {self.target_type} {self.created_at:%Y-%m-%d %H:%M}"


def log_access(actor, target_type, target_id, basis, *, case_id=None):
    return AccessLog.objects.create(
        actor=actor,
        role=getattr(actor, "role", ""),
        target_type=target_type,
        target_id=target_id,
        case_id=case_id,
        basis=basis,
    )
