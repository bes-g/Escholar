"""Accounts and sessions. Passwords stay hashed; the session cookie is httpOnly."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthSession, User, UserProfile
from app.profile import to_form, to_internal, validate_profile

COOKIE = "escholar_session"
SESSION_DAYS = 14
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, key_hex = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(key_hex)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(key, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_account(email: str, password: str) -> list[str]:
    errors = []
    if not EMAIL_RE.match(normalize_email(email)):
        errors.append("Enter a valid email address.")
    if len(password or "") < 8:
        errors.append("Password must be at least 8 characters.")
    if len(password or "") > 200:
        errors.append("Password is too long.")
    return errors


def profile_record(row: UserProfile | None) -> dict:
    if row is None:
        return {}
    return {
        "student_name": row.student_name,
        "field_of_study": row.field_of_study,
        "gpa": row.gpa,
        "year_of_study": row.year_of_study,
        "country": row.country,
        "citizenship": row.citizenship,
        "degree_level": row.degree_level,
        "gender": row.gender,
        "financial_need": row.financial_need,
        "english_test": row.english_test,
        "english_score": row.english_score,
        "student_level": row.student_level,
        "institution": row.institution,
        "grade_level": row.grade_level,
        "stream": row.stream,
        "research_interest": row.research_interest,
        "prior_field": row.prior_field,
    }


def write_profile(row: UserProfile, internal: dict, now: datetime) -> None:
    row.student_name = internal.get("student_name") or ""
    row.field_of_study = internal.get("field_of_study") or ""
    row.gpa = internal.get("gpa")
    row.year_of_study = internal.get("year_of_study")
    row.country = internal.get("country") or ""
    row.citizenship = internal.get("citizenship") or ""
    row.degree_level = internal.get("degree_level") or ""
    row.gender = internal.get("gender") or ""
    row.financial_need = internal.get("financial_need")
    row.english_test = internal.get("english_test") or ""
    row.english_score = internal.get("english_score")
    row.student_level = internal.get("student_level") or ""
    row.institution = internal.get("institution") or ""
    row.grade_level = internal.get("grade_level")
    row.stream = internal.get("stream") or ""
    row.research_interest = internal.get("research_interest") or ""
    row.prior_field = internal.get("prior_field") or ""
    row.updated_at = now


def public_account(user: User, profile: UserProfile | None) -> dict:
    role = user.role if user.role in {"student", "admin"} else "student"
    return {
        "user": {"id": user.id, "email": user.email, "role": role},
        "profile": to_form(profile_record(profile)),
    }


def checked_profile(raw: dict, *, require_level: bool = False) -> tuple[dict | None, list[str]]:
    errors = validate_profile(raw, require_level=require_level)
    if errors:
        return None, errors
    return to_internal(raw), []


def open_session(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            id=f"auth_{secrets.token_hex(8)}",
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=now + timedelta(days=SESSION_DAYS),
            created_at=now,
        )
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def revoke_token(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).one_or_none()
    if row is not None:
        db.delete(row)


def user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).one_or_none()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return user_from_request(request, db)
