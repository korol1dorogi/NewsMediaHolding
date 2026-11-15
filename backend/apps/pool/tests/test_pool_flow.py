"""B9/B10/B11: pool card, moderation, offers, choosing a lawyer, work and acceptance."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import LawyerProfile
from apps.audit.models import AccessLog
from apps.cases.models import Document
from apps.cases.testing import ANYA_FACTS, confirmed_case, make_user
from apps.claims.models import Claim, ExcludedReviewer, ReviewAssignment
from apps.payments.models import Allocation, HoldStatus
from apps.pool import services
from apps.pool.models import Offer, PoolCard, WorkSubmission
from apps.pool.similar import similar_cases

pytestmark = pytest.mark.django_db

CONSENT = {"accepted": True, "text_version": "demo-v1"}
PERSONAL = {
    "full_name": "Анна Сергеевна Демидова",
    "reply_address": "г. Вымышленск, ул. Учебная, д. 5",
    "contract_reference": "DEMO-CONTRACT-77",
}
OFFER = {
    "scope": "Подготовлю иск и представлю интересы",
    "duration_days": 14,
    "price_kopecks": 1_500_000,
    "included": ["Иск", "Расчёт неустойки"],
    "excluded": ["Апелляция"],
}


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def owner():
    return make_user("owner")


@pytest.fixture
def lawyer():
    user = make_user("lawyer1", role="lawyer")
    LawyerProfile.objects.create(user=user, rating=3)
    return user


@pytest.fixture
def lawyer2():
    user = make_user("lawyer2", role="lawyer")
    LawyerProfile.objects.create(user=user, rating=7)
    return user


def in_pool_case(owner, facts=None):
    case = confirmed_case(
        owner, {**ANYA_FACTS, "city": "Вымышленск", **(facts or {})}, state="in_pool"
    )
    case.path = "specialist"
    case.save()
    return case


def publish(owner, case):
    case.refresh_from_db()
    return api(owner).post(
        f"/api/cases/{case.pk}/pool",
        {"expected_version": case.version, "consent": CONSENT},
        format="json",
    )


def published(owner, case):
    assert publish(owner, case).status_code == 202
    card = PoolCard.objects.get(case=case)
    services.approve(card)
    return card


def offer(lawyer, card, **extra):
    return api(lawyer).post(f"/api/lawyer/pool/{card.pk}/offers", {**OFFER, **extra}, format="json")


def accept(owner, case, offer_id, **extra):
    case.refresh_from_db()
    body = {"expected_version": case.version, "consent": CONSENT, **extra}
    return api(owner).post(f"/api/cases/{case.pk}/offers/{offer_id}/accept", body, format="json")


# --- B9 --------------------------------------------------------------------------------


def test_publish_creates_pending_card_once(owner):
    case = in_pool_case(owner)
    response = publish(owner, case)
    assert response.status_code == 202
    assert response.data["moderation_status"] == "pending"
    again = publish(owner, case)
    assert again.status_code == 202 and again.data["id"] == response.data["id"]
    assert PoolCard.objects.count() == 1
    detail = api(owner).get(f"/api/cases/{case.pk}").json()
    assert detail["pool"] == {
        "id": response.data["id"],
        "moderation_status": "pending",
        "rejection_reason": None,
    }
    assert "publish_pool" not in detail["available_actions"]


def test_publish_only_on_specialist_path(owner):
    case = confirmed_case(owner)
    assert publish(owner, case).status_code == 409


def test_unapproved_card_is_hidden(owner, lawyer):
    case = in_pool_case(owner)
    publish(owner, case)
    card = PoolCard.objects.get(case=case)
    assert api(lawyer).get("/api/lawyer/pool").json()["items"] == []
    assert api(lawyer).get(f"/api/lawyer/pool/{card.pk}").status_code == 404
    assert offer(lawyer, card).status_code == 404
    services.reject(card, "Нужна очистка")
    assert api(lawyer).get("/api/lawyer/pool").json()["items"] == []
    status = api(owner).get(f"/api/cases/{case.pk}").json()["pool"]
    assert status["moderation_status"] == "rejected" and status["rejection_reason"]


def test_pool_has_no_personal_data_and_no_documents(owner, lawyer):
    case = in_pool_case(owner)
    from apps.pool.models import CaseContact

    CaseContact.objects.create(case=case, confirmed_at=timezone.now(), **PERSONAL)
    Document.objects.create(
        case=case,
        filename="Демидова-чек.txt",
        content_type="text/plain",
        size_bytes=4,
        content=b"demo",
    )
    card = published(owner, case)
    listing = api(lawyer).get("/api/lawyer/pool").json()
    detail = api(lawyer).get(f"/api/lawyer/pool/{card.pk}").json()
    assert listing["items"] == [detail]
    raw = json.dumps(listing, ensure_ascii=False)
    for value in [
        *PERSONAL.values(),
        "Демидова",
        "Учебная",
        str(case.pk),
        str(case.owner_id),
        "68 000",
    ]:
        assert value not in raw
    assert set(detail) == {
        "id",
        "category",
        "description",
        "city",
        "amount_range",
        "company",
        "actions_taken",
        "similar_cases",
    }
    assert detail["amount_range"] == {"min_kopecks": 5_000_000, "max_kopecks": 9_999_999}
    assert detail["city"] == "Вымышленск"


def test_personal_data_in_city_is_not_published(owner, lawyer):
    case = in_pool_case(owner, {"city": "звоните +7 900 123-45-67"})
    card = published(owner, case)
    assert card.city == services.NO_CITY


def test_pool_filters(owner, lawyer):
    card = published(owner, in_pool_case(owner))
    get = lambda **q: api(lawyer).get("/api/lawyer/pool", q).json()["items"]  # noqa: E731
    assert len(get(category="prepaid_services")) == 1
    assert get(category="housing") == []
    assert len(get(city="вымышленск")) == 1
    assert get(city="Другой") == []
    assert len(get(min_kopecks=6_000_000, max_kopecks=7_000_000)) == 1
    assert get(min_kopecks=10_000_000) == []
    assert get(max_kopecks=4_000_000) == []
    assert api(lawyer).get("/api/lawyer/pool", {"min_kopecks": "abc"}).status_code == 400
    assert card


# --- B10: offers -----------------------------------------------------------------------


def test_offers_sorted_by_rating_and_one_per_lawyer(owner, lawyer, lawyer2):
    case = in_pool_case(owner)
    card = published(owner, case)
    assert offer(lawyer, card).status_code == 201
    case.refresh_from_db()
    assert case.state == "has_offers"
    assert offer(lawyer, card).status_code == 409
    assert offer(lawyer2, card, price_kopecks=1_200_000).status_code == 201
    items = api(owner).get(f"/api/cases/{case.pk}/offers").json()["items"]
    assert [item["price_kopecks"] for item in items] == [1_200_000, 1_500_000]
    assert items[0]["lawyer_label"].startswith("Юрист ")


def test_offer_window_closes(owner, lawyer):
    case = in_pool_case(owner)
    card = published(owner, case)
    PoolCard.objects.update(offers_until=timezone.now() - timedelta(seconds=1))
    assert offer(lawyer, card).status_code == 404
    case.refresh_from_db()
    assert case.state == "no_offers"
    assert "choose_path" in api(owner).get(f"/api/cases/{case.pk}").json()["available_actions"]


def test_at_most_five_offers_shown(owner):
    case = in_pool_case(owner)
    card = published(owner, case)
    for index in range(7):
        assert offer(make_user(f"l{index}", role="lawyer"), card).status_code == 201
    assert len(api(owner).get(f"/api/cases/{case.pk}/offers").json()["items"]) == 5


def reviewed_case(owner, reviewer, *, faulty=False, outcome=""):
    case = in_pool_case(owner)
    claim = Claim.objects.create(
        case=case,
        card_version=1,
        current_version=1,
        reviewer=reviewer,
        faulty=faulty,
        outcome=outcome,
        sent_on=timezone.localdate() if outcome else None,
    )
    ReviewAssignment.objects.create(
        claim=claim, lawyer=reviewer, version=1, status="done", expires_at=timezone.now()
    )
    if faulty:
        ExcludedReviewer.objects.create(claim=claim, lawyer=reviewer)
    return case


@pytest.mark.parametrize(
    ("faulty", "outcome", "allowed"),
    [
        (False, "refused", True),
        (False, "no_response", True),
        (False, "resolved", False),
        (False, "", False),
        (True, "refused", False),
    ],
)
def test_rule_for_the_reviewing_lawyer(owner, lawyer, lawyer2, faulty, outcome, allowed):
    case = reviewed_case(owner, lawyer, faulty=faulty, outcome=outcome)
    card = published(owner, case)
    assert offer(lawyer, card).status_code == (201 if allowed else 409)
    assert offer(lawyer2, card).status_code == 201  # other lawyers are not restricted


# --- B10: accept, reveal, work ---------------------------------------------------------


def test_accept_reveals_data_only_to_chosen_lawyer(owner, lawyer, lawyer2):
    case = in_pool_case(owner)
    card = published(owner, case)
    first = offer(lawyer, card).data["id"]
    second = offer(lawyer2, card).data["id"]
    assert api(lawyer).get(f"/api/lawyer/cases/{case.pk}").status_code == 404
    doc = Document.objects.create(
        case=case, filename="чек.txt", content_type="text/plain", size_bytes=4, content=b"demo"
    )
    content = f"/api/cases/{case.pk}/documents/{doc.pk}/content"
    assert api(lawyer).get(content).status_code == 404

    assert accept(owner, case, first).status_code == 400  # personal data required
    response = accept(owner, case, first, personal_data=PERSONAL)
    assert response.status_code == 200, response.data
    assert response.data["state"] == "offer_accepted"
    assert accept(owner, case, second, personal_data=PERSONAL).status_code == 409

    detail = api(lawyer).get(f"/api/lawyer/cases/{case.pk}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["personal_data"] == PERSONAL
    assert body["accepted_offer"]["accepted"] is True
    assert body["case"]["available_actions"] == ["start_work"]
    assert [d["filename"] for d in body["documents"]] == ["чек.txt"]
    assert api(lawyer).get(content).status_code == 200
    assert api(lawyer2).get(f"/api/lawyer/cases/{case.pk}").status_code == 404
    assert api(lawyer2).get(content).status_code == 404
    assert AccessLog.objects.filter(actor=lawyer, basis="accepted_offer").count() == 1
    hold = Offer.objects.get(pk=first).assignment.hold
    assert hold.status == HoldStatus.HELD and hold.amount_kopecks == 1_500_000
    listing = api(lawyer).get("/api/lawyer/cases").json()["items"]
    assert [item["id"] for item in listing] == [str(case.pk)]


def test_claim_personal_data_is_reused(owner, lawyer):
    case = in_pool_case(owner)
    from apps.claims.models import ClaimPersonalData

    claim = Claim.objects.create(
        case=case, card_version=1, current_version=1, personal_data_confirmed=True
    )
    ClaimPersonalData.objects.create(claim=claim, confirmed_at=timezone.now(), **PERSONAL)
    card = published(owner, case)
    offer_id = offer(lawyer, card).data["id"]
    assert accept(owner, case, offer_id).status_code == 200
    assert api(lawyer).get(f"/api/lawyer/cases/{case.pk}").json()["personal_data"] == PERSONAL


def start_and_submit(owner, lawyer, lawyer_case):
    lawyer_case.refresh_from_db()
    client = api(lawyer)
    started = client.post(
        f"/api/lawyer/cases/{lawyer_case.pk}/start",
        {"expected_version": lawyer_case.version},
        format="json",
    )
    assert started.status_code == 200 and started.data["available_actions"] == ["submit_work"]
    lawyer_case.refresh_from_db()
    submitted = client.post(
        f"/api/lawyer/cases/{lawyer_case.pk}/submit-work",
        {"expected_version": lawyer_case.version, "text": "Иск подан, копия во вложении."},
        format="json",
    )
    assert submitted.status_code == 200 and submitted.data["state"] == "work_submitted"


@pytest.fixture
def working_case(owner, lawyer):
    case = in_pool_case(owner)
    card = published(owner, case)
    accept(owner, case, offer(lawyer, card).data["id"], personal_data=PERSONAL)
    start_and_submit(owner, lawyer, case)
    case.refresh_from_db()
    return case


def test_owner_accepts_work_and_lawyer_is_paid(owner, lawyer, working_case):
    detail = api(owner).get(f"/api/cases/{working_case.pk}").json()
    assert detail["work"]["version"] == 1
    assert detail["available_actions"] == ["accept_work"]
    stale = {"expected_version": working_case.version, "work_version": 2}
    assert (
        api(owner)
        .post(f"/api/cases/{working_case.pk}/work/accept", stale, format="json")
        .status_code
        == 409
    )
    body = {"expected_version": working_case.version, "work_version": 1}
    response = api(owner).post(f"/api/cases/{working_case.pk}/work/accept", body, format="json")
    assert response.status_code == 200 and response.data["state"] == "completed"
    shares = {a.kind: a.amount_kopecks for a in Allocation.objects.all()}
    assert shares == {"lawyer": 1_350_000, "platform": 150_000}
    assert LawyerProfile.objects.get(user=lawyer).rating == 4
    # The lawyer's access ends with the case.
    assert api(lawyer).get(f"/api/lawyer/cases/{working_case.pk}").status_code == 404


def test_auto_acceptance_after_three_days(owner, lawyer, working_case, settings):
    WorkSubmission.objects.update(accept_by=timezone.now() - timedelta(seconds=1))
    services.sweep()
    working_case.refresh_from_db()
    assert working_case.state == "completed"
    submission = WorkSubmission.objects.get()
    assert submission.auto_accepted is True
    assert Allocation.objects.filter(kind="lawyer").count() == 1


def test_work_is_not_auto_accepted_early(working_case):
    services.sweep()
    working_case.refresh_from_db()
    assert working_case.state == "work_submitted"
    assert WorkSubmission.objects.get().accept_by - timezone.now() > timedelta(days=2, hours=23)


# --- B11 -------------------------------------------------------------------------------


def test_similar_cases_counts_only_confirmed_by_inn(owner):
    mine = in_pool_case(owner)
    for index, city in enumerate(["Вымышленск", "Учебноград", "Учебноград"]):
        confirmed_case(make_user(f"o{index}"), {**ANYA_FACTS, "city": city})
    unconfirmed = confirmed_case(make_user("u"), ANYA_FACTS)
    unconfirmed.card_confirmed_at = None
    unconfirmed.save()
    confirmed_case(make_user("other-inn"), {**ANYA_FACTS, "company_inn": "7707083893"})
    result = similar_cases(mine)
    assert result == {"count": 3, "cities_count": 2, "period_months": 1}
    card = api(owner).get(f"/api/cases/{mine.pk}/card").json()
    assert card["similar_cases"] == result
    raw = json.dumps(card, ensure_ascii=False)
    assert "Учебноград" not in raw


def test_similar_cases_hidden_without_confirmed_card(owner):
    case = confirmed_case(owner)
    case.card_confirmed_at = None
    case.save()
    assert similar_cases(case) is None
