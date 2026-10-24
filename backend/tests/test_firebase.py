from app.database import SessionLocal
from app.firebase_auth import FirebaseAuthError
from app.models import User

from tests.test_accounts import _profile


def _identity(token: str) -> dict:
    if token == "good-student":
        return {"uid": "firebase-student", "email": "firebase.student@example.com"}
    if token == "good-admin":
        return {"uid": "firebase-admin", "email": "boss@example.com"}
    if token == "link-hanna":
        return {"uid": "firebase-hanna", "email": "hanna.firebase@example.com"}
    raise FirebaseAuthError("Sign-in could not be verified.")


def _enable(monkeypatch):
    monkeypatch.setattr("app.main.firebase_configured", lambda: True)
    monkeypatch.setattr("app.main.verify_firebase_token", _identity)
    monkeypatch.setattr("app.main.settings.admin_email", "boss@example.com")


def test_firebase_signup_creates_a_student_and_session(client, monkeypatch):
    _enable(monkeypatch)
    client.cookies.clear()
    missing = client.post("/api/auth/firebase", json={"id_token": "good-student"})
    assert missing.status_code == 400
    created = client.post(
        "/api/auth/firebase",
        json={"id_token": "good-student", "profile": _profile()},
    )
    assert created.status_code == 200
    assert created.json()["user"]["role"] == "student"
    assert created.json()["user"]["email"] == "firebase.student@example.com"
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["profile"]["student_level"] == "bsc"
    db = SessionLocal()
    row = db.query(User).filter(User.email == "firebase.student@example.com").one()
    assert row.firebase_uid == "firebase-student"
    assert row.role == "student"
    db.close()
    client.post("/api/logout")
    client.cookies.clear()


def test_firebase_admin_email_is_admin_and_other_signups_are_not(client, monkeypatch):
    _enable(monkeypatch)
    client.cookies.clear()
    created = client.post(
        "/api/auth/firebase",
        json={"id_token": "good-admin", "profile": _profile()},
    )
    assert created.status_code == 200
    assert created.json()["user"]["role"] == "admin"
    client.post("/api/logout")
    client.cookies.clear()


def test_firebase_links_an_existing_email_and_rejects_a_bad_token(client, monkeypatch):
    _enable(monkeypatch)
    client.cookies.clear()
    local = client.post(
        "/api/signup",
        json={"email": "hanna.firebase@example.com", "password": "long-secret", "profile": _profile()},
    )
    assert local.status_code == 200
    local_id = local.json()["user"]["id"]
    client.post("/api/logout")
    client.cookies.clear()
    linked = client.post("/api/auth/firebase", json={"id_token": "link-hanna"})
    assert linked.status_code == 200
    assert linked.json()["user"]["id"] == local_id
    assert linked.json()["user"]["role"] == "student"
    db = SessionLocal()
    row = db.get(User, local_id)
    assert row.firebase_uid == "firebase-hanna"
    db.close()
    client.cookies.clear()
    rejected = client.post("/api/auth/firebase", json={"id_token": "nope"})
    assert rejected.status_code == 401
    assert "could not be verified" in rejected.json()["message"]


def test_firebase_endpoint_stays_closed_until_the_server_is_configured(client, monkeypatch):
    monkeypatch.setattr("app.main.firebase_configured", lambda: False)
    refused = client.post("/api/auth/firebase", json={"id_token": "good-student", "profile": _profile()})
    assert refused.status_code == 400
    assert "not configured" in refused.json()["message"]
