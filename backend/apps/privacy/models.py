import uuid

from django.conf import settings
from django.db import models

# Draft texts until the consulting lawyers review them. The version is what the user saw.
CONSENT_TEXTS = {
    "demo-v1": {
        "processing_offer": (
            "ЧЕРНОВИК, до проверки юристами. Я согласен на обработку сведений об обращении и "
            "принимаю оферту: сделки с юристами — только на платформе; редакция NMH может "
            "получить обезличенный сигнал о массовом случае без моих персональных данных."
        ),
        "transfer_to_reviewer": (
            "ЧЕРНОВИК, до проверки юристами. Я согласен передать текст претензии и сведения "
            "карточки юристу-проверяющему. Мои контакты проверяющему не передаются."
        ),
        "transfer_to_lawyer": (
            "ЧЕРНОВИК, до проверки юристами. Я согласен раскрыть свои данные и документы "
            "выбранному юристу для ведения дела."
        ),
        "publish_pool": (
            "ЧЕРНОВИК, до проверки юристами. Я согласен опубликовать обезличенную карточку "
            "случая в пуле юристов после проверки модератором."
        ),
    }
}


class Consent(models.Model):
    class Kind(models.TextChoices):
        PROCESSING_OFFER = "processing_offer", "Обработка и оферта"
        TRANSFER_TO_REVIEWER = "transfer_to_reviewer", "Передача проверяющему"
        TRANSFER_TO_LAWYER = "transfer_to_lawyer", "Передача ведущему юристу"
        PUBLISH_POOL = "publish_pool", "Публикация в пуле"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    text_version = models.CharField(max_length=64)
    case = models.ForeignKey("cases.Case", null=True, on_delete=models.PROTECT, related_name="+")
    # Claim or Offer id, depending on the kind; a plain UUID to avoid cross-app cycles.
    reference_id = models.UUIDField(null=True)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accepted_at"]

    def __str__(self):
        return f"{self.kind} {self.text_version}"
