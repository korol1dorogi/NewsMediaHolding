import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Purpose(models.TextChoices):
    CLAIM_REVIEW = "claim_review", "Проверка претензии"
    LEGAL_SERVICE = "legal_service", "Работа юриста"


class HoldStatus(models.TextChoices):
    HELD = "held", "Заморожено"
    RELEASED = "released", "Разморожено"
    REFUNDED = "refunded", "Возвращено"


class RefundBasis(models.TextChoices):
    """Allowed reasons to return held money. Provisional until the lawyers confirm the policy."""

    CANCELLED_BEFORE_WORK = "cancelled_before_work", "Отмена до начала работы"
    DISPUTE_FOR_OWNER = "dispute_for_owner", "Спор решён в пользу пользователя"
    SERVICE_UNAVAILABLE = "service_unavailable", "Услугу невозможно оказать"


class AllocationKind(models.TextChoices):
    REVIEWER = "reviewer", "Юрист-проверяющий"
    LAWYER = "lawyer", "Ведущий юрист"
    PLATFORM = "platform", "Платформа"


class Hold(models.Model):
    """User's money held by the platform. Amounts are integer kopecks, never floats."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="holds"
    )
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    # Claim or Offer id. A plain UUID: those models belong to B5/B10.
    reference_id = models.UUIDField()
    amount_kopecks = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=HoldStatus.choices, default=HoldStatus.HELD)
    provider = models.CharField(max_length=32)
    provider_reference = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    release_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    refund_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    refund_basis = models.CharField(max_length=32, choices=RefundBasis.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_kopecks__gt=0), name="payments_hold_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(status__in=HoldStatus.values), name="payments_hold_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"Hold {self.id} {self.status} {self.amount_kopecks} коп."


class Allocation(models.Model):
    """How a released hold is split. The sum of allocations always equals the hold amount."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hold = models.ForeignKey(Hold, on_delete=models.PROTECT, related_name="allocations")
    kind = models.CharField(max_length=16, choices=AllocationKind.choices)
    # Null only for the platform's own account.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="allocations",
    )
    amount_kopecks = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "kind"]
        constraints = [
            models.UniqueConstraint(fields=["hold", "kind"], name="payments_allocation_once"),
            models.CheckConstraint(
                condition=(Q(kind=AllocationKind.PLATFORM) & Q(recipient__isnull=True))
                | (~Q(kind=AllocationKind.PLATFORM) & Q(recipient__isnull=False)),
                name="payments_allocation_recipient_matches_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount_kopecks} коп."
