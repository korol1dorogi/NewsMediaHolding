import uuid

from django.db import models


class PoolCard(models.Model):
    """The only thing lawyers see before an offer is accepted. No link to personal data.

    ``case`` is a private reference for the server; pool serializers never expose it.
    """

    class Moderation(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Опубликована"
        REJECTED = "rejected", "Отклонена"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField("cases.Case", related_name="pool_card", on_delete=models.CASCADE)
    card_version = models.PositiveIntegerField()
    category = models.CharField(max_length=64)
    description = models.TextField()
    city = models.CharField(max_length=128)
    amount_min_kopecks = models.PositiveBigIntegerField()
    amount_max_kopecks = models.PositiveBigIntegerField()
    company_name = models.CharField(max_length=500)
    company_status = models.CharField(max_length=16)
    company_inn = models.CharField(max_length=12, blank=True)  # private: for «Вы не один»
    actions_taken = models.JSONField(default=list)
    moderation_status = models.CharField(
        max_length=8, choices=Moderation.choices, default=Moderation.PENDING
    )
    rejection_reason = models.TextField(blank=True)
    scanner_flagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    offers_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-approved_at", "-created_at"]

    def __str__(self):
        return f"{self.category} · {self.city} · {self.moderation_status}"


class Offer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    card = models.ForeignKey(PoolCard, related_name="offers", on_delete=models.CASCADE)
    lawyer = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    scope = models.TextField()
    duration_days = models.PositiveIntegerField()
    price_kopecks = models.PositiveBigIntegerField()
    included = models.JSONField(default=list)
    excluded = models.JSONField(default=list)
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["card", "lawyer"], name="pool_one_offer_per_lawyer"),
            models.UniqueConstraint(
                fields=["card"], condition=models.Q(accepted=True), name="pool_one_accepted_offer"
            ),
        ]

    def __str__(self):
        return f"{self.card_id} {self.lawyer_id}"


class CaseContact(models.Model):
    """Personal data given when accepting an offer, if the claim path was never taken."""

    case = models.OneToOneField("cases.Case", related_name="contact", on_delete=models.CASCADE)
    full_name = models.CharField(max_length=200)
    reply_address = models.CharField(max_length=500)
    contract_reference = models.CharField(max_length=200)
    confirmed_at = models.DateTimeField()

    def __str__(self):
        return str(self.case_id)


class WorkAssignment(models.Model):
    """The chosen lawyer's access to the full case, created only by accepting an offer."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Ведёт дело"
        DONE = "done", "Завершено"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        "cases.Case", related_name="work_assignments", on_delete=models.CASCADE
    )
    offer = models.OneToOneField(Offer, related_name="assignment", on_delete=models.PROTECT)
    lawyer = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    hold = models.OneToOneField("payments.Hold", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case"], condition=models.Q(status="active"), name="pool_one_active_work"
            )
        ]

    def __str__(self):
        return f"{self.case_id} {self.lawyer_id} {self.status}"


class WorkSubmission(models.Model):
    assignment = models.ForeignKey(
        WorkAssignment, related_name="submissions", on_delete=models.CASCADE
    )
    version = models.PositiveIntegerField()
    text = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    accept_by = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    auto_accepted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["assignment", "version"], name="pool_work_version")
        ]

    def __str__(self):
        return f"{self.assignment_id} v{self.version}"
