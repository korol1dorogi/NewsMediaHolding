"""B6/B7: queue, take, timeout, safe reviewer view, approve/edit, owner steps, faulty."""

import json
import threading
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import LawyerProfile
from apps.audit.models import AccessLog
from apps.cases.models import Document
from apps.cases.testing import confirmed_case, make_user
from apps.claims import review, tasks
from apps.claims.models import Claim, ClaimVersion, ReviewAssignment
from apps.payments.models import Allocation, HoldStatus

pytestmark = pytest.mark.django_db

PERSONAL = {
    "full_name": "Анна Сергеевна Демидова",
    "reply_address": "г. Вымышленск, ул. Учебная, д. 5, кв. 12",
    "contract_reference": "DEMO-CONTRACT-77",
}
CONSENT = {"accepted": True, "text_version": "demo-v1"}


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
    LawyerProfile.objects.create(user=user)
    return user


@pytest.fixture
def lawyer2():
    return make_user("lawyer2", role="lawyer")


def submitted_case(owner, django_capture_on_commit_callbacks, *, note=""):
    """Anya's case up to claim_in_review, through the real endpoints."""
    case = confirmed_case(owner, state="claim_draft")
    client = api(owner)
    if note:
        Document.objects.create(
            case=case,
            filename=f"{PERSONAL['full_name']}.txt",
            content_type="text/plain",
            size_bytes=4,
            content=b"demo",
        )
    with patch.object(tasks.make_draft, "delay", side_effect=tasks.make_draft.run):
        with django_capture_on_commit_callbacks(execute=True):
            assert (
                client.post(
                    f"/api/cases/{case.pk}/claim", {"expected_version": case.version}, format="json"
                ).status_code
                == 202
            )
    case.refresh_from_db()
    client.put(
        f"/api/cases/{case.pk}/claim/personal-data",
        {"expected_version": case.version, "data": PERSONAL, "confirmed": True},
        format="json",
    )
    case.refresh_from_db()
    response = client.post(
        f"/api/cases/{case.pk}/claim/submit",
        {"expected_version": case.version, "claim_version": 1, "consent": CONSENT},
        format="json",
    )
    assert response.status_code == 200, response.data
    case.refresh_from_db()
    return case


@pytest.fixture
def case(owner, django_capture_on_commit_callbacks):
    return submitted_case(owner, django_capture_on_commit_callbacks)


def take(client, claim, case):
    case.refresh_from_db()
    return client.post(
        f"/api/lawyer/claims/{claim.pk}/take", {"expected_version": case.version}, format="json"
    )


def action(client, claim, kind, **extra):
    claim.refresh_from_db()
    claim.case.refresh_from_db()
    assignment = claim.assignments.filter(status="active").first()
    body = {
        "expected_version": claim.case.version,
        "assignment_version": assignment.version if assignment else 1,
        "claim_version": claim.current_version,
        **extra,
    }
    return client.post(f"/api/lawyer/claims/{claim.pk}/{kind}", body, format="json")


def owner_post(owner, case, suffix, **extra):
    case.refresh_from_db()
    claim = Claim.objects.get(case=case)
    body = {"expected_version": case.version, "claim_version": claim.current_version, **extra}
    return api(owner).post(f"/api/cases/{case.pk}/claim/{suffix}", body, format="json")


def test_submit_freezes_claim_price_and_records_consent(case, settings):
    claim = Claim.objects.get(case=case)
    assert claim.hold.status == HoldStatus.HELD
    assert claim.hold.amount_kopecks == settings.PAYMENTS_CLAIM_PRICE_KOPECKS
    assert claim.hold.owner_id == case.owner_id
    from apps.privacy.models import Consent

    kinds = set(Consent.objects.filter(user=case.owner).values_list("kind", flat=True))
    assert "transfer_to_reviewer" in kinds


def test_queue_has_no_personal_data(case, lawyer):
    response = api(lawyer).get("/api/lawyer/claims")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert set(items[0]) == {"id", "category", "amount_kopecks", "queued_at", "case_version"}
    assert items[0]["amount_kopecks"] == 6_800_000
    raw = json.dumps(response.json(), ensure_ascii=False)
    for value in [*PERSONAL.values(), "Демидова", str(case.owner_id), str(case.pk)]:
        assert value not in raw


@pytest.mark.parametrize("role", ["user", "moderator", "editor"])
def test_queue_is_lawyers_only(case, role):
    assert api(make_user(f"x-{role}", role=role)).get("/api/lawyer/claims").status_code == 403
    assert APIClient().get("/api/lawyer/claims").status_code == 401


