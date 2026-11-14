"""Date arithmetic requiring an explicit, approved calculation policy."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Deadline:
    due_on: date | None
    reason: str | None
    verified_by_lawyer: bool = False


@dataclass(frozen=True)
class DeadlinePolicy:
    """Explicit policy supplied by a responsible caller; none are preapproved."""

    approved: bool
    period_days: int
    period_type: str
    start_rule: str
    end_rule: str


def calculate_deadline(event_date, *, policy, calendar):
    """Apply the supported policy only when explicitly approved and complete.

    This library does not approve legal rules or provide a holiday calendar.
    The supported arithmetic is an example mechanism, not a legal default:
    calendar days from the next day, with a shift to the next working day.
    ``calendar(day)`` returns True/False or None if the day is unknown.
    """
    if not isinstance(policy, DeadlinePolicy) or policy.approved is not True:
        return Deadline(None, "policy_unconfirmed")
    if (
        policy.period_type != "calendar_days"
        or policy.start_rule != "day_after_event"
        or policy.end_rule != "next_working_day"
    ):
        return Deadline(None, "policy_unsupported")
    if type(event_date) is not date:
        return Deadline(None, "event_date_unknown")
    if (
        not isinstance(policy.period_days, int)
        or isinstance(policy.period_days, bool)
        or policy.period_days < 1
    ):
        return Deadline(None, "period_unknown")
    if calendar is None:
        return Deadline(None, "calendar_unknown")
    try:
        day = event_date + timedelta(days=policy.period_days)
        for _ in range(367):
            working = calendar(day)
            if working is True:
                return Deadline(day, None)
            if working is not False:
                return Deadline(None, "calendar_unknown")
            day += timedelta(days=1)
        return Deadline(None, "calendar_unknown")
    except (OverflowError, ValueError):
        return Deadline(None, "date_out_of_range")


def article_31_deadline(*, presented_on, applicable, calendar, policy_approved=False):
    """Conditional ten-day calculation for the limited Art. 31 requirements.

    ``applicable`` must be explicitly confirmed for the enumerated requirements
    under Arts. 28/29, and ``presented_on`` must be the date of presentation,
    not automatically the dispatch date. Neither selection nor legal review is
    performed by this library. The working-day calendar must cover the due date.
    This rule has not been reviewed by a lawyer.
    """
    if applicable is not True:
        return Deadline(None, "article_31_applicability_unconfirmed")
    policy = DeadlinePolicy(
        approved=policy_approved,
        period_days=10,
        period_type="calendar_days",
        start_rule="day_after_event",
        end_rule="next_working_day",
    )
    return calculate_deadline(presented_on, policy=policy, calendar=calendar)
