"""Profile parsing. The form schema here is also sent to the React app."""

FIELDS_OF_STUDY = [
    "Computer Science",
    "Engineering",
    "Mathematics",
    "Public Health",
    "Agriculture",
    "Environmental Science",
    "History",
    "Archaeology",
    "Heritage Studies",
    "Law",
    "Business",
    "Education",
]

FIELD_ALIASES = {
    "cs": "Computer Science",
    "computer science": "Computer Science",
    "comp sci": "Computer Science",
    "software engineering": "Engineering",
    "electrical engineering": "Engineering",
    "mechanical engineering": "Engineering",
    "civil engineering": "Engineering",
    "engineering": "Engineering",
    "math": "Mathematics",
    "maths": "Mathematics",
    "mathematics": "Mathematics",
    "public health": "Public Health",
    "agriculture": "Agriculture",
    "environmental science": "Environmental Science",
    "history": "History",
    "archaeology": "Archaeology",
    "archeology": "Archaeology",
    "heritage studies": "Heritage Studies",
    "law": "Law",
    "business": "Business",
    "education": "Education",
}

DEGREE_ALIASES = {
    "bachelor": "Bachelor",
    "bachelors": "Bachelor",
    "bachelor's": "Bachelor",
    "undergraduate": "Bachelor",
    "bsc": "Bachelor",
    "master": "Master",
    "masters": "Master",
    "master's": "Master",
    "graduate": "Master",
    "msc": "Master",
    "phd": "PhD",
    "ph.d": "PhD",
    "doctorate": "PhD",
    "high school": "High school",
}

LEVEL_DEGREE = {
    "high_school": "High school",
    "bsc": "Bachelor",
    "masters": "Master",
    "phd": "PhD",
}

LEVELS = [
    {"id": "high_school", "label": "High school", "detail": "Grades 9–12"},
    {"id": "bsc", "label": "University — BSc", "detail": "Bachelor's degree"},
    {"id": "masters", "label": "University — Master's", "detail": "Master's degree"},
    {"id": "phd", "label": "University — PhD", "detail": "Doctoral study"},
]

STREAMS = ["Natural science", "Social science", "Other"]
GRADES = ["9", "10", "11", "12"]

FORM_FIELDS = [
    {
        "name": "student_name",
        "label": "Name",
        "kind": "text",
        "required": True,
        "wide": True,
        "hint": "Use a fictitious name. Do not enter a real person's details.",
    },
    {
        "name": "field_of_study",
        "label": "Field of study",
        "kind": "select",
        "required": True,
        "wide": True,
        "options": FIELDS_OF_STUDY,
    },
    {
        "name": "gpa",
        "label": "GPA",
        "kind": "number",
        "required": True,
        "wide": False,
        "step": "0.01",
        "min": 0,
        "max": 4,
        "hint": "Use a 0.0 to 4.0 scale.",
    },
    {
        "name": "year_of_study",
        "label": "Year of study",
        "kind": "number",
        "required": False,
        "wide": False,
        "step": "1",
        "min": 1,
        "max": 7,
        "hint": "Leave blank if you do not know it yet. The adviser will ask.",
    },
    {
        "name": "country",
        "label": "Country of residence",
        "kind": "select",
        "required": True,
        "wide": False,
        "options": ["Ethiopia", "Kenya", "Uganda", "Nigeria", "Other"],
    },
    {
        "name": "citizenship",
        "label": "Citizenship",
        "kind": "select",
        "required": False,
        "wide": False,
        "options": ["Ethiopian", "Kenyan", "Ugandan", "Nigerian", "Other"],
    },
    {
        "name": "degree_level",
        "label": "Degree level",
        "kind": "select",
        "required": False,
        "wide": False,
        "options": ["Bachelor", "Master"],
    },
    {
        "name": "gender",
        "label": "Gender",
        "kind": "select",
        "required": False,
        "wide": False,
        "options": ["Female", "Male", "Other"],
    },
    {
        "name": "financial_need",
        "label": "Financial need",
        "kind": "select",
        "required": False,
        "wide": False,
        "options": [
            {"value": "yes", "label": "Yes, I need funding"},
            {"value": "no", "label": "No"},
        ],
    },
    {
        "name": "english_test",
        "label": "English test",
        "kind": "select",
        "required": False,
        "wide": False,
        "options": [
            {"value": "IELTS", "label": "IELTS"},
            {"value": "TOEFL", "label": "TOEFL"},
            {"value": "None", "label": "No English test"},
        ],
    },
    {
        "name": "english_score",
        "label": "English score",
        "kind": "number",
        "required": False,
        "wide": False,
        "step": "0.5",
        "min": 0,
        "max": 120,
        "hint": "IELTS is out of 9. TOEFL is out of 120.",
    },
]


