import json

from app.catalog import SCHOLARSHIPS
from app.database import SessionLocal
from app.eligibility import evaluate_profile
from app.plans import plan_item_from_result
from app.profile import EXAMPLES, to_internal, validate_profile
from app.tools import check_eligibility, execute_tool, search_opportunities


def _example(example_id: str) -> dict:
    raw = next(item for item in EXAMPLES if item["id"] == example_id)
    return to_internal(raw["profile"])


def test_catalog_has_five_consistent_records(client):
    response = client.get("/api/catalog")
    assert response.status_code == 200
    rows = response.json()["opportunities"]
    assert [row["id"] for row in rows] == ["SCH-001", "SCH-002", "SCH-003", "SCH-004", "SCH-005"]
    for row in rows:
        assert row["deadline"]
        assert 2 <= len(row["criteria"]) <= 6
        assert row["required_documents"]


def test_validation_messages():
    errors = validate_profile(
        {
            "student_name": "",
            "field_of_study": "",
            "gpa": "9",
            "year_of_study": "year two",
            "country": "",
        }
    )
    assert any("Name" in error for error in errors)
    assert any("GPA" in error for error in errors)
    assert any("Year of study" in error for error in errors)
    assert validate_profile(EXAMPLES[0]["profile"]) == []
    missing_year = dict(EXAMPLES[2]["profile"])
    assert validate_profile(missing_year) == []


def test_api_rejects_bad_gpa_without_losing_the_contract(client):
    profile = dict(EXAMPLES[0]["profile"])
    profile["gpa"] = "4.5"
    response = client.post("/api/advise", json={"profile": profile})
    assert response.status_code == 400
    body = response.json()
    assert "GPA" in " ".join(body["errors"])


def test_catalog_check_cites_rules_and_a_confirmed_plan_reopens(client):
    profile = dict(EXAMPLES[2]["profile"])
    first = client.post("/api/advise", json={"profile": profile})
    assert first.status_code == 200
    body = first.json()
    assert body["saved_plan"] is None
    assert body["awaiting_confirmation"] is False
    assert any(field["field"] == "year_of_study" for field in body["missing_fields"])
    assert "year of study" in body["assistant_message"].casefold()
    assert [entry["tool"] for entry in body["tool_log"]] == ["search_opportunities", "check_eligibility"]
    undetermined = next(item for item in body["eligibility"] if item["opportunity_id"] == "SCH-001")
    assert undetermined["status"] == "undetermined"
    assert undetermined["source_record"]["id"] == "SCH-001"
    assert "SCH-001" in undetermined["unknown"][0]["detail"]
    blocked = next(item for item in body["eligibility"] if item["opportunity_id"] == "SCH-002")
    assert blocked["status"] == "ineligible"
    assert "SCH-002" in blocked["failed"][0]["detail"]

    profile["year_of_study"] = "3"
    second = client.post("/api/advise", json={"profile": profile, "session_id": body["session_id"]})
    assert second.status_code == 200
    ready = second.json()
    assert ready["awaiting_confirmation"] is True
    assert ready["saved_plan"] is None
    items = ready["plan_preview"]["items"]
    assert [item["opportunity_id"] for item in items] == ["SCH-001", "SCH-003", "SCH-004"]
    for item in items:
        assert item["deadline"]
        assert item["required_documents"]
        assert item["next_actions"]
        assert item["checklist"]
        assert all(entry["done"] is False for entry in item["checklist"])

    saved = client.post(
        f"/api/sessions/{ready['session_id']}/confirm",
        json={"plan_name": ready["plan_preview"]["plan_name"]},
    )
    assert saved.status_code == 200
    plan = saved.json()["saved_plan"]
    assert [item["opportunity_id"] for item in plan["opportunities"]] == [
        "SCH-001",
        "SCH-003",
        "SCH-004",
    ]
    assert plan["opportunities"] == items
    reopened = client.get(f"/api/plans/{plan['id']}")
    assert reopened.status_code == 200
    assert reopened.json()["opportunities"] == plan["opportunities"]


def test_simulated_failure_is_explicit(client):
    response = client.post(
        "/api/advise",
        json={"profile": EXAMPLES[0]["profile"], "simulate": "model"},
    )
    assert response.status_code == 502
    assert "Simulated model failure" in response.json()["message"]


