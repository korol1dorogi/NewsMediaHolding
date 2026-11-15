"""S2: endpoint x role x ownership -> expected status, from the S1 access matrix.

Every /api/ route must have a row here: a new endpoint without one fails
``test_every_route_is_in_the_matrix``. State-specific rules (409) live in each app's tests.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.cases.models import Document
from apps.cases.testing import confirmed_case, make_user
from apps.claims.models import Claim

pytestmark = pytest.mark.django_db

PUBLIC = {"api/health", "api/ready", "api/auth/csrf", "api/auth/login"}
SESSION_ONLY = {"api/auth/logout", "api/auth/me"}  # any signed-in role, own session only

# Rule kinds:
#   owner          object of a user's case: owner passes, everyone else 404
#   user_list      the user's own collection: other roles 403
#   lawyer_list    lawyers only: other roles 403
#   lawyer_object  lawyers only (403 for others); a lawyer without an assignment gets 404
MATRIX = {
    "api/cases": {"get": "user_list", "post": "user_list"},
    "api/cases/<uuid:case_id>": {"get": "owner"},
    "api/cases/<uuid:case_id>/messages": {"get": "owner", "post": "owner"},
    "api/cases/<uuid:case_id>/documents": {"post": "owner"},
    "api/cases/<uuid:case_id>/documents/<uuid:document_id>/content": {"get": "owner"},
    "api/cases/<uuid:case_id>/close": {"post": "owner"},
    "api/cases/<uuid:case_id>/card": {"get": "owner"},
    "api/cases/<uuid:case_id>/card/facts/<str:key>": {"patch": "owner"},
    "api/cases/<uuid:case_id>/card/confirm": {"post": "owner"},
    "api/cases/<uuid:case_id>/company": {"get": "owner"},
    "api/cases/<uuid:case_id>/paths": {"get": "owner"},
    "api/cases/<uuid:case_id>/path": {"post": "owner"},
    "api/cases/<uuid:case_id>/plan": {"get": "owner"},
    "api/cases/<uuid:case_id>/claim": {"get": "owner", "post": "owner"},
    "api/cases/<uuid:case_id>/claim/personal-data": {"put": "owner"},
    "api/cases/<uuid:case_id>/claim/submit": {"post": "owner"},
    "api/cases/<uuid:case_id>/claim/accept-edits": {"post": "owner"},
    "api/cases/<uuid:case_id>/claim/reject-edits": {"post": "owner"},
    "api/cases/<uuid:case_id>/claim/mark-sent": {"post": "owner"},
    "api/cases/<uuid:case_id>/claim/outcome": {"post": "owner"},
    "api/lawyer/claims": {"get": "lawyer_list"},
    "api/lawyer/claims/<uuid:claim_id>": {"get": "lawyer_object"},
    "api/lawyer/claims/<uuid:claim_id>/take": {"post": "lawyer_object"},
    "api/lawyer/claims/<uuid:claim_id>/approve": {"post": "lawyer_object"},
    "api/lawyer/claims/<uuid:claim_id>/edit": {"post": "lawyer_object"},
}

ROLES = ("user", "lawyer", "moderator", "editor")


def api_routes(patterns=None, prefix=""):
    for item in patterns if patterns is not None else get_resolver().url_patterns:
        route = prefix + str(item.pattern)
        if isinstance(item, URLResolver):
            yield from api_routes(item.url_patterns, route)
        elif isinstance(item, URLPattern) and route.startswith("api/"):
            yield route


def test_every_route_is_in_the_matrix():
    routes = set(api_routes())
    missing = sorted(routes - set(MATRIX) - PUBLIC - SESSION_ONLY)
    assert not missing, f"Add these routes to the access matrix: {missing}"
    stale = sorted(set(MATRIX) - routes)
    assert not stale, f"Matrix rows without a route: {stale}"


@pytest.fixture
def world():
    owner = make_user("owner")
    case = confirmed_case(owner, state="claim_draft")
    doc = Document.objects.create(
        case=case, filename="x.txt", content_type="text/plain", size_bytes=1, content=b"x"
    )
    claim = Claim.objects.create(case=case, card_version=1)
    users = {role: make_user(f"other-{role}", role=role) for role in ROLES}
    return {"owner": owner, "case": case, "doc": doc, "claim": claim, "users": users}


def url_for(route, world):
    return "/" + (
        route.replace("<uuid:case_id>", str(world["case"].pk))
        .replace("<uuid:document_id>", str(world["doc"].pk))
        .replace("<uuid:claim_id>", str(world["claim"].pk))
        .replace("<str:key>", "company_name")
    )


def call(user, method, url):
    client = APIClient()
    if user is not None:
        client.force_login(user)
    return getattr(client, method)(url, {}, format="json")


CASES = [
    (route, method, rule) for route, methods in MATRIX.items() for method, rule in methods.items()
]


@pytest.mark.parametrize(("route", "method", "rule"), CASES, ids=[f"{m} {r}" for r, m, _ in CASES])
def test_access(world, route, method, rule):
    url = url_for(route, world)
    assert call(None, method, url).status_code == 401, "anonymous must sign in"
    users = world["users"]
    if rule == "owner":
        for role, user in users.items():
            assert call(user, method, url).status_code == 404, f"{role} must not see the case"
        assert call(world["owner"], method, url).status_code not in (401, 403, 404)
    elif rule == "user_list":
        for role in ("lawyer", "moderator", "editor"):
            assert call(users[role], method, url).status_code == 403, role
        assert call(users["user"], method, url).status_code in (200, 400)
    elif rule == "lawyer_list":
        for role in ("user", "moderator", "editor"):
            assert call(users[role], method, url).status_code == 403, role
        assert call(world["owner"], method, url).status_code == 403
        assert call(users["lawyer"], method, url).status_code == 200
    elif rule == "lawyer_object":
        for role in ("user", "moderator", "editor"):
            assert call(users[role], method, url).status_code == 403, role
        assert call(world["owner"], method, url).status_code == 403
        assert call(users["lawyer"], method, url).status_code in (400, 404)
    else:
        pytest.fail(f"Unknown rule {rule}")