def test_take_then_safe_review_view(case, lawyer):
    claim = Claim.objects.get(case=case)
    response = take(api(lawyer), claim, case)
    assert response.status_code == 200, response.data
    body = response.json()
    assert body["assignment_version"] == 1
    assert body["available_actions"] == ["approve_claim", "edit_claim"]
    assert "{{claimant}}" in body["version"]["template_text"]
    raw = json.dumps(body, ensure_ascii=False)
    for value in [*PERSONAL.values(), "Демидова", "Учебная", "DEMO-CONTRACT-77"]:
        assert value not in raw
    keys = {fact["key"] for fact in body["facts"]}
    assert {"company_name", "amount", "payment_date"} <= keys
    detail = api(lawyer).get(f"/api/lawyer/claims/{claim.pk}")
    assert detail.status_code == 200
    assert AccessLog.objects.filter(actor=lawyer, basis="review_assignment").count() == 2


def test_documents_are_labelled_and_originals_closed(
    owner, lawyer, django_capture_on_commit_callbacks
):
    case = submitted_case(owner, django_capture_on_commit_callbacks, note="file")
    claim = Claim.objects.get(case=case)
    body = take(api(lawyer), claim, case).json()
    assert body["documents"] == [
        {
            "id": body["documents"][0]["id"],
            "label": "Документ 1 (текст)",
            "content_type": "text/plain",
            "safe_redaction_available": False,
        }
    ]
    url = f"/api/cases/{case.pk}/documents/{body['documents'][0]['id']}/content"
    assert api(lawyer).get(url).status_code == 404


def test_mask_hides_personal_data_but_keeps_dates():
    known = review._known(type("C", (), {"personal_data": type("P", (), PERSONAL)()})())
    text = "Анна Демидова, тел. +7 900 123-45-67, оплатила 01.10.2026, договор DEMO-CONTRACT-77"
    masked = review.mask(text, known)
    assert "Демидова" not in masked and "123-45-67" not in masked
    assert "DEMO-CONTRACT-77" not in masked
    assert "01.10.2026" in masked


def test_second_take_is_409(case, lawyer, lawyer2):
    claim = Claim.objects.get(case=case)
    assert take(api(lawyer), claim, case).status_code == 200
    assert take(api(lawyer2), claim, case).status_code == 409
    assert api(lawyer2).get("/api/lawyer/claims").json()["items"] == []
    assert api(lawyer2).get(f"/api/lawyer/claims/{claim.pk}").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_concurrent_take_only_one_wins(owner, django_capture_on_commit_callbacks):
    case = submitted_case(owner, django_capture_on_commit_callbacks)
    claim = Claim.objects.get(case=case)
    lawyers = [make_user(f"racer{i}", role="lawyer") for i in range(2)]
    results = []
    barrier = threading.Barrier(2)

    def attempt(user):
        client = Client()
        client.force_login(user)
        barrier.wait()
        response = client.post(
            f"/api/lawyer/claims/{claim.pk}/take",
            json.dumps({"expected_version": case.version}),
            content_type="application/json",
        )
        results.append(response.status_code)
        connection.close()

    threads = [threading.Thread(target=attempt, args=(user,)) for user in lawyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 409]
    assert ReviewAssignment.objects.filter(claim=claim).count() == 1


def test_timeout_frees_the_claim(case, lawyer, lawyer2, settings):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    ReviewAssignment.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert api(lawyer).get(f"/api/lawyer/claims/{claim.pk}").status_code == 404
    assert len(api(lawyer2).get("/api/lawyer/claims").json()["items"]) == 1
    response = take(api(lawyer2), claim, case)
    assert response.status_code == 200
    assert response.json()["assignment_version"] == 2
    # The expired reviewer cannot act any more.
    assert action(api(lawyer), claim, "approve").status_code == 404


def test_approve_pays_reviewer_and_rates(case, lawyer):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    response = action(api(lawyer), claim, "approve")
    assert response.status_code == 200, response.data
    assert response.json()["state"] == "claim_approved"
    claim.refresh_from_db()
    assert claim.hold.status == HoldStatus.RELEASED
    shares = {a.kind: (a.amount_kopecks, a.recipient_id) for a in Allocation.objects.all()}
    assert shares["reviewer"] == (104_300, lawyer.pk)
    assert LawyerProfile.objects.get(user=lawyer).rating == 1


def test_approve_rejects_stale_versions(case, lawyer):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    for field in ("expected_version", "assignment_version", "claim_version"):
        response = action(api(lawyer), claim, "approve", **{field: 99})
        assert response.status_code == 409
        assert response.data["details"] == {"fields": [field]}


