import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction

from apps.payments import services
from apps.payments.models import Allocation, AllocationKind, Hold, HoldStatus, Purpose

pytestmark = pytest.mark.django_db

CLAIM_PRICE = 149_000


def make_user(name: str):
    user_model = get_user_model()
    # Works with the default user and with the custom user from K2.
    return user_model.objects.create_user(**{user_model.USERNAME_FIELD: name}, password=None)


@pytest.fixture
def owner():
    return make_user("demo-owner")


@pytest.fixture
def lawyer():
    return make_user("demo-lawyer")


@pytest.fixture
def claim_hold(owner):
    return services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), CLAIM_PRICE, "claim-1")


# --- hold ---------------------------------------------------------------------------------


def test_hold_freezes_money_with_demo_provider(claim_hold, owner):
    assert claim_hold.status == HoldStatus.HELD
    assert claim_hold.owner == owner
    assert claim_hold.amount_kopecks == CLAIM_PRICE
    assert claim_hold.provider == "demo"
    assert claim_hold.provider_reference.startswith("demo-")
    assert claim_hold.closed_at is None


def test_hold_same_key_and_input_returns_same_hold(owner):
    reference = uuid.uuid4()
    first = services.hold(owner, Purpose.CLAIM_REVIEW, reference, CLAIM_PRICE, "k")
    second = services.hold(owner, Purpose.CLAIM_REVIEW, str(reference), CLAIM_PRICE, "k")
    assert first.pk == second.pk
    assert Hold.objects.count() == 1


@pytest.mark.parametrize(
    "change",
    [
        {"amount_kopecks": CLAIM_PRICE + 1},
        {"purpose": Purpose.LEGAL_SERVICE},
        {"reference_id": uuid.UUID(int=2)},
    ],
)
def test_hold_same_key_different_input_conflicts(owner, change):
    base = {
        "owner": owner,
        "purpose": Purpose.CLAIM_REVIEW,
        "reference_id": uuid.UUID(int=1),
        "amount_kopecks": CLAIM_PRICE,
        "idempotency_key": "k",
    }
    services.hold(**base)
    with pytest.raises(services.ConflictingKey):
        services.hold(**{**base, **change})


def test_hold_same_key_other_owner_conflicts(owner, lawyer):
    reference = uuid.uuid4()
    services.hold(owner, Purpose.CLAIM_REVIEW, reference, CLAIM_PRICE, "k")
    with pytest.raises(services.ConflictingKey):
        services.hold(lawyer, Purpose.CLAIM_REVIEW, reference, CLAIM_PRICE, "k")


@pytest.mark.parametrize("amount", [0, -1, 1490.0, Decimal("1490"), "149000", True, None])
def test_hold_rejects_non_positive_or_non_integer_amount(owner, amount):
    with pytest.raises(services.InvalidAmount):
        services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), amount, "k")
    assert not Hold.objects.exists()


def test_hold_rejects_unknown_purpose(owner):
    with pytest.raises(services.InvalidPurpose):
        services.hold(owner, "subscription", uuid.uuid4(), CLAIM_PRICE, "k")


@pytest.mark.parametrize("key", ["", "   ", None, "x" * 129])
def test_hold_rejects_bad_key(owner, key):
    with pytest.raises(services.ConflictingKey):
        services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), CLAIM_PRICE, key)


def test_database_rejects_non_positive_amount(owner):
    with pytest.raises(IntegrityError), transaction.atomic():
        Hold.objects.create(
            owner=owner,
            purpose=Purpose.CLAIM_REVIEW,
            reference_id=uuid.uuid4(),
            amount_kopecks=0,
            provider="demo",
            idempotency_key="db-check",
        )


# --- release ------------------------------------------------------------------------------


def test_release_claim_review_pays_reviewer_70_percent(claim_hold, lawyer):
    result = services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=lawyer)

    assert result.hold.status == HoldStatus.RELEASED
    assert result.hold.closed_at is not None
    shares = {a.kind: (a.amount_kopecks, a.recipient) for a in result.allocations}
    assert shares == {
        AllocationKind.REVIEWER: (104_300, lawyer),
        AllocationKind.PLATFORM: (44_700, None),
    }
    assert sum(a.amount_kopecks for a in result.allocations) == CLAIM_PRICE


def test_release_legal_service_keeps_10_percent_fee(owner, lawyer):
    held = services.hold(owner, Purpose.LEGAL_SERVICE, uuid.uuid4(), 1_500_000, "offer-1")
    result = services.release(held, HoldStatus.HELD, "release-1", recipient=lawyer)
    shares = {a.kind: a.amount_kopecks for a in result.allocations}
    assert shares == {AllocationKind.LAWYER: 1_350_000, AllocationKind.PLATFORM: 150_000}


@pytest.mark.parametrize("amount", [1, 3, 7, 99, 101, 149_001, 999_999_999])
@pytest.mark.parametrize("purpose", Purpose.values)
def test_split_is_exact_and_remainder_goes_to_platform(purpose, amount):
    shares = services.split_amount(purpose, amount)
    assert sum(shares.values()) == amount
    assert all(type(value) is int and value >= 0 for value in shares.values())
    lawyer_share = next(v for k, v in shares.items() if k != AllocationKind.PLATFORM)
    bp = 7_000 if purpose == Purpose.CLAIM_REVIEW else 9_000
    assert lawyer_share == amount * bp // 10_000


