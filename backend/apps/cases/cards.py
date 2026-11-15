from uuid import UUID

from rest_framework import serializers

from .models import Fact


def card_facts(case):
    return [
        {
            "key": fact.key,
            "required": fact.required,
            "value": fact.value or None,
            "status": fact.status,
            "source": fact.source,
            "source_quote": fact.source_quote or None,
        }
        for fact in case.facts.order_by("key")
    ]


def card_data(case):
    if case.card_confirmed_at is None:
        facts = card_facts(case)
        timestamp = None
        version = case.card_version
    else:
        snapshot = case.card_snapshot
        facts = snapshot.facts
        timestamp = serializers.DateTimeField().to_representation(snapshot.confirmed_at)
        version = snapshot.version
    missing = [row["key"] for row in facts if row["required"] and not row["value"]]
    from apps.pool.similar import similar_cases

    return {
        "version": version,
        "confirmed_at": timestamp,
        "facts": facts,
        "missing_required_fields": missing,
        "similar_cases": similar_cases(case),
    }


def verified_source(case, proposal):
    source = proposal.get("source")
    quote = proposal.get("source_quote")
    if not isinstance(source, dict) or not isinstance(quote, str) or not quote.strip():
        return None
    try:
        source_id = UUID(str(source.get("id")))
    except ValueError:
        return None
    version = source.get("source_version")
    if type(version) is not int or version < 1:
        return None
    kind = source.get("kind")
    if kind == "message" and version == 1:
        text = (
            case.messages.filter(pk=source_id, author="user").values_list("text", flat=True).first()
        )
    elif kind == "document":
        content = (
            case.documents.filter(pk=source_id, source_version=version, content_type="text/plain")
            .values_list("content", flat=True)
            .first()
        )
        text = bytes(content).decode("utf-8") if content is not None else None
    else:
        return None
    if text is not None and quote in text:
        return {"kind": kind, "id": str(source_id), "source_version": version}
    return None


def apply_proposals(case, proposals):
    """Called under B1's case lock, after checking the intake job version."""
    changed = False
    for proposal in proposals:
        key = proposal["key"]
        required = proposal["required"]
        if not isinstance(key, str) or not key.strip() or not isinstance(required, bool):
            raise ValueError("Invalid proposed fact")
        source = None
        value = proposal.get("value")
        if proposal.get("status") == Fact.Status.FOUND and isinstance(value, str) and value.strip():
            source = verified_source(case, proposal)
        attrs = {
            "required": required,
            "status": Fact.Status.FOUND if source else Fact.Status.NOT_FOUND,
            "value": value if source else "",
            "source": source,
            "source_quote": proposal["source_quote"] if source else "",
        }
        fact, created = Fact.objects.get_or_create(case=case, key=key, defaults=attrs)
        if created:
            changed = True
        elif fact.status != Fact.Status.USER_EDITED and any(
            getattr(fact, field) != item for field, item in attrs.items()
        ):
            for field, item in attrs.items():
                setattr(fact, field, item)
            fact.save(update_fields=attrs)
            changed = True
    return changed
