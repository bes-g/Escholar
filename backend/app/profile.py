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
    "master": "Master",
    "masters": "Master",
    "master's": "Master",
    "graduate": "Master",
}

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


def validate_profile(raw: dict) -> list[str]:
    errors = []
    if not _text(raw.get("student_name")):
        errors.append("Name is required. Use a fictitious name.")
    if not _text(raw.get("field_of_study")):
        errors.append("Field of study is required.")
    if not _text(raw.get("country")):
        errors.append("Country of residence is required.")

    gpa = raw.get("gpa")
    if _blank(gpa):
        errors.append("GPA is required.")
    else:
        try:
            gpa_value = float(gpa)
        except (TypeError, ValueError):
            errors.append("GPA must be a number from 0.0 to 4.0.")
        else:
            if gpa_value < 0 or gpa_value > 4:
                errors.append("GPA must be between 0.0 and 4.0.")

    year = raw.get("year_of_study")
    if not _blank(year):
        try:
            year_value = int(str(year).strip())
        except (TypeError, ValueError):
            errors.append("Year of study must be a whole number from 1 to 7.")
        else:
            if year_value < 1 or year_value > 7:
                errors.append("Year of study must be a whole number from 1 to 7.")

    test = _text(raw.get("english_test"))
    score = raw.get("english_score")
    if test in {"IELTS", "TOEFL"}:
        if _blank(score):
            errors.append(f"Enter the {test} score, or clear the English test if you do not have a result yet.")
        else:
            try:
                score_value = float(score)
            except (TypeError, ValueError):
                errors.append("English score must be a number.")
            else:
                if test == "IELTS" and (score_value < 0 or score_value > 9):
                    errors.append("IELTS scores run from 0 to 9.")
                if test == "TOEFL" and (score_value < 0 or score_value > 120):
                    errors.append("TOEFL scores run from 0 to 120.")
    return errors


def to_internal(raw: dict) -> dict:
    field = _text(raw.get("field_of_study"))
    degree = _text(raw.get("degree_level"))
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
        "field_of_study": FIELD_ALIASES.get(field.casefold(), field),
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
        "field_of_study": profile.get("field_of_study") or "",
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


def summary(profile: dict) -> dict:
    return {key: value for key, value in profile.items() if value not in (None, "")}
