from django.contrib import admin, messages

from apps.accounts.admin import moderator_admin
from apps.audit.admin import ReadOnlyAdmin

from . import services
from .models import PoolCard


@admin.register(PoolCard, site=moderator_admin)
class PoolCardAdmin(ReadOnlyAdmin):
    """Moderation of every card before the pool (product decision for the start).

    The moderator sees only the anonymised card, never the source case.
    """

    list_display = (
        "created_at",
        "category",
        "city",
        "company_name",
        "moderation_status",
        "scanner_flagged",
    )
    list_filter = ("moderation_status", "scanner_flagged")
    fields = (
        "category",
        "description",
        "city",
        "amount_min_kopecks",
        "amount_max_kopecks",
        "company_name",
        "company_status",
        "actions_taken",
        "moderation_status",
        "rejection_reason",
        "scanner_flagged",
        "approved_at",
        "offers_until",
    )
    readonly_fields = fields
    actions = ["approve_cards", "reject_cards"]

    @admin.action(description="Опубликовать в пуле")
    def approve_cards(self, request, queryset):
        for card in queryset:
            services.approve(card)
        self.message_user(request, f"Опубликовано: {queryset.count()}.")

    @admin.action(description="Отклонить: требуется дополнительная очистка")
    def reject_cards(self, request, queryset):
        for card in queryset:
            services.reject(card, "Описание требует дополнительной очистки.")
        self.message_user(request, f"Отклонено: {queryset.count()}.", messages.WARNING)
