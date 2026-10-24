"""The three tools. Eligibility and saving are decided here, not by the model."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm.attributes import flag_modified

from app.eligibility import counts, evaluate_profile, profile_was_used
from app.models import ApplicationPlan, Scholarship
from app.plans import default_plan_name, plan_item_from_result, serialize_plan
from app.profile import summary


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_opportunities",
            "description": (
                "Read the scholarship catalog from the database and return every candidate "
                "with its source record. Optional keywords only mark matches. They never drop a record."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "Optional words used to mark relevant records. Leave empty for the full catalog.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_eligibility",
            "description": (
                "Compare the stored student profile with each catalog record using explicit rules in code. "
                "Returns eligible, ineligible, or undetermined, plus passed, failed, and unknown criteria "
                "and the source record. Always checks the full catalog. Do not judge eligibility yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional catalog ids. The tool still classifies every stored scholarship.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_application_plan",
            "description": (
                "Save the confirmed application plan. This succeeds only after the student has confirmed. "
                "The saved deadlines, documents, and checklist come from the catalog. "
                "Only eligible scholarships are stored."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {"type": "string"},
                    "opportunity_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Eligible catalog ids the student approved.",
                    },
                },
                "required": ["opportunity_ids"],
                "additionalProperties": False,
            },
        },
    },
]


def published_scholarships(db):
    return (
        db.query(Scholarship)
        .filter(Scholarship.status == "published")
        .order_by(Scholarship.id)
        .all()
    )


def scholarship_dict(row: Scholarship) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "deadline": row.deadline,
        "summary": row.summary,
        "required_documents": list(row.required_documents),
        "criteria": list(row.criteria),
        "source_url": row.source_url or "",
        "origin": row.origin or "seed",
    }


def source_record(row: Scholarship) -> dict:
    record = scholarship_dict(row)
    record["source_record_id"] = row.id
    return record


def search_opportunities(db, keywords: str = "") -> dict:
    rows = published_scholarships(db)
    terms = [term for term in (keywords or "").casefold().split() if term]
    opportunities = []
    for row in rows:
        blob = " ".join(
            [row.name, row.provider, row.summary, " ".join(rule["label"] for rule in row.criteria)]
        ).casefold()
        opportunities.append({**source_record(row), "keyword_hits": [term for term in terms if term in blob]})
    return {"ok": True, "count": len(opportunities), "opportunities": opportunities}


def _checked(profile: dict, rows, requested: list | None = None) -> dict:
    """One pass over the published rows. Time and result size are linear in rules checked."""
    known = {row.id for row in rows}
    asked = requested or []
    results = evaluate_profile(profile, [scholarship_dict(row) for row in rows])
    return {
        "ok": True,
        "results": results,
        "counts": counts(results),
        "unknown_ids": [item for item in asked if item not in known],
        "profile_used": profile_was_used(profile),
        "note": "Eligibility was computed in application code from the stored profile and catalog rules.",
    }


def review_catalog(db, profile: dict) -> tuple[dict, dict]:
    """Search and classify published scholarships with one query and one rule pass."""
    rows = published_scholarships(db)
    search = {"ok": True, "count": len(rows), "ids": [row.id for row in rows]}
    return search, _checked(profile, rows)


def check_eligibility(db, profile: dict, opportunity_ids: list | None = None) -> dict:
    return _checked(profile, published_scholarships(db), opportunity_ids)


def save_application_plan(db, session, arguments: dict) -> dict:
    if not session.confirmed:
        return {
            "ok": False,
            "error": "Save refused. The student has not confirmed this plan.",
        }
    if session.plan_id:
        existing = db.get(ApplicationPlan, session.plan_id)
        if existing is not None:
            return {
                "ok": True,
                "plan_id": existing.id,
                "already_saved": True,
                "plan": serialize_plan(existing),
            }

    results = list(session.latest_eligibility or [])
    if not results:
        results = evaluate_profile(
            session.profile,
            [scholarship_dict(row) for row in published_scholarships(db)],
        )
    results.sort(key=lambda item: item["opportunity_id"])
    session.latest_eligibility = results
    flag_modified(session, "latest_eligibility")
    eligible = [item for item in results if item["status"] == "eligible"]
    eligible_ids = [item["opportunity_id"] for item in eligible]
    if not eligible_ids:
        return {"ok": False, "error": "There is no eligible scholarship to save."}

    requested = arguments.get("opportunity_ids") or []
    if isinstance(requested, str):
        requested = [requested]
    ignored = sorted(set(requested) - set(eligible_ids))

    items = [plan_item_from_result(item) for item in eligible]
    requested_name = (getattr(session, "requested_plan_name", None) or arguments.get("plan_name") or "").strip()
    plan_name = requested_name or default_plan_name(session.profile)
    plan = ApplicationPlan(
        id=f"plan_{uuid4().hex[:12]}",
        plan_name=plan_name,
        student_name=session.profile.get("student_name") or "Student",
        profile_summary=summary(session.profile),
        opportunities=items,
        created_at=datetime.now(timezone.utc),
        user_id=getattr(session, "user_id", None),
    )
    db.add(plan)
    session.plan_id = plan.id
    session.status = "saved"
    db.flush()
    payload = {
        "ok": True,
        "plan_id": plan.id,
        "saved_ids": eligible_ids,
        "ignored_ids": ignored,
        "plan": serialize_plan(plan),
    }
    if ignored:
        payload["note"] = "Ineligible or unknown ids were ignored. The saved plan matches the eligible shortlist."
    return payload


def execute_tool(db, session, name: str, arguments: dict) -> dict:
    if name == "search_opportunities":
        return search_opportunities(db, arguments.get("keywords") or "")
    if name == "check_eligibility":
        payload = check_eligibility(db, session.profile, arguments.get("opportunity_ids"))
        session.latest_eligibility = payload["results"]
        flag_modified(session, "latest_eligibility")
        return payload
    if name == "save_application_plan":
        return save_application_plan(db, session, arguments)
    return {"ok": False, "error": f"Unknown tool {name}."}


def summarize_tool(name: str, payload: dict) -> str:
    if not payload.get("ok"):
        return payload.get("error") or "The tool failed."
    if name == "search_opportunities":
        return f"Read {payload.get('count', 0)} catalog records from the database."
    if name == "check_eligibility":
        tally = payload.get("counts") or {}
        return (
            f"Eligible {tally.get('eligible', 0)}, "
            f"ineligible {tally.get('ineligible', 0)}, "
            f"undetermined {tally.get('undetermined', 0)}."
        )
    if name == "save_application_plan":
        return f"Saved plan {payload.get('plan_id')}."
    return "Done."
