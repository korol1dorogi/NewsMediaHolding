"""D2: idempotent fictional demo data."""

import pytest
from django.core.management import call_command

from apps.cases.models import Case
from apps.cases.testing import confirmed_case, make_user
from apps.claims.models import Claim
from apps.claims.review import queue_for
from apps.pool.models import PoolCard
from apps.pool.services import visible_cards
from apps.pool.similar import similar_cases

pytestmark = pytest.mark.django_db


def test_seed_with_data_is_idempotent():
    call_command("seed_demo", "--with-data")
    call_command("seed_demo", "--with-data")
    crowd = Case.objects.filter(owner__username="demo_crowd")
    assert crowd.count() == 33
    assert crowd.filter(owner__is_demo=True).count() == 33
    assert Claim.objects.count() == 3
    assert PoolCard.objects.filter(moderation_status="approved").count() == 3


def test_demo_data_fills_queue_pool_and_similar_cases():
    call_command("seed_demo", "--with-data")
    lawyer = make_user("lawyer", role="lawyer")
    assert len(queue_for(lawyer)) == 3
    assert visible_cards({}).count() == 3
    anya = confirmed_case(make_user("anya"))
    result = similar_cases(anya)
    assert result["count"] == 33
    assert result["cities_count"] == 5


def test_crowd_cannot_sign_in():
    call_command("seed_demo", "--with-data")
    from django.contrib.auth import get_user_model

    assert not get_user_model().objects.get(username="demo_crowd").has_usable_password()
