import json
from datetime import datetime, timezone

from app.agent import run_agent
from app.database import SessionLocal
from app.models import AdviceSession
from app.profile import EXAMPLES, to_internal


class _Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.dumps(arguments)


class _ToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = _Function(name, arguments)


class _Message:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ]
        return data


def _session(profile):
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    session = AdviceSession(
        id=f"ses_{profile['student_name'].split()[0].lower()}_{now.microsecond}",
        profile=profile,
        messages=[],
        tool_log=[],
        latest_eligibility=[],
        confirmed=False,
        status="draft",
        plan_id=None,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()
    return db, session


def test_agent_checks_in_code_and_saves_only_after_confirmation(client):
    profile = to_internal(EXAMPLES[0]["profile"])
    db, session = _session(profile)

    def advise_complete(messages, tool_choice):
        tool_names = [
            call.function.name
            for message in messages
            if message.get("role") == "assistant"
            for call in []
        ]
        del tool_names
        has_check = any(
            message.get("role") == "tool" and "eligible" in message.get("content", "")
            for message in messages
        )
        if not has_check:
            return _Message(
                content="",
                tool_calls=[
                    _ToolCall("call_search", "search_opportunities", {}),
                    _ToolCall("call_check", "check_eligibility", {}),
                ],
            )
        return _Message(
            content="Three scholarships are eligible. Confirm if you want me to save the plan."
        )

    try:
        advised = run_agent(db, session, "Check this profile.", "advise", advise_complete)
        db.commit()
        assert advised["awaiting_confirmation"] is True
        assert advised["saved_plan"] is None
        assert [item["tool"] for item in advised["tool_log"]] == [
            "search_opportunities",
            "check_eligibility",
        ]
        assert "Confirm" in advised["assistant_message"]
        assert [item["opportunity_id"] for item in advised["plan_preview"]["items"]] == [
            "SCH-001",
            "SCH-003",
            "SCH-004",
        ]

        def confirm_complete(messages, tool_choice):
            called_save = any(
                message.get("role") == "tool" and "plan_" in message.get("content", "")
                for message in messages
            )
            if called_save:
                return _Message(content=f"Saved plan {session.plan_id}.")
            return _Message(
                content="",
                tool_calls=[
                    _ToolCall(
                        "call_save",
                        "save_application_plan",
                        {
                            "plan_name": "Hanna Bekele's scholarship plan",
                            "opportunity_ids": ["SCH-001", "SCH-003", "SCH-004"],
                        },
                    )
                ],
            )

        session.requested_plan_name = "Hanna Bekele's scholarship plan"
        saved = run_agent(db, session, "The student confirmed.", "confirm", confirm_complete)
        db.commit()
        assert saved["saved_plan"]["plan_name"] == "Hanna Bekele's scholarship plan"
        assert [item["opportunity_id"] for item in saved["saved_plan"]["opportunities"]] == [
            "SCH-001",
            "SCH-003",
            "SCH-004",
        ]
        assert saved["awaiting_confirmation"] is False
        reopened = client.get(f"/api/plans/{saved['saved_plan']['id']}").json()
        assert reopened["opportunities"] == saved["saved_plan"]["opportunities"]
    finally:
        db.close()


def test_confirm_without_a_shortlist_is_rejected(client):
    profile = to_internal(EXAMPLES[1]["profile"])
    db, session = _session(profile)

    def complete(messages, tool_choice):
        return _Message(
            tool_calls=[_ToolCall("call_check", "check_eligibility", {})],
            content="",
        )

    try:
        # One round of tools, then the loop asks the model again and it would recurse.
        calls = {"n": 0}

        def scripted(messages, tool_choice):
            calls["n"] += 1
            if calls["n"] == 1:
                return complete(messages, tool_choice)
            return _Message(content="None of these scholarships are eligible.")

        result = run_agent(db, session, "Check.", "advise", scripted)
        db.commit()
        assert result["awaiting_confirmation"] is False
        assert result["saved_plan"] is None

        def should_not_run(messages, tool_choice):
            raise AssertionError("save must not be attempted")

        try:
            run_agent(db, session, "Confirm.", "confirm", should_not_run)
            assert False, "expected a rejection"
        except Exception as exc:
            assert "no eligible" in str(exc).lower()
    finally:
        db.close()