def test_shares_come_from_settings(settings, owner, lawyer):
    settings.PAYMENTS_REVIEWER_SHARE_BP = 5_000
    held = services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), 1_000, "k")
    result = services.release(held, HoldStatus.HELD, "r", recipient=lawyer)
    assert {a.kind: a.amount_kopecks for a in result.allocations} == {
        AllocationKind.REVIEWER: 500,
        AllocationKind.PLATFORM: 500,
    }


@pytest.mark.parametrize("value", [-1, 10_001, "7000", 70.0])
def test_invalid_share_setting_fails_loudly(settings, value):
    settings.PAYMENTS_REVIEWER_SHARE_BP = value
    with pytest.raises(ImproperlyConfigured):
        services.split_amount(Purpose.CLAIM_REVIEW, 1_000)


def test_release_twice_with_same_key_returns_same_result(claim_hold, lawyer):
    first = services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=lawyer)
    again = services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=lawyer)
    assert {a.pk for a in again.allocations} == {a.pk for a in first.allocations}
    assert Allocation.objects.count() == 2


def test_second_release_with_new_key_is_impossible(claim_hold, lawyer):
    services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=lawyer)
    with pytest.raises(services.InvalidTransition):
        services.release(claim_hold, HoldStatus.HELD, "release-2", recipient=lawyer)
    assert Allocation.objects.count() == 2


def test_release_with_stale_expected_status_fails(claim_hold, lawyer):
    with pytest.raises(services.InvalidTransition):
        services.release(claim_hold, HoldStatus.RELEASED, "release-1", recipient=lawyer)
    claim_hold.refresh_from_db()
    assert claim_hold.status == HoldStatus.HELD


def test_release_of_refunded_hold_fails(claim_hold, lawyer):
    services.refund(claim_hold, "cancelled_before_work", "refund-1")
    with pytest.raises(services.InvalidTransition):
        services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=lawyer)
    assert not Allocation.objects.exists()


def test_release_key_cannot_be_reused_for_another_hold(owner, lawyer):
    first = services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), CLAIM_PRICE, "a")
    second = services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), CLAIM_PRICE, "b")
    services.release(first, HoldStatus.HELD, "same", recipient=lawyer)
    with pytest.raises(services.ConflictingKey):
        services.release(second, HoldStatus.HELD, "same", recipient=lawyer)


def test_payer_cannot_be_recipient(claim_hold, owner):
    with pytest.raises(services.InvalidRecipient):
        services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=owner)
    with pytest.raises(services.InvalidRecipient):
        services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=None)
    claim_hold.refresh_from_db()
    assert claim_hold.status == HoldStatus.HELD


def test_release_uses_database_state_not_stale_instance(claim_hold, lawyer):
    stale = Hold.objects.get(pk=claim_hold.pk)
    services.refund(claim_hold, "dispute_for_owner", "refund-1")
    assert stale.status == HoldStatus.HELD
    with pytest.raises(services.InvalidTransition):
        services.release(stale, HoldStatus.HELD, "release-1", recipient=lawyer)


# --- refund -------------------------------------------------------------------------------


def test_refund_returns_held_money(claim_hold):
    refunded = services.refund(claim_hold, "service_unavailable", "refund-1")
    assert refunded.status == HoldStatus.REFUNDED
    assert refunded.refund_basis == "service_unavailable"
    assert refunded.closed_at is not None
    assert not Allocation.objects.exists()


def test_refund_is_idempotent_by_key(claim_hold):
    first = services.refund(claim_hold, "service_unavailable", "refund-1")
    again = services.refund(claim_hold, "service_unavailable", "refund-1")
    assert first.closed_at == again.closed_at


def test_refund_same_key_different_basis_conflicts(claim_hold):
    services.refund(claim_hold, "service_unavailable", "refund-1")
    with pytest.raises(services.ConflictingKey):
        services.refund(claim_hold, "dispute_for_owner", "refund-1")


def test_released_hold_is_not_refunded(claim_hold, lawyer):
    services.release(claim_hold, HoldStatus.HELD, "release-1", recipient=lawyer)
    with pytest.raises(services.InvalidTransition):
        services.refund(claim_hold, "dispute_for_owner", "refund-1")
    claim_hold.refresh_from_db()
    assert claim_hold.status == HoldStatus.RELEASED


def test_second_refund_with_new_key_is_impossible(claim_hold):
    services.refund(claim_hold, "service_unavailable", "refund-1")
    with pytest.raises(services.InvalidTransition):
        services.refund(claim_hold, "service_unavailable", "refund-2")


def test_refund_rejects_unknown_basis(claim_hold):
    with pytest.raises(services.InvalidBasis):
        services.refund(claim_hold, "because", "refund-1")


# --- provider -----------------------------------------------------------------------------


def test_unknown_provider_fails_loudly(settings, owner):
    settings.PAYMENTS_PROVIDER = "real-bank"
    with pytest.raises(ImproperlyConfigured):
        services.hold(owner, Purpose.CLAIM_REVIEW, uuid.uuid4(), CLAIM_PRICE, "k")
    assert not Hold.objects.exists()
