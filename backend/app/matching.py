"""Match a saved profile to published scholarships and record an email notice."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.auth import profile_record
from app.eligibility import evaluate_profile
from app.mail import email_configured, send_match_email
from app.models import Notification, Scholarship, User, UserProfile
from app.profile import level_label
from app.tools import published_scholarships, scholarship_dict
from app.vectors import VectorError, similar_chunks

def _notice(db: Session, user: User, scholarship: dict, reason: str, detail: str) -> None:
    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.scholarship_id == scholarship["id"],
            Notification.reason == reason,
        )
        .one_or_none()
    )
    if existing is not None:
        return
    subject = f"E-Scholar match: {scholarship['name']}"
    body = (
        f"Hello,\n\n"
        f"{scholarship['name']} ({scholarship['id']}) matches the profile saved on your account.\n"
        f"Deadline: {scholarship['deadline']}\n"
        f"{detail}\n\n"
        f"Open your E-Scholar dashboard to review it. Do not send personal documents by email.\n"
    )
    status = send_match_email(user.email, subject, body)
    db.add(
        Notification(
            id=f"ntf_{uuid4().hex[:12]}",
            user_id=user.id,
            scholarship_id=scholarship["id"],
            title=scholarship["name"],
            body=detail,
            reason=reason,
            email_status=status,
            created_at=datetime.now(timezone.utc),
            read_at=None,
        )
    )


def _students(db: Session) -> list[tuple[User, dict]]:
    rows = []
    for user in db.query(User).filter(User.role == "student").all():
        profile = profile_record(db.get(UserProfile, user.id))
        if profile.get("student_name") and profile.get("gpa") is not None:
            rows.append((user, profile))
    return rows


def notify_for_scholarship(db: Session, row: Scholarship) -> None:
    scholarship = scholarship_dict(row)
    for user, profile in _students(db):
        result = evaluate_profile(profile, [scholarship])[0]
        if result["status"] == "eligible":
            _notice(db, user, scholarship, "eligible", "The catalog rules mark this scholarship eligible for the saved profile.")
            continue
        if result["status"] == "ineligible":
            continue
        _notice_similar(db, user, profile, scholarship)


def notify_for_user(db: Session, user: User) -> None:
    if user.role != "student":
        return
    profile = profile_record(db.get(UserProfile, user.id))
    if not profile.get("student_name") or profile.get("gpa") is None:
        return
    scholarships = [scholarship_dict(row) for row in published_scholarships(db)]
    results = {item["opportunity_id"]: item for item in evaluate_profile(profile, scholarships)}
    try:
        hits = {item["scholarship_id"]: item for item in similar_chunks(db, profile, limit=8)}
    except VectorError:
        hits = {}
    for scholarship in scholarships:
        result = results[scholarship["id"]]
        if result["status"] == "eligible":
            _notice(db, user, scholarship, "eligible", "The catalog rules mark this scholarship eligible for the saved profile.")
        elif result["status"] != "ineligible" and scholarship["id"] in hits:
            score = hits[scholarship["id"]]["score"]
            _notice(
                db,
                user,
                scholarship,
                "similar",
                f"The embedded scholarship text is close to this profile (similarity {score}). A missing fact still has to be checked.",
            )


def _notice_similar(db: Session, user: User, profile: dict, scholarship: dict) -> None:
    try:
        hits = similar_chunks(db, profile, limit=8)
    except VectorError:
        return
    hit = next((item for item in hits if item["scholarship_id"] == scholarship["id"]), None)
    if hit is None:
        return
    _notice(
        db,
        user,
        scholarship,
        "similar",
        f"The embedded scholarship text is close to this profile (similarity {hit['score']}). A missing fact still has to be checked.",
    )


def _slim(result: dict) -> dict:
    return {
        "id": result["opportunity_id"],
        "name": result["name"],
        "provider": result["provider"],
        "deadline": result["deadline"],
        "summary": result["summary"],
        "status": result["status"],
        "source_url": result.get("source_url") or "",
        "passed": [item["label"] for item in result["passed"]],
        "unknown": [item["label"] for item in result["unknown"]],
    }


def dashboard_for(db: Session, user: User) -> dict:
    notify_for_user(db, user)
    profile = profile_record(db.get(UserProfile, user.id))
    ready = bool(profile.get("student_name") and profile.get("gpa") is not None and profile.get("field_of_study"))
    scholarships = [scholarship_dict(row) for row in published_scholarships(db)]
    results = evaluate_profile(profile, scholarships) if ready else []
    visible = [_slim(item) for item in results if item["status"] != "ineligible"]
    visible.sort(key=lambda item: {"eligible": 0, "undetermined": 1}.get(item["status"], 2))
    related = []
    related_note = ""
    if ready:
        try:
            related = similar_chunks(db, profile)
        except VectorError as exc:
            related_note = exc.message
        else:
            blocked = {item["opportunity_id"] for item in results if item["status"] == "ineligible"}
            names = {item["id"]: item["name"] for item in scholarships}
            related = [
                {**hit, "name": names.get(hit["scholarship_id"], hit["scholarship_id"])}
                for hit in related
                if hit["scholarship_id"] not in blocked
            ]
            if not related:
                related_note = "No embedded passage is close to this profile yet."
    notices = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    unread = sum(1 for notice in notices if notice.read_at is None)
    now = datetime.now(timezone.utc)
    for notice in notices:
        if notice.read_at is None:
            notice.read_at = now
    return {
        "profile_ready": ready,
        "needs_level": not profile.get("student_level"),
        "level": {"id": profile.get("student_level") or "", "label": level_label(profile.get("student_level") or "")},
        "student_name": profile.get("student_name") or "",
        "counts": {
            "eligible": sum(1 for item in visible if item["status"] == "eligible"),
            "undetermined": sum(1 for item in visible if item["status"] == "undetermined"),
            "notifications": unread,
        },
        "matches": visible,
        "related": related,
        "related_note": related_note,
        "email_configured": email_configured(),
        "notifications": [
            {
                "id": notice.id,
                "title": notice.title,
                "body": notice.body,
                "reason": notice.reason,
                "email_status": notice.email_status,
                "scholarship_id": notice.scholarship_id,
                "created_at": notice.created_at.isoformat(),
            }
            for notice in notices
        ],
    }
