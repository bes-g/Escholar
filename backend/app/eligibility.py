"""Deterministic eligibility. A failed rule beats a missing one."""

from app.profile import summary


def _blank(value) -> bool:
    return value is None or value == ""


def _same(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) is bool(right)
    return str(left).strip().casefold() == str(right).strip().casefold()


def _shown(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def apply_rule(profile: dict, rule: dict) -> tuple[str, str, list[str]]:
    """Return status (passed, failed, unknown), a reason, and missing field names."""
    op = rule["op"]
    label = rule["label"]
    expected = rule["value"]

    if op == "english":
        return _english(profile, label, expected)

    field = rule["field"]
    actual = profile.get(field)
    if _blank(actual):
        pretty = field.replace("_", " ")
        return "unknown", f"{label}: {pretty} was not provided.", [field]

    if op == "eq":
        if _same(actual, expected):
            return "passed", f"{label}: profile has {_shown(actual)}.", []
        return (
            "failed",
            f"{label}: profile has {_shown(actual)}, which does not match {_shown(expected)}.",
            [],
        )

    if op == "gte":
        if float(actual) >= float(expected):
            return "passed", f"{label}: profile value {_shown(actual)} meets the minimum of {_shown(expected)}.", []
        return (
            "failed",
            f"{label}: profile value {_shown(actual)} is below the minimum of {_shown(expected)}.",
            [],
        )

    if op == "lte":
        if float(actual) <= float(expected):
            return "passed", f"{label}: profile value {_shown(actual)} is within the maximum of {_shown(expected)}.", []
        return (
            "failed",
            f"{label}: profile value {_shown(actual)} is above the maximum of {_shown(expected)}.",
            [],
        )

    if op == "in":
        allowed = {_shown(item).casefold() for item in expected}
        if _shown(actual).casefold() in allowed:
            return "passed", f"{label}: {_shown(actual)} is accepted.", []
        listed = ", ".join(_shown(item) for item in expected)
        return "failed", f"{label}: {_shown(actual)} is not one of {listed}.", []

    if op == "between":
        low, high = expected
        number = float(actual)
        if float(low) <= number <= float(high):
            return "passed", f"{label}: profile value {_shown(actual)} is inside {low} to {high}.", []
        return "failed", f"{label}: profile value {_shown(actual)} is outside {low} to {high}.", []

    return "unknown", f"{label}: this rule could not be evaluated.", [field]


def _english(profile: dict, label: str, thresholds: dict) -> tuple[str, str, list[str]]:
    test = profile.get("english_test")
    score = profile.get("english_score")
    if _blank(test):
        return "unknown", f"{label}: an English test and score were not provided.", ["english_test", "english_score"]
    if str(test).casefold() in {"none", "no", "no test"}:
        return (
            "failed",
            f"{label}: no English test was reported. IELTS {thresholds['ielts']} or TOEFL {thresholds['toefl']} is required.",
            [],
        )
    if _blank(score):
        return "unknown", f"{label}: {test} was selected but no score was provided.", ["english_score"]

    score_value = float(score)
    kind = str(test).casefold()
    if kind == "ielts":
        minimum = float(thresholds["ielts"])
        if score_value >= minimum:
            return "passed", f"{label}: IELTS {_shown(score_value)} meets {_shown(minimum)}.", []
        return "failed", f"{label}: IELTS {_shown(score_value)} is below {_shown(minimum)}.", []
    if kind == "toefl":
        minimum = float(thresholds["toefl"])
        if score_value >= minimum:
            return "passed", f"{label}: TOEFL {_shown(score_value)} meets {_shown(minimum)}.", []
        return "failed", f"{label}: TOEFL {_shown(score_value)} is below {_shown(minimum)}.", []
    return "failed", f"{label}: {test} is not an accepted English test.", []


def evaluate_one(profile: dict, scholarship: dict) -> dict:
    passed, failed, unknown = [], [], []
    for rule in scholarship["criteria"]:
        status, detail, missing = apply_rule(profile, rule)
        detail = f"{detail} Source record {scholarship['id']}."
        entry = {
            "id": rule["id"],
            "label": rule["label"],
            "field": rule["field"],
            "detail": detail,
            "source_record_id": scholarship["id"],
            "missing_fields": missing,
        }
        if status == "passed":
            passed.append(entry)
        elif status == "failed":
            failed.append(entry)
        else:
            unknown.append(entry)

    if failed:
        overall = "ineligible"
    elif unknown:
        overall = "undetermined"
    else:
        overall = "eligible"

    return {
        "opportunity_id": scholarship["id"],
        "name": scholarship["name"],
        "provider": scholarship["provider"],
        "deadline": scholarship["deadline"],
        "summary": scholarship["summary"],
        "required_documents": list(scholarship["required_documents"]),
        "status": overall,
        "passed": passed,
        "failed": failed,
        "unknown": unknown,
        "source_record": {
            "id": scholarship["id"],
            "name": scholarship["name"],
            "provider": scholarship["provider"],
            "deadline": scholarship["deadline"],
            "summary": scholarship["summary"],
            "required_documents": list(scholarship["required_documents"]),
            "criteria": scholarship["criteria"],
        },
    }


def evaluate_profile(profile: dict, scholarships: list[dict]) -> list[dict]:
    return [evaluate_one(profile, scholarship) for scholarship in scholarships]


def collect_missing(results: list[dict]) -> list[dict]:
    from app.profile import FORM_FIELDS

    labels = {field["name"]: field["label"] for field in FORM_FIELDS}
    found: dict[str, list[str]] = {}
    for result in results:
        if result["status"] != "undetermined":
            continue
        for item in result["unknown"]:
            for field in item["missing_fields"]:
                reason = f"{result['opportunity_id']}: {item['detail']}"
                bucket = found.setdefault(field, [])
                if reason not in bucket:
                    bucket.append(reason)
    return [
        {"field": field, "label": labels.get(field, field.replace("_", " ")), "reasons": reasons}
        for field, reasons in found.items()
    ]


def counts(results: list[dict]) -> dict:
    tally = {"eligible": 0, "ineligible": 0, "undetermined": 0}
    for result in results:
        tally[result["status"]] = tally.get(result["status"], 0) + 1
    return tally


def profile_was_used(profile: dict) -> dict:
    return summary(profile)
