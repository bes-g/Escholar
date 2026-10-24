from app.database import SessionLocal
from app.models import User
from app.sources import SourceError, extract_scholarship, validate_public_url


SAMPLE_HTML = """
<html>
  <head>
    <title>Rift Scholars Award | Example University</title>
    <meta name="description" content="Funding for Ethiopian students with a strong academic record." />
  </head>
  <body>
    <h1>Rift Scholars Award</h1>
    <p>Applications are open to Ethiopian citizens residing in Ethiopia.</p>
    <p>Deadline 15 March 2027.</p>
    <p>A minimum GPA of 3.4 is required, with IELTS 6.5 or TOEFL 90.</p>
    <h2>Required documents</h2>
    <ul>
      <li>Official transcript</li>
      <li>Personal statement</li>
    </ul>
    <h2>Eligibility</h2>
    <ul>
      <li>Must be an Ethiopian citizen</li>
    </ul>
  </body>
</html>
"""


def _profile():
    return {
        "student_name": "Hanna Bekele",
        "student_level": "bsc",
        "institution": "Addis Ababa University",
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
    }


def test_private_links_are_refused():
    for url in ("http://127.0.0.1/secret", "http://localhost/secret", "file:///etc/passwd", "http://10.1.1.1/a"):
        try:
            validate_public_url(url)
            raise AssertionError(url)
        except SourceError as exc:
            assert exc.message


def test_extraction_suggests_rules_without_publishing():
    record = extract_scholarship(SAMPLE_HTML, "https://example.edu/rift")
    assert record["name"] == "Rift Scholars Award"
    assert record["deadline"] == "2027-03-15"
    assert "Official transcript" in record["required_documents"]
    fields = {rule["field"] for rule in record["criteria"]}
    assert "gpa" in fields
    assert "english" in fields
    assert "citizenship" in fields


def _make_admin(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()
    finally:
        db.close()


def test_signup_stores_profile_and_profile_page_can_change_it(client):
    client.cookies.clear()
    created = client.post("/api/signup", json={"email": "hanna@example.com", "password": "long-secret", "profile": _profile()})
    assert created.status_code == 200
    assert created.json()["profile"]["student_name"] == "Hanna Bekele"
    assert created.json()["user"]["role"] == "student"
    assert client.get("/api/me").json()["user"]["email"] == "hanna@example.com"

    changed = dict(_profile())
    changed["year_of_study"] = "4"
    changed["gpa"] = "3.6"
    updated = client.put("/api/profile", json={"profile": changed})
    assert updated.status_code == 200
    assert updated.json()["profile"]["year_of_study"] == 4
    assert client.get("/api/me").json()["profile"]["gpa"] == 3.6

    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401
    again = client.post("/api/login", json={"email": "Hanna@Example.com", "password": "long-secret"})
    assert again.status_code == 200
    assert again.json()["profile"]["year_of_study"] == 4
    client.post("/api/logout")
    client.cookies.clear()


def test_draft_source_is_hidden_until_it_is_published(client, monkeypatch):
    monkeypatch.setattr("app.main.fetch_public_html", lambda url: ("https://example.edu/rift", SAMPLE_HTML))
    client.cookies.clear()
    source_id = None
    client.post(
        "/api/signup",
        json={"email": "curator@example.com", "password": "long-secret", "profile": _profile()},
    )
    refused = client.post("/api/sources", json={"url": "https://example.edu/rift"})
    assert refused.status_code == 403
    _make_admin("curator@example.com")
    created = client.post("/api/sources", json={"url": "https://example.edu/rift"})
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "draft"
    catalog = client.get("/api/catalog").json()["opportunities"]
    assert body["id"] not in {row["id"] for row in catalog}

    published = client.post(
        f"/api/sources/{body['id']}/publish",
        json={
            "name": body["name"],
            "provider": body["provider"],
            "deadline": "2027-03-15",
            "summary": "A reviewed scholarship for Ethiopian undergraduate students.",
            "required_documents": ["Official transcript"],
            "eligibility_notes": body["eligibility_notes"],
            "criteria": body["criteria"],
        },
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    catalog = client.get("/api/catalog").json()["opportunities"]
    assert body["id"] in {row["id"] for row in catalog}

    try:
        client.post(f"/api/sources/{body['id']}/unpublish")
        client.delete(f"/api/sources/{body['id']}")
        catalog = client.get("/api/catalog").json()["opportunities"]
        assert body["id"] not in {row["id"] for row in catalog}
        assert [row["id"] for row in catalog] == ["SCH-001", "SCH-002", "SCH-003", "SCH-004", "SCH-005"]
    finally:
        client.post(f"/api/sources/{body['id']}/unpublish")
        client.delete(f"/api/sources/{body['id']}")
        client.post("/api/logout")
        client.cookies.clear()
