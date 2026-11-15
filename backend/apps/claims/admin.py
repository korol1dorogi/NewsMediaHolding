from django.contrib import admin, messages

from apps.accounts.admin import moderator_admin
from apps.audit.admin import ReadOnlyAdmin
from apps.audit.models import AccessLog, log_access
from apps.cases.states import Conflict

from . import review
from .models import Claim


@admin.register(Claim, site=moderator_admin)
class ClaimAdmin(ReadOnlyAdmin):
    """Moderator view of claims. Read-only except the «faulty» decision (B7)."""

    list_display = ("id", "case", "current_version", "faulty", "submitted_at", "sent_on")
    list_filter = ("faulty",)
    readonly_fields = (
        "id",
        "case",
        "current_version",
        "faulty",
        "commission_revoked",
        "submitted_at",
        "sent_on",
        "response_due_on",
        "outcome",
    )
    exclude = ("norm_ids", "reviewer", "hold", "rejection_comment", "outcome_comment")
    actions = ["mark_faulty"]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        claim = self.get_object(request, object_id)
        if claim is not None:
            log_access(
                request.user, "claim", claim.pk, AccessLog.Basis.MODERATION, case_id=claim.case_id
            )
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.action(description="Признать претензию ошибочной: бесплатная перепроверка")
    def mark_faulty(self, request, queryset):
        done = 0
        for claim in queryset:
            try:
                review.mark_faulty(claim.pk)
                done += 1
            except Conflict:
                self.message_user(
                    request,
                    f"{claim.pk}: можно только для проверенной претензии до отправки.",
                    messages.WARNING,
                )
        if done:
            self.message_user(request, f"Отправлено на перепроверку: {done}.")
