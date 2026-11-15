import uuid

from django.conf import settings
from django.db import models


class Case(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    state = models.CharField(max_length=32, default="draft")
    path = models.CharField(max_length=24, null=True)  # noqa: DJ001 - null in API v1
    ai_state = models.CharField(max_length=16, default="thinking")
    version = models.PositiveIntegerField(default=1)
    consent_text_version = models.TextField()
    close_reason = models.TextField(blank=True)
    card_confirmed_at = models.DateTimeField(null=True)
    card_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.pk)


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(Case, related_name="messages", on_delete=models.CASCADE)
    author = models.CharField(max_length=4, choices=[("user", "user"), ("ai", "ai")])
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return str(self.pk)


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(Case, related_name="documents", on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=32)
    size_bytes = models.PositiveIntegerField()
    source_version = models.PositiveIntegerField(default=1)
    content = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.pk)


class Fact(models.Model):
    class Status(models.TextChoices):
        FOUND = "found"
        NOT_FOUND = "not_found"
        USER_EDITED = "user_edited"

    case = models.ForeignKey(Case, related_name="facts", on_delete=models.CASCADE)
    key = models.TextField()
    value = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.NOT_FOUND)
    required = models.BooleanField()
    source = models.JSONField(null=True)
    source_quote = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["case", "key"], name="unique_case_fact")]

    def __str__(self):
        return self.key


class CardSnapshot(models.Model):
    case = models.OneToOneField(Case, related_name="card_snapshot", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    facts = models.JSONField()
    confirmed_at = models.DateTimeField()

    def __str__(self):
        return str(self.case_id)
