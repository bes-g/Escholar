from app.database import SessionLocal
from app.models import ScholarshipChunk, User
from app.vectors import split_chunks


def _bsc():
    return {
        "student_name": "Hanna Bekele",
        "student_level": "bsc",
        "institution": "Addis Ababa University",
        "field_of_study": "Computer Science",
        "gpa": "3.8",
        "year_of_study": "3",
        "country": "Ethiopia",
        "citizenship": "Ethiopian",
        "gender": "Female",
        "financial_need": "yes",
    }


def _make_admin(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        user.role = "admin"
        db.commit()
    finally:
        db.close()


def test_chunks_stay_within_the_requested_sizes():
    text = "scholarship " * 80
    chunks = split_chunks(text, small=80, large=200, overlap=10)
    assert {chunk["kind"] for chunk in chunks} == {"small", "large"}
    assert max(len(chunk["text"]) for chunk in chunks if chunk["kind"] == "small") <= 80
    assert max(len(chunk["text"]) for chunk in chunks if chunk["kind"] == "large") <= 200
    assert any(chunk["parent_key"] for chunk in chunks if chunk["kind"] == "small")


def test_high_school_signup_uses_its_own_form(client):
    client.cookies.clear()
    missing = dict(_bsc())
    missing["student_level"] = "high_school"
    refused = client.post("/api/signup", json={"email": "grade@example.com", "password": "long-secret", "profile": missing})
    assert refused.status_code == 400
    assert any("Grade" in error for error in refused.json()["errors"])

    profile = dict(_bsc())
    profile.update({"student_level": "high_school", "institution": "Bole Secondary", "grade_level": "11", "stream": "Natural science"})
    created = client.post("/api/signup", json={"email": "grade@example.com", "password": "long-secret", "profile": profile})
    assert created.status_code == 200
    body = created.json()["profile"]
    assert body["student_level"] == "high_school"
    assert body["degree_level"] == "High school"
    assert body["grade_level"] == "11"
    client.post("/api/logout")
    client.cookies.clear()


def test_student_dashboard_shows_rule_matches_and_a_notice(client):
    client.cookies.clear()
    created = client.post("/api/signup", json={"email": "dash@example.com", "password": "long-secret", "profile": _bsc()})
    assert created.status_code == 200
    assert created.json()["profile"]["degree_level"] == "Bachelor"
    board = client.get("/api/dashboard").json()
    match = next(item for item in board["matches"] if item["id"] == "SCH-001")
    assert match["status"] == "eligible"
    assert any(item["scholarship_id"] == "SCH-001" and item["email_status"] == "skipped" for item in board["notifications"])
    assert client.get("/api/admin/chunking").status_code == 403
    client.post("/api/logout")
    client.cookies.clear()


def test_admin_chunk_settings_control_the_saved_embeddings(client, monkeypatch):
    monkeypatch.setattr(
        "app.vectors.embed_texts",
        lambda texts, task="RETRIEVAL_DOCUMENT": [[1.0, 0.0, float(len(text))] for text in texts],
    )
    client.cookies.clear()
    client.post("/api/signup", json={"email": "embed@example.com", "password": "long-secret", "profile": _bsc()})
    assert client.put(
        "/api/admin/chunking",
        json={"small_chunk_size": 500, "large_chunk_size": 200, "chunk_overlap": 10},
    ).status_code == 403
    _make_admin("embed@example.com")
    refused = client.put(
        "/api/admin/chunking",
        json={"small_chunk_size": 500, "large_chunk_size": 200, "chunk_overlap": 10},
    )
    assert refused.status_code == 400
    saved = client.put(
        "/api/admin/chunking",
        json={"small_chunk_size": 80, "large_chunk_size": 200, "chunk_overlap": 10},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["small_chunk_size"] == 80
    assert body["embedded_count"] > 0
    assert body["vector_store"] == "local"
    db = SessionLocal()
    try:
        rows = db.query(ScholarshipChunk).all()
        assert rows
        assert all(row.embedding for row in rows)
        assert all(row.char_count <= 80 for row in rows if row.kind == "small")
        assert all(row.char_count <= 200 for row in rows if row.kind == "large")
    finally:
        db.close()
        client.post("/api/logout")
        client.cookies.clear()
