"""guidance.build_plan(case) and path availability (B4).

Everything here is deterministic code: norms come only from the A3 library, deadlines
only from the A3 calculator, amounts only from the confirmed card. Nothing is generated.
"""

import math

from django.conf import settings

from apps.cases.facts import (
    AMOUNT,
    COMPANY_NAME,
    PAYMENT_DATE,
    SERVICE_DESCRIPTION,
    confirmed_values,
    format_rub,
    parse_amount,
    parse_date,
)

from .deadlines import article_31_deadline
from .destinations import DESTINATIONS
from .norms import select_norms

DISCLAIMER = (
    "Не является юридической консультацией. Нормы и сроки ещё не проверены юристом; "
    "перед подачей документов сверьтесь с текстом закона или обратитесь к специалисту."
)

PATH_TITLES = {
    "self_guided": "Реши сам",
    "claim": "Официальный запрос",
    "specialist": "Обращение к специалисту",
}
PATH_TARGET_STATE = {"self_guided": "self_guided", "claim": "claim_draft", "specialist": "in_pool"}

# Where each path can be chosen from (docs/state-machine.md).
_PATH_FROM = {
    "self_guided": {"card_confirmed"},
    "claim": {"card_confirmed", "self_guided", "no_offers"},
    "specialist": {"card_confirmed", "self_guided", "no_response", "no_offers"},
}

_COMPANY_BLOCKS_CLAIM = {
    "liquidating": (
        "Компания ликвидируется: требование предъявляется ликвидационной комиссии. "
        "Порядок — в плане «Реши сам»."
    ),
    "bankrupt": (
        "Компания в процедуре банкротства: требование заявляется в деле о банкротстве. "
        "Порядок — в плане «Реши сам»."
    ),
    "unavailable": (
        "Не удалось проверить компанию по ИНН. Претензию оформим после успешной проверки; "
        "план «Реши сам» доступен уже сейчас."
    ),
}


def _norm_dto(norm):
    return {
        "id": norm["id"],
        "title": f"{norm['article']}. {norm['title']}",
        "url": norm["url"],
        "verified_by_lawyer": bool(norm["verified_by_lawyer"]),
    }


def _conditions(facts):
    """Classification evidence for the library's only category: prepaid consumer services.

    A paid service is evidenced by a confirmed company and amount; refusal is the user's
    request to get the money back, which is what this service is used for. Article 31
    applicability is never assumed here.
    """
    if facts.get(COMPANY_NAME) and parse_amount(facts.get(AMOUNT)):
        return {"consumer", "paid_service", "refusal"}
    return set()


def claim_norms(case):
    return select_norms(_conditions(confirmed_values(case)))


def response_deadline(case, presented_on):
    """Due date for the company's answer. ``None`` until lawyers approve the policy."""
    return article_31_deadline(presented_on=presented_on, applicable=False, calendar=None)


def path_options(case, company_status):
    options = []
    for path, title in PATH_TITLES.items():
        reason = None
        available = case.state in _PATH_FROM[path]
        if not available:
            reason = "Недоступно на текущем этапе обращения."
        elif path == "claim" and company_status != "active":
            available = False
            reason = _COMPANY_BLOCKS_CLAIM.get(company_status, _COMPANY_BLOCKS_CLAIM["unavailable"])
        elif path == "self_guided" and company_status == "unavailable":
            reason = "Компанию проверить не удалось: план составлен без учёта её статуса."
        options.append(
            {
                "path": path,
                "title": title,
                "available": available,
                "reason": reason,
                "estimated_days": {
                    "self_guided": 1,
                    "claim": max(1, math.ceil(settings.CLAIM_REVIEW_TIMEOUT_HOURS / 24)),
                    "specialist": max(1, math.ceil(settings.OFFERS_WINDOW_HOURS / 24)),
                }[path],
                "price_kopecks": {
                    "self_guided": 0,
                    "claim": settings.PAYMENTS_CLAIM_PRICE_KOPECKS,
                    "specialist": None,
                }[path],
            }
        )
    return options


def build_plan(case, company_status):
    """SelfGuidedPlan for the confirmed card snapshot. Same snapshot -> same plan."""
    facts = confirmed_values(case)
    company = facts.get(COMPANY_NAME) or "компания"
    amount = parse_amount(facts.get(AMOUNT))
    paid_on = parse_date(facts.get(PAYMENT_DATE), today=case.created_at.date())
    service = facts.get(SERVICE_DESCRIPTION)
    money = f"вернуть {format_rub(amount)}" if amount else "вернуть оплаченную сумму"
    norms = [_norm_dto(norm) for norm in select_norms(_conditions(facts))]
    proof = ["Чек или банковская выписка об оплате", "Договор, оферта или скриншот условий"]
    if paid_on:
        proof[0] += f" от {paid_on.strftime('%d.%m.%Y')}"

    steps = [
        {
            "text": "Соберите и сохраните документы: подтверждение оплаты, условия услуги "
            "и переписку с компанией" + (f" по услуге «{service}»." if service else "."),
            "due_on": None,
            "documents": [*proof, "Переписка с компанией"],
            "destination": "Сохраните у себя",
            "norms": [],
        }
    ]
    if company_status == "bankrupt":
        steps.append(
            {
                "text": f"{company} в процедуре банкротства. Найдите сообщение о процедуре и "
                f"арбитражного управляющего и заявите требование {money} в деле о банкротстве.",
                "due_on": None,
                "documents": [*proof, "Заявление о включении требования в реестр"],
                "destination": "Арбитражный управляющий по делу о банкротстве",
                "norms": [],
            }
        )
    elif company_status == "liquidating":
        steps.append(
            {
                "text": f"{company} ликвидируется. Направьте требование {money} "
                "ликвидационной комиссии по адресу из выписки ЕГРЮЛ.",
                "due_on": None,
                "documents": [*proof, "Требование кредитора"],
                "destination": "Ликвидационная комиссия",
                "norms": [],
            }
        )
    else:
        deadline = response_deadline(case, presented_on=None)
        steps.append(
            {
                "text": f"Направьте {company} письменную претензию с требованием {money}. "
                "Отправьте заказным письмом с описью или вручите под подпись на копии."
                + (" Срок ответа уточнит юрист." if deadline.due_on is None else ""),
                "due_on": deadline.due_on.isoformat() if deadline.due_on else None,
                "documents": [*proof, "Претензия в двух экземплярах"],
                "destination": f"{DESTINATIONS['claim']}: {company}",
                "norms": norms,
            }
        )
    steps.append(
        {
            "text": "Если оплачивали картой и услугу не оказали, обратитесь в банк с заявлением "
            "об оспаривании платежа.",
            "due_on": None,
            "documents": [proof[0], "Заявление в банк", "Копия претензии и ответ компании"],
            "destination": DESTINATIONS["bank"],
            "norms": [],
        }
    )
    steps.append(
        {
            "text": "Если компания не ответила или отказала, подайте жалобу в Роспотребнадзор "
            "через портал госуслуг или личный кабинет ведомства.",
            "due_on": None,
            "documents": ["Копия претензии", "Подтверждение отправки", "Ответ компании, если есть"],
            "destination": DESTINATIONS["consumer_authority"],
            "norms": [],
        }
    )
    return {
        "version": case.card_snapshot.version,
        "steps": [{"order": index, **step} for index, step in enumerate(steps, start=1)],
        "disclaimer": DISCLAIMER,
    }