def test_edit_then_owner_accepts(case, lawyer, owner):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    no_comment = action(api(lawyer), claim, "edit", template_text="Новый текст {{claimant}}")
    assert no_comment.status_code == 400
    response = action(
        api(lawyer), claim, "edit", template_text="Новый текст {{claimant}}", comment="Уточнил"
    )
    assert response.status_code == 200
    assert response.json()["state"] == "claim_edited"
    versions = api(owner).get(f"/api/cases/{case.pk}/claim").json()["versions"]
    assert versions[-1]["author"] == "lawyer" and versions[-1]["comment"] == "Уточнил"
    assert PERSONAL["full_name"] in versions[-1]["text"]
    assert ClaimVersion.objects.get(claim=claim, version=2).author_user == lawyer
    # Not paid until the owner accepts the edits.
    claim.refresh_from_db()
    assert claim.hold.status == HoldStatus.HELD
    accepted = owner_post(owner, case, "accept-edits")
    assert accepted.status_code == 200 and accepted.data["state"] == "claim_approved"
    claim.refresh_from_db()
    assert claim.hold.status == HoldStatus.RELEASED


def test_owner_rejects_edits_back_to_queue(case, lawyer, lawyer2, owner):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    action(api(lawyer), claim, "edit", template_text="Правка", comment="Уточнил")
    assert owner_post(owner, case, "reject-edits").status_code == 400
    response = owner_post(owner, case, "reject-edits", comment="Не согласна с суммой")
    assert response.status_code == 200 and response.data["state"] == "claim_in_review"
    assert len(api(lawyer2).get("/api/lawyer/claims").json()["items"]) == 1


def test_mark_sent_and_outcomes(case, lawyer, owner):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    action(api(lawyer), claim, "approve")
    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert owner_post(owner, case, "mark-sent", sent_on=future).status_code == 400
    assert owner_post(owner, case, "mark-sent", sent_on="2020-01-01").status_code == 400
    today = timezone.localdate().isoformat()
    sent = owner_post(owner, case, "mark-sent", sent_on=today)
    assert sent.status_code == 200 and sent.data["state"] == "awaiting_response"
    assert "record_outcome" in sent.data["available_actions"]
    claim_dto = api(owner).get(f"/api/cases/{case.pk}/claim").json()
    assert claim_dto["sent_on"] == today
    # A3 does not compute a deadline without a lawyer-approved policy.
    assert claim_dto["response_due_on"] is None
    case.refresh_from_db()
    body = {"expected_version": case.version, "outcome": "refused", "comment": "Отказали"}
    response = api(owner).post(f"/api/cases/{case.pk}/claim/outcome", body, format="json")
    assert response.status_code == 200
    assert response.data["state"] == "no_response"
    assert "choose_path" in response.data["available_actions"]


def test_outcome_resolved(case, lawyer, owner):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    action(api(lawyer), claim, "approve")
    owner_post(owner, case, "mark-sent", sent_on=date.today().isoformat())
    case.refresh_from_db()
    body = {"expected_version": case.version, "outcome": "resolved", "comment": "Вернули"}
    response = api(owner).post(f"/api/cases/{case.pk}/claim/outcome", body, format="json")
    assert response.data["state"] == "resolved"
    assert response.data["available_actions"] == ["close_case"]


@pytest.mark.parametrize(
    ("suffix", "extra"),
    [
        ("accept-edits", {}),
        ("reject-edits", {"comment": "нет"}),
        ("mark-sent", {"sent_on": "2026-11-15"}),
    ],
)
def test_owner_commands_out_of_order_are_409(case, owner, suffix, extra):
    assert owner_post(owner, case, suffix, **extra).status_code == 409


def test_faulty_claim_rule(case, lawyer, lawyer2):
    claim = Claim.objects.get(case=case)
    take(api(lawyer), claim, case)
    action(api(lawyer), claim, "approve")
    review.mark_faulty(claim.pk)
    claim.refresh_from_db()
    assert claim.faulty and claim.commission_revoked
    assert claim.case.state == "claim_in_review"
    assert LawyerProfile.objects.get(user=lawyer).rating == 0
    # The first lawyer cannot see or take it again; another lawyer reviews for free.
    assert api(lawyer).get("/api/lawyer/claims").json()["items"] == []
    assert take(api(lawyer), claim, case).status_code == 404
    assert take(api(lawyer2), claim, case).status_code == 200
    assert action(api(lawyer2), claim, "approve").status_code == 200
    assert Allocation.objects.filter(kind="reviewer").count() == 1


def test_faulty_only_after_approval(case):
    from apps.cases.states import Conflict

    with pytest.raises(Conflict):
        review.mark_faulty(Claim.objects.get(case=case).pk)


def test_foreign_owner_commands_are_404(case, lawyer):
    stranger = make_user("stranger")
    case.refresh_from_db()
    for suffix in ("accept-edits", "reject-edits", "mark-sent", "outcome"):
        response = api(stranger).post(
            f"/api/cases/{case.pk}/claim/{suffix}",
            {"expected_version": case.version, "claim_version": 1},
            format="json",
        )
        assert response.status_code in (400, 404)
        if response.status_code == 400:
            pytest.fail(f"{suffix}: validation ran before ownership")
