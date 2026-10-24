"""Five fictitious scholarships. The rule engine reads these criteria; the model does not."""

SCHOLARSHIPS = [
    {
        "id": "SCH-001",
        "name": "Abay STEM Excellence Scholarship",
        "provider": "Abay Education Trust (fictitious)",
        "deadline": "2026-03-15",
        "summary": "Undergraduate funding for strong STEM students studying in Ethiopia.",
        "required_documents": [
            "Official transcript",
            "Academic recommendation",
            "Personal statement (500 words)",
        ],
        "criteria": [
            {
                "id": "SCH-001-C1",
                "label": "Country of residence is Ethiopia",
                "field": "country",
                "op": "eq",
                "value": "Ethiopia",
            },
            {
                "id": "SCH-001-C2",
                "label": "Degree level is Bachelor",
                "field": "degree_level",
                "op": "eq",
                "value": "Bachelor",
            },
            {
                "id": "SCH-001-C3",
                "label": "GPA is at least 3.5 on a 4.0 scale",
                "field": "gpa",
                "op": "gte",
                "value": 3.5,
            },
            {
                "id": "SCH-001-C4",
                "label": "Field of study is Computer Science, Engineering, or Mathematics",
                "field": "field_of_study",
                "op": "in",
                "value": ["Computer Science", "Engineering", "Mathematics"],
            },
            {
                "id": "SCH-001-C5",
                "label": "Year of study is 2, 3, or 4",
                "field": "year_of_study",
                "op": "in",
                "value": [2, 3, 4],
            },
        ],
    },
    {
        "id": "SCH-002",
        "name": "Blue Nile Graduate Fellowship",
        "provider": "Blue Nile Scholars Fund (fictitious)",
        "deadline": "2026-04-30",
        "summary": "A master's fellowship for Ethiopian citizens in health, agriculture, or environmental science.",
        "required_documents": [
            "Official transcript",
            "Research proposal",
            "Two academic recommendations",
        ],
        "criteria": [
            {
                "id": "SCH-002-C1",
                "label": "Citizenship is Ethiopian",
                "field": "citizenship",
                "op": "eq",
                "value": "Ethiopian",
            },
            {
                "id": "SCH-002-C2",
                "label": "Degree level is Master",
                "field": "degree_level",
                "op": "eq",
                "value": "Master",
            },
            {
                "id": "SCH-002-C3",
                "label": "GPA is at least 3.2 on a 4.0 scale",
                "field": "gpa",
                "op": "gte",
                "value": 3.2,
            },
            {
                "id": "SCH-002-C4",
                "label": "Field of study is Public Health, Agriculture, or Environmental Science",
                "field": "field_of_study",
                "op": "in",
                "value": ["Public Health", "Agriculture", "Environmental Science"],
            },
            {
                "id": "SCH-002-C5",
                "label": "English result is IELTS 6.5 or higher, or TOEFL 80 or higher",
                "field": "english",
                "op": "english",
                "value": {"ielts": 6.5, "toefl": 80},
            },
        ],
    },
    {
        "id": "SCH-003",
        "name": "Lalibela Women in STEM Award",
        "provider": "Lalibela Learning Collective (fictitious)",
        "deadline": "2026-06-01",
        "summary": "Undergraduate award for women in STEM at Ethiopian institutions.",
        "required_documents": [
            "Official transcript",
            "Short essay",
            "Student identification",
        ],
        "criteria": [
            {
                "id": "SCH-003-C1",
                "label": "Gender is Female",
                "field": "gender",
                "op": "eq",
                "value": "Female",
            },
            {
                "id": "SCH-003-C2",
                "label": "Country of residence is Ethiopia",
                "field": "country",
                "op": "eq",
                "value": "Ethiopia",
            },
            {
                "id": "SCH-003-C3",
                "label": "Degree level is Bachelor",
                "field": "degree_level",
                "op": "eq",
                "value": "Bachelor",
            },
            {
                "id": "SCH-003-C4",
                "label": "GPA is at least 3.0 on a 4.0 scale",
                "field": "gpa",
                "op": "gte",
                "value": 3.0,
            },
            {
                "id": "SCH-003-C5",
                "label": "Field of study is a listed STEM subject",
                "field": "field_of_study",
                "op": "in",
                "value": [
                    "Computer Science",
                    "Engineering",
                    "Mathematics",
                    "Environmental Science",
                ],
            },
            {
                "id": "SCH-003-C6",
                "label": "Year of study is between 1 and 4",
                "field": "year_of_study",
                "op": "between",
                "value": [1, 4],
            },
        ],
    },
    {
        "id": "SCH-004",
        "name": "Rift Valley Community Scholarship",
        "provider": "Rift Valley Student Aid (fictitious)",
        "deadline": "2026-05-20",
        "summary": "Need-based help for undergraduates in Ethiopia.",
        "required_documents": [
            "Official transcript",
            "Statement of financial need",
            "Community recommendation",
        ],
        "criteria": [
            {
                "id": "SCH-004-C1",
                "label": "Country of residence is Ethiopia",
                "field": "country",
                "op": "eq",
                "value": "Ethiopia",
            },
            {
                "id": "SCH-004-C2",
                "label": "Degree level is Bachelor",
                "field": "degree_level",
                "op": "eq",
                "value": "Bachelor",
            },
            {
                "id": "SCH-004-C3",
                "label": "GPA is at least 2.5 on a 4.0 scale",
                "field": "gpa",
                "op": "gte",
                "value": 2.5,
            },
            {
                "id": "SCH-004-C4",
                "label": "Financial need is declared",
                "field": "financial_need",
                "op": "eq",
                "value": True,
            },
            {
                "id": "SCH-004-C5",
                "label": "Year of study is 3 or earlier",
                "field": "year_of_study",
                "op": "lte",
                "value": 3,
            },
        ],
    },
    {
        "id": "SCH-005",
        "name": "Axum Heritage Exchange Grant",
        "provider": "Axum Heritage Circle (fictitious)",
        "deadline": "2026-02-28",
        "summary": "Final-year grant for Ethiopian citizens in history, heritage, archaeology, or law.",
        "required_documents": [
            "Official transcript",
            "Writing sample",
            "Passport biographical page",
        ],
        "criteria": [
            {
                "id": "SCH-005-C1",
                "label": "Citizenship is Ethiopian",
                "field": "citizenship",
                "op": "eq",
                "value": "Ethiopian",
            },
            {
                "id": "SCH-005-C2",
                "label": "GPA is at least 3.7 on a 4.0 scale",
                "field": "gpa",
                "op": "gte",
                "value": 3.7,
            },
            {
                "id": "SCH-005-C3",
                "label": "Year of study is 4 or 5",
                "field": "year_of_study",
                "op": "in",
                "value": [4, 5],
            },
            {
                "id": "SCH-005-C4",
                "label": "Field of study is History, Archaeology, Heritage Studies, or Law",
                "field": "field_of_study",
                "op": "in",
                "value": ["History", "Archaeology", "Heritage Studies", "Law"],
            },
        ],
    },
]


def seed_catalog(db) -> None:
    from app.models import Scholarship

    keep = {record["id"] for record in SCHOLARSHIPS}
    for stale in (
        db.query(Scholarship).filter(Scholarship.origin == "seed", Scholarship.id.notin_(keep)).all()
    ):
        db.delete(stale)
    for record in SCHOLARSHIPS:
        row = db.get(Scholarship, record["id"])
        if row is None:
            row = Scholarship(id=record["id"])
            db.add(row)
        row.name = record["name"]
        row.provider = record["provider"]
        row.deadline = record["deadline"]
        row.summary = record["summary"]
        row.required_documents = list(record["required_documents"])
        row.criteria = list(record["criteria"])
        row.source_url = ""
        row.status = "published"
        row.origin = "seed"
        row.eligibility_notes = ""
        row.excerpt = ""
        row.fetched_at = None
        row.submitted_by = None
    db.commit()
