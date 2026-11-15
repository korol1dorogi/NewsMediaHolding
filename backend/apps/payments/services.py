"""hold / release / refund: the interface a real payment provider will get later.

Rules (docs/decisions.md, «Внутренние сервисы»):
- amounts are integer kopecks; shares are basis points from settings; rounding remainder goes
  to the platform, so allocations always sum to the hold amount;
- every operation is atomic and idempotent by its key: the same key and input returns the
  previous result, the same key with a different input is a conflict;
- a hold is released or refunded at most once; a released hold is never refunded automatically.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Allocation, AllocationKind, Hold, HoldStatus, Purpose, RefundBasis
from .providers import get_provider

BASIS_POINTS = 10_000
LAWYER_ROLE = "lawyer"  # accounts.User.Role.LAWYER
_KEY_MAX_LENGTH = 128


class PaymentError(Exception):
    """Base error of the payments service. Messages never contain personal data."""


class InvalidAmount(PaymentError):
    pass


class InvalidPurpose(PaymentError):
    pass


class InvalidRecipient(PaymentError):
    pass


class InvalidBasis(PaymentError):
    pass


class InvalidTransition(PaymentError):
    pass


class ConflictingKey(PaymentError):
    pass


@dataclass(frozen=True)
class ReleaseResult:
    hold: Hold
    allocations: list[Allocation]


def _check_key(key: object) -> str:
    if not isinstance(key, str) or not key.strip() or len(key) > _KEY_MAX_LENGTH:
        raise ConflictingKey("Idempotency key must be a non-empty string up to 128 chars")
    return key


def _check_amount(amount: object) -> int:
    # bool is a subclass of int; floats and Decimals are rejected to keep money exact.
    if type(amount) is not int or amount <= 0:
        raise InvalidAmount("Amount must be a positive integer number of kopecks")
    return amount


def _basis_points(name: str) -> int:
    value = getattr(settings, name)
    if type(value) is not int or not 0 <= value <= BASIS_POINTS:
        raise ImproperlyConfigured(f"{name} must be an integer between 0 and {BASIS_POINTS}")
    return value


def split_amount(purpose: str, amount_kopecks: int) -> dict[str, int]:
    """Split a held amount between the lawyer and the platform. Pure integer arithmetic."""
    amount = _check_amount(amount_kopecks)
    if purpose == Purpose.CLAIM_REVIEW:
        kind = AllocationKind.REVIEWER
        share = amount * _basis_points("PAYMENTS_REVIEWER_SHARE_BP") // BASIS_POINTS
    elif purpose == Purpose.LEGAL_SERVICE:
        kind = AllocationKind.LAWYER
        fee_bp = _basis_points("PAYMENTS_PLATFORM_FEE_BP")
        share = amount * (BASIS_POINTS - fee_bp) // BASIS_POINTS
    else:
        raise InvalidPurpose("Unknown hold purpose")
    return {kind: share, AllocationKind.PLATFORM: amount - share}


def hold(owner, purpose: str, reference_id, amount_kopecks: int, idempotency_key: str) -> Hold:
    """Freeze the user's money. The demo provider confirms instantly."""
    if purpose not in Purpose.values:
        raise InvalidPurpose("Unknown hold purpose")
    amount = _check_amount(amount_kopecks)
    key = _check_key(idempotency_key)
    request = {
        "owner_id": owner.pk,
        "purpose": purpose,
        "reference_id": str(reference_id),
        "amount_kopecks": amount,
    }

    def same_request(existing: Hold) -> Hold:
        stored = {
            "owner_id": existing.owner_id,
            "purpose": existing.purpose,
            "reference_id": str(existing.reference_id),
            "amount_kopecks": existing.amount_kopecks,
        }
        if stored != request:
            raise ConflictingKey("Idempotency key was used for a different hold")
        return existing

    existing = Hold.objects.filter(idempotency_key=key).first()
    if existing:
        return same_request(existing)

    provider = get_provider()
    try:
        with transaction.atomic():
            return Hold.objects.create(
                owner=owner,
                purpose=purpose,
                reference_id=reference_id,
                amount_kopecks=amount,
                provider=provider.name,
                provider_reference=provider.capture(amount),
                idempotency_key=key,
            )
    except IntegrityError:
        # A concurrent call with the same key won the race.
        return same_request(Hold.objects.get(idempotency_key=key))


def release(hold: Hold, expected_status: str, idempotency_key: str, recipient) -> ReleaseResult:
    """Unfreeze money after the work is accepted and record who gets what."""
    key = _check_key(idempotency_key)
    with transaction.atomic():
        locked = Hold.objects.select_for_update().get(pk=hold.pk)
        if locked.release_key == key:
            return ReleaseResult(locked, list(locked.allocations.all()))
        if locked.status != expected_status or locked.status != HoldStatus.HELD:
            raise InvalidTransition("Hold is not in the expected held status")
        if Hold.objects.filter(release_key=key).exists():
            raise ConflictingKey("Idempotency key was used for another release")
        if (
            recipient is None
            or recipient.pk is None
            or recipient.pk == locked.owner_id
            or getattr(recipient, "role", None) != LAWYER_ROLE
        ):
            raise InvalidRecipient("Recipient must be a lawyer, not the payer")

        shares = split_amount(locked.purpose, locked.amount_kopecks)
        get_provider().payout(locked.provider_reference, locked.amount_kopecks)
        allocations = [
            Allocation.objects.create(
                hold=locked,
                kind=kind,
                recipient=None if kind == AllocationKind.PLATFORM else recipient,
                amount_kopecks=amount,
            )
            for kind, amount in shares.items()
        ]
        locked.status = HoldStatus.RELEASED
        locked.release_key = key
        locked.closed_at = timezone.now()
        locked.save(update_fields=["status", "release_key", "closed_at"])
        return ReleaseResult(locked, allocations)


def refund(hold: Hold, basis: str, idempotency_key: str) -> Hold:
    """Return held money to the user. Only a held, not yet released hold can be refunded."""
    if basis not in RefundBasis.values:
        raise InvalidBasis("Unknown refund basis")
    key = _check_key(idempotency_key)
    with transaction.atomic():
        locked = Hold.objects.select_for_update().get(pk=hold.pk)
        if locked.refund_key == key:
            if locked.refund_basis != basis:
                raise ConflictingKey("Idempotency key was used with a different basis")
            return locked
        if locked.status != HoldStatus.HELD:
            raise InvalidTransition("Only a held hold can be refunded")
        if Hold.objects.filter(refund_key=key).exists():
            raise ConflictingKey("Idempotency key was used for another refund")

        get_provider().refund(locked.provider_reference, locked.amount_kopecks)
        locked.status = HoldStatus.REFUNDED
        locked.refund_key = key
        locked.refund_basis = basis
        locked.closed_at = timezone.now()
        locked.save(update_fields=["status", "refund_key", "refund_basis", "closed_at"])
        return locked