def _spec(**kwargs) -> dict:
    field = {"required": False, "wide": False, "kind": "text", "hint": ""}
    field.update(kwargs)
    return field


_NAME = _spec(name="student_name", label="Name", kind="text", required=True, wide=True, hint="Use a fictitious name. Do not enter a real person's details.")
_COUNTRY = _spec(name="country", label="Country of residence", kind="select", required=True, options=["Ethiopia", "Kenya", "Uganda", "Nigeria", "Other"])
_CITIZENSHIP = _spec(name="citizenship", label="Citizenship", kind="select", options=["Ethiopian", "Kenyan", "Ugandan", "Nigerian", "Other"])
_GENDER = _spec(name="gender", label="Gender", kind="select", options=["Female", "Male", "Other"])
_NEED = _spec(
    name="financial_need",
    label="Financial need",
    kind="select",
    options=[{"value": "yes", "label": "Yes, I need funding"}, {"value": "no", "label": "No"}],
)
_GPA = _spec(name="gpa", label="GPA", kind="number", required=True, step="0.01", min=0, max=4, hint="Use a 0.0 to 4.0 scale.")
_ENGLISH = _spec(
    name="english_test",
    label="English test",
    kind="select",
    options=[{"value": "IELTS", "label": "IELTS"}, {"value": "TOEFL", "label": "TOEFL"}, {"value": "None", "label": "No English test"}],
)
_SCORE = _spec(name="english_score", label="English score", kind="number", step="0.5", min=0, max=120, hint="IELTS is out of 9. TOEFL is out of 120.")

LEVEL_FORMS = {
    "high_school": [
        _NAME,
        _spec(name="institution", label="School", kind="text", required=True, wide=True),
        _spec(name="grade_level", label="Grade", kind="select", required=True, options=GRADES),
        _spec(name="stream", label="Stream", kind="select", required=True, options=STREAMS),
        _spec(name="field_of_study", label="Intended field of study", kind="select", required=True, wide=True, options=FIELDS_OF_STUDY),
        _GPA,
        _COUNTRY,
        _CITIZENSHIP,
        _GENDER,
        _NEED,
    ],
    "bsc": [
        _NAME,
        _spec(name="institution", label="University", kind="text", required=True, wide=True),
        _spec(name="field_of_study", label="Field of study", kind="select", required=True, wide=True, options=FIELDS_OF_STUDY),
        _GPA,
        _spec(name="year_of_study", label="Year of study", kind="number", required=True, step="1", min=1, max=6, hint="1 is first year."),
        _COUNTRY,
        _CITIZENSHIP,
        _GENDER,
        _NEED,
    ],
    "masters": [
        _NAME,
        _spec(name="institution", label="University", kind="text", required=True, wide=True),
        _spec(name="field_of_study", label="Master's field", kind="select", required=True, wide=True, options=FIELDS_OF_STUDY),
        _spec(name="prior_field", label="Bachelor's field", kind="select", required=True, wide=True, options=FIELDS_OF_STUDY),
        _GPA,
        _spec(name="year_of_study", label="Year of study", kind="number", step="1", min=1, max=3),
        _spec(name="research_interest", label="Research interest", kind="textarea", required=True, wide=True, hint="A short description is enough."),
        _COUNTRY,
        _CITIZENSHIP,
        _GENDER,
        _NEED,
        _ENGLISH,
        _SCORE,
    ],
    "phd": [
        _NAME,
        _spec(name="institution", label="University", kind="text", required=True, wide=True),
        _spec(name="field_of_study", label="PhD field", kind="select", required=True, wide=True, options=FIELDS_OF_STUDY),
        _spec(name="prior_field", label="Master's field", kind="select", required=True, wide=True, options=FIELDS_OF_STUDY),
        _GPA,
        _spec(name="year_of_study", label="Year of study", kind="number", step="1", min=1, max=6),
        _spec(name="research_interest", label="Research topic", kind="textarea", required=True, wide=True),
        _COUNTRY,
        _CITIZENSHIP,
        _GENDER,
        _NEED,
        _ENGLISH,
        _SCORE,
    ],
}

