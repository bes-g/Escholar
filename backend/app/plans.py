"""The plan written to the database is the same plan shown before confirmation."""

from datetime import datetime, timezone


def default_plan_name(profile: dict) -> str:
    name = (profile.get("student_name") or "Student").strip()
    return f"{name}'s scholarship plan"


def next_actions(name: str, deadline: str, documents: list[str]) -> list[str]:
    actions = [f"Collect {document}." for document in documents]
    actions.append(f"Submit {name} before {deadline}.")
    actions.append("Recheck the source record before you send anything.")
    return actions


def plan_item(opportunity_id: str, name: str, deadline: str, documents: list[str]) -> dict:
    docs = list(documents)
    return {
        "opportunity_id": opportunity_id,
        "name": name,
        "deadline": deadline,
        "required_documents": docs,
        "next_actions": next_actions(name, deadline, docs),
        "checklist": [{"item": document, "done": False} for document in docs],
        "source_record_id": opportunity_id,
    }


def plan_item_from_result(result: dict) -> dict:
    return plan_item(
        result["opportunity_id"],
        result["name"],
        result["deadline"],
        result["required_documents"],
    )


def plan_item_from_row(row) -> dict:
    return plan_item(row.id, row.name, row.deadline, list(row.required_documents))


def preview(profile: dict, eligible_results: list[dict], plan_name: str | None = None) -> dict:
    ordered = sorted(eligible_results, key=lambda item: item["opportunity_id"])
    return {
        "plan_name": plan_name or default_plan_name(profile),
        "items": [plan_item_from_result(result) for result in ordered],
    }


def serialize_plan(plan) -> dict:
    created = plan.created_at
    if isinstance(created, datetime):
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        created = created.astimezone(timezone.utc).isoformat()
    return {
        "id": plan.id,
        "plan_name": plan.plan_name,
        "student_name": plan.student_name,
        "profile_summary": plan.profile_summary,
        "opportunities": plan.opportunities,
        "created_at": created,
    }
