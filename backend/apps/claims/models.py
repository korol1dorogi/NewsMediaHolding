import uuid

from django.db import models

CLAIMANT = "{{claimant}}"
REPLY_ADDRESS = "{{reply_address}}"


class Claim(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField("cases.Case", related_name="claim", on_delete=models.CASCADE)
    card_version = models.PositiveIntegerField()
    current_version = models.PositiveIntegerField(default=0)  # 0 until the draft is ready
    norm_ids = models.JSONField(default=list)
    personal_data_confirmed = models.BooleanField(default=False)
    faulty = models.BooleanField(default=False)
    submit_consent_version = models.CharField(max_length=64, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Review (B6/B7).
    hold = models.OneToOneField(
        "payments.Hold", null=True, blank=True, on_delete=models.PROTECT, related_name="claim"
    )
    queued_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rejection_comment = models.TextField(blank=True)
    commission_revoked = models.BooleanField(default=False)
    outcome = models.CharField(max_length=16, blank=True)
    outcome_comment = models.TextField(blank=True)
    sent_on = models.DateField(null=True, blank=True)
    response_due_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)

    @property
    def ready(self):
        return self.current_version > 0


class ClaimVersion(models.Model):
    """Immutable: a lawyer edit is a new row. Text keeps personal-data placeholders."""

    class Author(models.TextChoices):
        AI = "ai", "AI"
        LAWYER = "lawyer", "Юрист"

    claim = models.ForeignKey(Claim, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    author = models.CharField(max_length=8, choices=Author.choices)
    author_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    template_text = models.TextField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["version"]
        constraints = [
            models.UniqueConstraint(fields=["claim", "version"], name="claims_version_once")
        ]

    def __str__(self):
        return f"{self.claim_id} v{self.version}"


class ClaimPersonalData(models.Model):
    """Kept apart from the claim text: queue and review serializers never touch this model."""

    claim = models.OneToOneField(Claim, related_name="personal_data", on_delete=models.CASCADE)
    full_name = models.CharField(max_length=200)
    reply_address = models.CharField(max_length=500)
    contract_reference = models.CharField(max_length=200)
    confirmed_at = models.DateTimeField()

    def __str__(self):
        return str(self.claim_id)


class ReviewAssignment(models.Model):
    """A lawyer's hold on one claim for review. Expires after CLAIM_REVIEW_TIMEOUT_HOURS."""

    class Status(models.TextChoices):
        ACTIVE = "active", "В работе"
        DONE = "done", "Завершено"
        EXPIRED = "expired", "Истекло"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    claim = models.ForeignKey(Claim, related_name="assignments", on_delete=models.CASCADE)
    lawyer = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    taken_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["claim", "version"], name="claims_assignment_version"),
            models.UniqueConstraint(
                fields=["claim"],
                condition=models.Q(status="active"),
                name="claims_one_active_assignment",
            ),
        ]

    def __str__(self):
        return f"{self.claim_id} #{self.version} {self.status}"


class ExcludedReviewer(models.Model):
    """A lawyer whose review of this claim was found faulty: no re-review, no offers."""

    claim = models.ForeignKey(Claim, related_name="excluded", on_delete=models.CASCADE)
    lawyer = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["claim", "lawyer"], name="claims_excluded_once")
        ]

    def __str__(self):
        return f"{self.claim_id} {self.lawyer_id}"


def personalize(template_text, personal_data):
    """Owner/assigned-lawyer view only. Without data the placeholders stay visible."""
    if personal_data is None:
        return template_text
    return template_text.replace(CLAIMANT, personal_data.full_name).replace(
        REPLY_ADDRESS, personal_data.reply_address
    )