def test_eligible_ineligible_and_undetermined_profiles(client):
    db = SessionLocal()
    try:
        eligible = check_eligibility(db, _example("eligible"))
        statuses = {item["opportunity_id"]: item["status"] for item in eligible["results"]}
        assert statuses == {
            "SCH-001": "eligible",
            "SCH-002": "ineligible",
            "SCH-003": "eligible",
            "SCH-004": "eligible",
            "SCH-005": "ineligible",
        }
        failed = next(item for item in eligible["results"] if item["opportunity_id"] == "SCH-002")
        assert failed["failed"]
        assert "SCH-002" in failed["failed"][0]["detail"]

        blocked = check_eligibility(db, _example("ineligible"))
        assert {item["status"] for item in blocked["results"]} == {"ineligible"}
        assert all(item["failed"] for item in blocked["results"])

        partial = check_eligibility(db, _example("missing-year"))
        partial_status = {item["opportunity_id"]: item["status"] for item in partial["results"]}
        assert partial_status["SCH-001"] == "undetermined"
        assert partial_status["SCH-003"] == "undetermined"
        assert partial_status["SCH-004"] == "undetermined"
        assert partial_status["SCH-002"] == "ineligible"
        unknown = next(item for item in partial["results"] if item["opportunity_id"] == "SCH-001")
        assert unknown["unknown"][0]["missing_fields"] == ["year_of_study"]
    finally:
        db.close()


def test_failed_rule_overrides_missing_information():
    profile = _example("missing-year")
    profile["gpa"] = 2.0
    result = next(item for item in evaluate_profile(profile, SCHOLARSHIPS) if item["opportunity_id"] == "SCH-001")
    assert result["status"] == "ineligible"
    assert any(item["field"] == "gpa" for item in result["failed"])
    assert any(item["field"] == "year_of_study" for item in result["unknown"])


def test_search_returns_source_records_from_the_database(client):
    db = SessionLocal()
    try:
        payload = search_opportunities(db, "abay")
        assert payload["count"] == 5
        assert payload["opportunities"][0]["source_record_id"] == "SCH-001"
        assert "abay" in payload["opportunities"][0]["keyword_hits"]
    finally:
        db.close()


def test_save_is_refused_until_confirmation_and_matches_the_preview(client):
    from app.models import AdviceSession
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        profile = _example("eligible")
        session = AdviceSession(
            id="ses_save_test",
            profile=profile,
            messages=[],
            tool_log=[],
            latest_eligibility=[],
            confirmed=False,
            status="draft",
            plan_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.commit()

        refused = execute_tool(
            db,
            session,
            "save_application_plan",
            {"opportunity_ids": ["SCH-001"], "plan_name": "Hanna Bekele's scholarship plan"},
        )
        assert refused["ok"] is False
        assert "not confirmed" in refused["error"]

        checked = execute_tool(db, session, "check_eligibility", {})
        session.confirmed = True
        session.requested_plan_name = "Hanna Bekele's scholarship plan"
        saved = execute_tool(
            db,
            session,
            "save_application_plan",
            {"opportunity_ids": ["SCH-002", "SCH-001"], "plan_name": "ignored"},
        )
        db.commit()
        assert saved["ok"] is True
        assert saved["saved_ids"] == ["SCH-001", "SCH-003", "SCH-004"]
        assert "SCH-002" in saved["ignored_ids"]

        stored = saved["plan"]["opportunities"]
        expected = [
            plan_item_from_result(item)
            for item in checked["results"]
            if item["status"] == "eligible"
        ]
        assert [item["opportunity_id"] for item in stored] == [item["opportunity_id"] for item in expected]
        for left, right in zip(stored, expected):
            assert left["deadline"] == right["deadline"]
            assert left["checklist"] == right["checklist"]
            assert left["next_actions"] == right["next_actions"]

        again = execute_tool(db, session, "save_application_plan", {"opportunity_ids": ["SCH-001"]})
        assert again["already_saved"] is True
        assert again["plan_id"] == saved["plan_id"]

        listed = client.get("/api/plans").json()["plans"]
        match = next(item for item in listed if item["id"] == saved["plan_id"])
        assert match["opportunities"] == stored
        assert client.get(f"/api/plans/{saved['plan_id']}").json()["plan_name"] == "Hanna Bekele's scholarship plan"
    finally:
        db.close()


def test_tool_arguments_round_trip():
    raw = json.dumps({"opportunity_ids": ["SCH-001"]})
    assert json.loads(raw)["opportunity_ids"] == ["SCH-001"]
