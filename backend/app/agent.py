"""Bounded tool loop. The model chooses the tools; the tools do the work."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.eligibility import collect_missing
from app.plans import preview, serialize_plan
from app.profile import summary, to_form
from app.tools import TOOLS, execute_tool, summarize_tool

logger = logging.getLogger("escholar.agent")

MAX_ROUNDS = 5

SYSTEM_PROMPT = """You are E-Scholar, a scholarship adviser working from a fictitious catalog.

Follow these rules:
- Call search_opportunities and check_eligibility before you describe any scholarship result.
- Never invent a scholarship, deadline, document, criterion, or eligibility status.
- Report only what check_eligibility returns. Do not decide eligibility yourself.
- For every failed or unknown criterion, say which rule it is, why, and cite the source record id such as SCH-001.
- If any opportunity is undetermined, ask only for the missing facts. Do not ask to save yet.
- Put only eligible opportunities on the shortlist.
- Describe deadlines, documents, and next actions from the tool results.
- Do not call save_application_plan until the student has clearly confirmed in this conversation.
- After the student confirms, call save_application_plan. The tool stores every currently eligible scholarship.
- If a tool returns an error, explain that error in one plain sentence and stop.
- Write short plain sentences. Do not use tables.
"""


class ModelError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UserInputError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(getattr(part, "text", "") or ""))
        return "".join(parts).strip()
    return str(content)


def parse_args(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def read_tool_calls(message) -> list[tuple[str, str, object]]:
    calls = getattr(message, "tool_calls", None) or []
    parsed = []
    for call in calls:
        function = call.function
        if isinstance(function, dict):
            name = function.get("name") or ""
            raw = function.get("arguments") or {}
        else:
            name = function.name
            raw = function.arguments
        parsed.append((call.id, name, raw))
    return parsed


def serialize_assistant(message, text: str) -> dict:
    data = message.model_dump(exclude_none=True) if hasattr(message, "model_dump") else {}
    tool_calls = data.get("tool_calls")
    if not tool_calls and getattr(message, "tool_calls", None):
        tool_calls = []
        for call in message.tool_calls:
            function = call.function
            if isinstance(function, dict):
                name = function.get("name")
                arguments = function.get("arguments")
            else:
                name = function.name
                arguments = function.arguments
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments)
            tool_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
    out = {"role": "assistant", "content": text or ""}
    if tool_calls:
        out["tool_calls"] = tool_calls
    for key in ("reasoning", "reasoning_content", "extra_content"):
        if data.get(key) is not None:
            out[key] = data[key]
    return out


def messages_for_model(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history]


def friendly_model_error(exc: Exception) -> str:
    text = str(exc).lower()
    if any(token in text for token in ("quota", "429", "resource_exhausted", "rate limit")):
        return "The model quota was reached. Wait a moment and retry. Your entries were kept, and nothing was saved."
    if any(token in text for token in ("api key", "api_key", "unauthorized", "401", "403", "permission")):
        return "The model rejected the server API key. Your entries were kept, and nothing was saved."
    logger.exception("model request failed")
    return "The model request failed. Your entries were kept, and nothing was saved. You can retry."


def default_complete(messages: list[dict], tool_choice):
    if not settings.model_configured:
        raise ModelError(
            "No model API key is configured on the server. Add LLM_API_KEY to the backend environment."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ModelError("The model client is not installed on the server.") from exc

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=45.0,
    )
    kwargs = {
        "model": settings.llm_model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": tool_choice,
    }
    if settings.llm_reasoning_effort.strip():
        kwargs["reasoning_effort"] = settings.llm_reasoning_effort.strip()
    try:
        try:
            response = client.chat.completions.create(**kwargs)
        except TypeError:
            kwargs.pop("reasoning_effort", None)
            response = client.chat.completions.create(**kwargs)
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError(friendly_model_error(exc)) from exc
    if not response.choices:
        raise ModelError("The model returned an empty response. Your entries were kept. You can retry.")
    return response.choices[0].message


def explain_results(results: list[dict], plan_id: str | None = None) -> str:
    """Short answer from the rule pass. The cards carry every citation, so this stays bounded."""
    if plan_id:
        return f"The plan is saved. Reopen it with id {plan_id}."
    missing = collect_missing(results)
    eligible = [item for item in results if item["status"] == "eligible"]
    parts = []
    if missing:
        labels = ", ".join(item["label"] for item in missing)
        parts.append(f"Some scholarships are undetermined. Please provide: {labels}.")
        for item in missing[:6]:
            if item["reasons"]:
                parts.append(item["reasons"][0])
    cited = 0
    for result in results:
        for entry in result["failed"]:
            if cited >= 8:
                break
            parts.append(entry["detail"])
            cited += 1
        if cited >= 8:
            break
    if not missing and eligible:
        shown = eligible[:8]
        names = ", ".join(item["name"] for item in shown)
        extra = len(eligible) - len(shown)
        if extra:
            names = f"{names}, and {extra} more"
        parts.append(
            f"Eligible scholarships: {names}. "
            "Review the plan below. Nothing is saved until you confirm."
        )
    elif not missing and results and not eligible:
        parts.append("None of the catalog scholarships are eligible. Each card cites the failed rule and its source record.")
    elif not results:
        parts.append("The catalog has no published scholarships to check.")
    return " ".join(parts)


def _remember(session, text: str, turn_log: list[dict]) -> None:
    session.messages = [
        {"role": "user", "content": "Check the stored profile against published scholarships."},
        {"role": "assistant", "content": text},
    ]
    flag_modified(session, "messages")
    session.tool_log = turn_log
    flag_modified(session, "tool_log")
    session.updated_at = datetime.now(timezone.utc)


def run_catalog(db, session) -> dict:
    """Search and classify in one pass. The model is not called."""
    from app.tools import review_catalog, summarize_tool

    search, checked = review_catalog(db, session.profile)
    session.latest_eligibility = checked["results"]
    flag_modified(session, "latest_eligibility")
    session.confirmed = False
    turn_log = [
        {
            "tool": "search_opportunities",
            "arguments": {},
            "ok": True,
            "summary": summarize_tool("search_opportunities", search),
            "output": search,
        },
        {
            "tool": "check_eligibility",
            "arguments": {},
            "ok": True,
            "summary": summarize_tool("check_eligibility", checked),
            "output": {
                "ok": True,
                "counts": checked["counts"],
                "unknown_ids": checked["unknown_ids"],
            },
        },
    ]
    text = explain_results(checked["results"])
    _remember(session, text, turn_log)
    db.flush()
    return build_payload(db, session, turn_log, text, None)


def confirm_saved(db, session, plan_name: str) -> dict:
    """Save the eligible shortlist from the last check. No second catalog scan and no model call."""
    from app.tools import execute_tool, summarize_tool

    results = list(session.latest_eligibility or [])
    missing = collect_missing(results)
    if missing:
        labels = ", ".join(item["label"] for item in missing)
        raise UserInputError(f"Add the missing information before confirming: {labels}.")
    eligible_ids = [item["opportunity_id"] for item in results if item["status"] == "eligible"]
    if not eligible_ids:
        raise UserInputError("There is no eligible scholarship to save yet.")
    session.confirmed = True
    session.requested_plan_name = (plan_name or "").strip()
    arguments = {"opportunity_ids": eligible_ids, "plan_name": session.requested_plan_name}
    payload = execute_tool(db, session, "save_application_plan", arguments)
    text = payload.get("error") or f"Saved the application plan. The plan id is {payload.get('plan_id')}."
    turn_log = [
        {
            "tool": "save_application_plan",
            "arguments": arguments,
            "ok": bool(payload.get("ok")),
            "summary": summarize_tool("save_application_plan", payload),
            "output": {
                "ok": payload.get("ok"),
                "plan_id": payload.get("plan_id"),
                "saved_ids": payload.get("saved_ids"),
                "ignored_ids": payload.get("ignored_ids"),
                "error": payload.get("error"),
                "already_saved": payload.get("already_saved"),
            },
        }
    ]
    _remember(session, text, turn_log)
    db.flush()
    return build_payload(db, session, turn_log, text, None if payload.get("ok") else text)


def fallback_text(session) -> str:
    results = session.latest_eligibility or []
    missing = collect_missing(results)
    eligible = [item for item in results if item["status"] == "eligible"]
    if session.plan_id:
        return f"The plan is saved. Reopen it with id {session.plan_id}."
    if missing:
        labels = ", ".join(item["label"] for item in missing)
        return f"Some scholarships are undetermined. Please provide: {labels}."
    if eligible:
        names = ", ".join(item["name"] for item in eligible)
        return (
            f"Eligible scholarships: {names}. "
            "Review the plan below. Nothing is saved until you confirm."
        )
    if results:
        return "None of the catalog scholarships are eligible. Each card cites the failed rule and its source record."
    return "The adviser did not return a written summary. Use the tool log and retry if the result looks incomplete."


def user_message(profile: dict, intent: str, plan_name: str | None, eligible_ids: list[str]) -> str:
    shown = json.dumps(summary(profile), ensure_ascii=True)
    if intent == "confirm":
        ids = ", ".join(eligible_ids) if eligible_ids else "none"
        name = plan_name or "the student's scholarship plan"
        return (
            "The student confirmed this application plan and asked you to save it. "
            f"Plan name: {name}. Eligible ids from the latest check: {ids}. "
            "Call save_application_plan now. Do not add ineligible scholarships. "
            f"Stored profile: {shown}"
        )
    if intent == "recheck":
        return (
            "The student updated the profile. Call search_opportunities and check_eligibility again, "
            "then revise the shortlist. Do not save. "
            f"Stored profile: {shown}"
        )
    return (
        "A student submitted this fictitious profile. Call search_opportunities and check_eligibility. "
        "Explain every result with its source record. If a required fact is missing, ask for it. "
        "If scholarships are eligible, propose the plan and ask the student to confirm before any save. "
        f"Do not save yet. Stored profile: {shown}"
    )


def build_payload(db, session, turn_log: list[dict], assistant_text: str, error: str | None) -> dict:
    from app.models import ApplicationPlan

    results = session.latest_eligibility or []
    missing = collect_missing(results)
    eligible = [item for item in results if item["status"] == "eligible"]
    saved_plan = None
    if session.plan_id:
        row = db.get(ApplicationPlan, session.plan_id)
        if row is not None:
            saved_plan = serialize_plan(row)

    awaiting = bool(error is None and session.plan_id is None and not missing and eligible)
    plan_preview = preview(session.profile, eligible) if awaiting else None
    if session.plan_id:
        session.status = "saved"
    elif awaiting:
        session.status = "awaiting_confirmation"
    elif missing:
        session.status = "awaiting_information"
    else:
        session.status = "answered"

    return {
        "session_id": session.id,
        "assistant_message": assistant_text,
        "profile": to_form(session.profile),
        "eligibility": results,
        "missing_fields": missing,
        "awaiting_confirmation": awaiting,
        "plan_preview": plan_preview,
        "saved_plan": saved_plan,
        "tool_log": turn_log,
        "error": error,
        "model": settings.llm_model,
    }


def run_agent(db, session, user_text: str, intent: str, complete) -> dict:
    results = list(session.latest_eligibility or [])
    eligible_ids = [item["opportunity_id"] for item in results if item["status"] == "eligible"]
    if intent == "confirm":
        missing = collect_missing(results)
        if missing:
            labels = ", ".join(item["label"] for item in missing)
            raise UserInputError(f"Add the missing information before confirming: {labels}.")
        if not eligible_ids:
            raise UserInputError("There is no eligible scholarship to save yet.")
        session.confirmed = True
    else:
        session.confirmed = False

    history = list(session.messages or [])
    history.append({"role": "user", "content": user_text})
    turn_log = []
    assistant_text = ""
    error = None
    nudged_save = False
    nudged_tools = False
    rounds = 0
    tool_calls_used = 0
    saved_now = False

    while rounds < MAX_ROUNDS:
        rounds += 1
        tool_choice = "auto"
        if intent == "confirm" and nudged_save and not session.plan_id:
            tool_choice = {"type": "function", "function": {"name": "save_application_plan"}}
        message = complete(messages_for_model(history), tool_choice)
        calls = read_tool_calls(message)
        latest_text = content_to_text(getattr(message, "content", None))
        if latest_text:
            assistant_text = latest_text
        if not calls:
            history.append(serialize_assistant(message, assistant_text))
            checked = any(entry["tool"] == "check_eligibility" and entry["ok"] for entry in turn_log)
            if intent != "confirm" and not checked and not nudged_tools:
                nudged_tools = True
                history.append(
                    {
                        "role": "user",
                        "content": (
                            "You have not checked eligibility yet. Call search_opportunities and "
                            "check_eligibility before you answer the student."
                        ),
                    }
                )
                continue
            if intent == "confirm" and not session.plan_id and not nudged_save:
                nudged_save = True
                history.append(
                    {
                        "role": "user",
                        "content": (
                            "The student already confirmed. Call save_application_plan now with these eligible ids: "
                            + ", ".join(eligible_ids)
                        ),
                    }
                )
                continue
            break

        history.append(serialize_assistant(message, assistant_text))
        for call_id, name, raw_args in calls:
            arguments = {}
            if tool_calls_used >= settings.max_tool_calls:
                payload = {
                    "ok": False,
                    "error": f"Tool-call limit of {settings.max_tool_calls} reached.",
                }
                error = (
                    f"Stopped after {settings.max_tool_calls} tool calls so the request cannot loop without a limit. "
                    "You can retry."
                )
            else:
                tool_calls_used += 1
                arguments = parse_args(raw_args)
                try:
                    payload = execute_tool(db, session, name, arguments)
                except Exception:
                    logger.exception("tool %s failed", name)
                    payload = {"ok": False, "error": f"{name} failed before it could finish."}
            turn_log.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "ok": bool(payload.get("ok")),
                    "summary": summarize_tool(name, payload),
                    "output": payload,
                }
            )
            history.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload)})
            if name == "save_application_plan" and payload.get("ok"):
                saved_now = True
            if error:
                break
        if error or saved_now:
            break
    else:
        error = error or "Stopped because the adviser reached its step limit. You can retry."

    if saved_now and not assistant_text:
        assistant_text = f"Saved the application plan. The plan id is {session.plan_id}."
    if not assistant_text:
        assistant_text = fallback_text(session)

    session.messages = history
    flag_modified(session, "messages")
    session.tool_log = list(session.tool_log or []) + turn_log
    flag_modified(session, "tool_log")
    session.updated_at = datetime.now(timezone.utc)
    db.flush()
    return build_payload(db, session, turn_log, assistant_text, error)