EXAMPLES = [
    {
        "id": "eligible",
        "label": "Example: eligible shortlist",
        "detail": "Computer Science, GPA 3.8, year 3, Ethiopia. Expect eligible, ineligible, and a plan.",
        "profile": {
            "student_name": "Hanna Bekele",
            "field_of_study": "Computer Science",
            "gpa": "3.8",
            "year_of_study": "3",
            "country": "Ethiopia",
            "citizenship": "Ethiopian",
            "degree_level": "Bachelor",
            "gender": "Female",
            "financial_need": "yes",
            "english_test": "IELTS",
            "english_score": "7",
        },
    },
    {
        "id": "ineligible",
        "label": "Example: ineligible",
        "detail": "Business, GPA 2.1, year 2, Kenya. Every scholarship should fail a cited rule.",
        "profile": {
            "student_name": "Dawit Mekonnen",
            "field_of_study": "Business",
            "gpa": "2.1",
            "year_of_study": "2",
            "country": "Kenya",
            "citizenship": "Kenyan",
            "degree_level": "Bachelor",
            "gender": "Male",
            "financial_need": "no",
            "english_test": "IELTS",
            "english_score": "6",
        },
    },
    {
        "id": "missing-year",
        "label": "Example: missing year",
        "detail": "Same STEM profile with year left blank. The adviser should ask, then you can recheck.",
        "profile": {
            "student_name": "Hanna Bekele",
            "field_of_study": "Computer Science",
            "gpa": "3.8",
            "year_of_study": "",
            "country": "Ethiopia",
            "citizenship": "Ethiopian",
            "degree_level": "Bachelor",
            "gender": "Female",
            "financial_need": "yes",
            "english_test": "IELTS",
            "english_score": "7",
        },
    },
]


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _gpa_errors(raw: dict) -> list[str]:
    gpa = raw.get("gpa")
    if _blank(gpa):
        return ["GPA is required."]
    try:
        gpa_value = float(gpa)
    except (TypeError, ValueError):
        return ["GPA must be a number from 0.0 to 4.0."]
    if gpa_value < 0 or gpa_value > 4:
        return ["GPA must be between 0.0 and 4.0."]
    return []


def _year_errors(raw: dict, *, required: bool, low: int, high: int) -> list[str]:
    year = raw.get("year_of_study")
    if _blank(year):
        return ["Year of study is required."] if required else []
    try:
        year_value = int(str(year).strip())
    except (TypeError, ValueError):
        return [f"Year of study must be a whole number from {low} to {high}."]
    if year_value < low or year_value > high:
        return [f"Year of study must be a whole number from {low} to {high}."]
    return []


def _english_errors(raw: dict) -> list[str]:
    test = _text(raw.get("english_test"))
    score = raw.get("english_score")
    if test not in {"IELTS", "TOEFL"}:
        return []
    if _blank(score):
        return [f"Enter the {test} score, or clear the English test if you do not have a result yet."]
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return ["English score must be a number."]
    if test == "IELTS" and (score_value < 0 or score_value > 9):
        return ["IELTS scores run from 0 to 9."]
    if test == "TOEFL" and (score_value < 0 or score_value > 120):
        return ["TOEFL scores run from 0 to 120."]
    return []


def _choice_errors(raw: dict, key: str, options: list, message: str) -> list[str]:
    value = _text(raw.get(key))
    allowed = {str(option) for option in options}
    if value not in allowed:
        return [message]
    return []


def _validate_level(raw: dict, level: str) -> list[str]:
    errors = []
    if not _text(raw.get("student_name")):
        errors.append("Name is required. Use a fictitious name.")
    if not _text(raw.get("country")):
        errors.append("Country of residence is required.")
    if not _text(raw.get("field_of_study")):
        errors.append("Field of study is required.")
    if not _text(raw.get("institution")):
        errors.append("School or university is required.")
    errors.extend(_gpa_errors(raw))
    if level == "high_school":
        errors.extend(_choice_errors(raw, "grade_level", GRADES, "Grade must be 9, 10, 11, or 12."))
        errors.extend(_choice_errors(raw, "stream", STREAMS, "Choose a stream."))
    elif level == "bsc":
        errors.extend(_year_errors(raw, required=True, low=1, high=6))
    else:
        if not _text(raw.get("prior_field")):
            errors.append("The previous degree field is required.")
        if len(_text(raw.get("research_interest"))) < 8:
            errors.append("Describe the research interest in at least a short sentence.")
        errors.extend(_year_errors(raw, required=False, low=1, high=6))
        errors.extend(_english_errors(raw))
    return errors


