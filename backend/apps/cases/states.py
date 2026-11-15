from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"
    default_detail = "Недопустимый переход или устаревшая версия."

    def __init__(self, fields=None):
        super().__init__()
        # Field names only, never values: they reach the client in ``details``.
        self.details = {"fields": list(fields)} if fields else {}


# Domain services check event-specific conditions and lock the case before transition.
TRANSITIONS = {
    "draft": {"clarifying", "card_ready", "closed"},
    "clarifying": {"draft", "closed"},
    "card_ready": {"card_ready", "card_confirmed", "closed"},
    "card_confirmed": {"self_guided", "claim_draft", "in_pool", "closed"},
    "self_guided": {"closed", "claim_draft", "in_pool"},
    "claim_draft": {"claim_in_review", "closed"},
    "claim_in_review": {"claim_in_review", "claim_approved", "claim_edited"},
    "claim_edited": {"claim_approved", "claim_in_review"},
    "claim_approved": {"claim_approved", "claim_in_review", "awaiting_response", "closed"},
    "awaiting_response": {"resolved", "no_response", "closed"},
    "no_response": {"in_pool", "closed"},
    "resolved": {"closed"},
    "in_pool": {"has_offers", "no_offers", "closed"},
    "has_offers": {"offer_accepted", "closed"},
    "no_offers": {"in_pool", "claim_draft", "closed"},
    "offer_accepted": {"in_progress"},
    "in_progress": {"work_submitted"},
    "work_submitted": {"completed", "disputed"},
    "disputed": {"completed", "in_pool", "closed"},
    "completed": {"closed"},
    "closed": set(),
}

INTAKE_STATES = {"draft", "clarifying"}
UPLOAD_STATES = INTAKE_STATES | {"card_ready"}


def transition(case, target):
    if target not in TRANSITIONS.get(case.state, ()):
        raise Conflict()
    case.state = target


def can_close(case):
    # Settlement checks for later payment flows belong to their respective commands.
    return case.state in UPLOAD_STATES | {"card_confirmed", "self_guided", "claim_draft"}


def _claim_draft_actions(case):
    claim = getattr(case, "claim", None)
    if claim is None or not claim.ready:
        return [] if case.ai_state == "thinking" else ["create_claim"]
    if case.ai_state == "thinking":
        return []
    actions = ["confirm_personal_data"]
    if claim.personal_data_confirmed:
        actions.append("submit_claim")
    return actions


def available_actions(case):
    actions = []
    if case.state in INTAKE_STATES and case.ai_state != "thinking":
        actions.append("send_message")
    if case.state in UPLOAD_STATES and case.ai_state != "thinking":
        actions.append("upload_document")
    if case.state == "card_ready":
        actions.append("confirm_card")
    if case.state in {"card_confirmed", "self_guided", "no_response", "no_offers"}:
        actions.append("choose_path")
    if case.state == "claim_draft":
        actions.extend(_claim_draft_actions(case))
    if can_close(case):
        actions.append("close_case")
    return actions
