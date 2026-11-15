import uuid

from django.db import models


class CompanyCheck(models.Model):
    """Snapshot of one company check for a case's confirmed card version."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Действует"
        LIQUIDATING = "liquidating", "Ликвидируется"
        BANKRUPT = "bankrupt", "Банкротство"
        UNAVAILABLE = "unavailable", "Не удалось проверить"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey("cases.Case", related_name="company_checks", on_delete=models.CASCADE)
    card_version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices)
    name = models.CharField(max_length=500, blank=True)
    inn = models.CharField(max_length=12, blank=True)
    registered_on = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=64)
    is_demo = models.BooleanField(default=False)
    checked_at = models.DateTimeField()

    class Meta:
        ordering = ["-checked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "card_version"], name="companies_one_check_per_card_version"
            )
        ]

    def __str__(self):
        return f"{self.status} {self.inn}"