def validate_profile(raw: dict, *, require_level: bool = False) -> list[str]:
    level = _text(raw.get("student_level")).casefold()
    if require_level and level not in LEVEL_DEGREE:
        return ["Choose whether you are a high school, BSc, master's, or PhD student."]
    if level in LEVEL_DEGREE:
        return _validate_level(raw, level)

    errors = []
    if not _text(raw.get("student_name")):
        errors.append("Name is required. Use a fictitious name.")
    if not _text(raw.get("field_of_study")):
        errors.append("Field of study is required.")
    if not _text(raw.get("country")):
        errors.append("Country of residence is required.")
    errors.extend(_gpa_errors(raw))
    errors.extend(_year_errors(raw, required=False, low=1, high=7))
    errors.extend(_english_errors(raw))
    return errors


def to_internal(raw: dict) -> dict:
    field = _text(raw.get("field_of_study"))
    level = _text(raw.get("student_level")).casefold()
    degree = LEVEL_DEGREE.get(level, _text(raw.get("degree_level")))
    grade = raw.get("grade_level")
    need = raw.get("financial_need")
    if need is True or _text(need).casefold() in {"yes", "true"}:
        financial_need = True
    elif need is False or _text(need).casefold() in {"no", "false"}:
        financial_need = False
    else:
        financial_need = None

    gpa = None if _blank(raw.get("gpa")) else float(raw.get("gpa"))
    year = None if _blank(raw.get("year_of_study")) else int(str(raw.get("year_of_study")).strip())
    score = None if _blank(raw.get("english_score")) else float(raw.get("english_score"))

    return {
        "student_name": _text(raw.get("student_name")),
        "student_level": level if level in LEVEL_DEGREE else "",
        "institution": _text(raw.get("institution")),
        "grade_level": None if _blank(grade) else int(str(grade).strip()),
        "stream": _text(raw.get("stream")),
        "field_of_study": FIELD_ALIASES.get(field.casefold(), field),
        "prior_field": FIELD_ALIASES.get(_text(raw.get("prior_field")).casefold(), _text(raw.get("prior_field"))),
        "research_interest": _text(raw.get("research_interest")),
        "gpa": gpa,
        "year_of_study": year,
        "country": _text(raw.get("country")),
        "citizenship": _text(raw.get("citizenship")),
        "degree_level": DEGREE_ALIASES.get(degree.casefold(), degree),
        "gender": _text(raw.get("gender")),
        "financial_need": financial_need,
        "english_test": _text(raw.get("english_test")),
        "english_score": score,
    }


def to_form(profile: dict) -> dict:
    need = profile.get("financial_need")
    if need is True:
        financial_need = "yes"
    elif need is False:
        financial_need = "no"
    else:
        financial_need = ""
    return {
        "student_name": profile.get("student_name") or "",
        "student_level": profile.get("student_level") or "",
        "institution": profile.get("institution") or "",
        "grade_level": "" if profile.get("grade_level") is None else str(profile.get("grade_level")),
        "stream": profile.get("stream") or "",
        "field_of_study": profile.get("field_of_study") or "",
        "prior_field": profile.get("prior_field") or "",
        "research_interest": profile.get("research_interest") or "",
        "gpa": "" if profile.get("gpa") is None else profile.get("gpa"),
        "year_of_study": "" if profile.get("year_of_study") is None else profile.get("year_of_study"),
        "country": profile.get("country") or "",
        "citizenship": profile.get("citizenship") or "",
        "degree_level": profile.get("degree_level") or "",
        "gender": profile.get("gender") or "",
        "financial_need": financial_need,
        "english_test": profile.get("english_test") or "",
        "english_score": "" if profile.get("english_score") is None else profile.get("english_score"),
    }


def level_label(level: str) -> str:
    for item in LEVELS:
        if item["id"] == level:
            return item["label"]
    return ""


def summary(profile: dict) -> dict:
    return {key: value for key, value in profile.items() if value not in (None, "")}
