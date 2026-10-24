"""E-Scholar API. The React app is served from the same host after it is built."""

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import app.agent as agent
from app.agent import ModelError, UserInputError
from app.auth import (
    checked_profile,
    clear_session_cookie,
    hash_password,
    revoke_token,
    normalize_email,
    open_session,
    optional_user,
    public_account,
    set_session_cookie,
    user_from_request,
    validate_account,
    verify_password,
    write_profile,
)
from app.catalog import seed_catalog
from app.scrapes import load_scrapes, record_from_row, remove_scrape, write_scrape
from app.config import settings
from app.database import Base, SessionLocal, engine, ensure_columns, get_db
from app.firebase_auth import FirebaseAuthError, firebase_configured, verify_firebase_token
from app.matching import dashboard_for, notify_for_scholarship, notify_for_user
from app.models import AdviceSession, ApplicationPlan, Scholarship, ScholarshipChunk, User, UserProfile
from app.plans import serialize_plan
from app.profile import EXAMPLES, FORM_FIELDS, LEVEL_FORMS, LEVELS, to_form, to_internal, validate_profile
from app.sources import (
    FETCH_HEADERS,
    SourceError,
    CRAWL_PAGE_CAP,
    discover_links,
    extract_scholarship,
    fetch_public_html,
    normalize_criteria,
    source_payload,
    validate_for_publish,
)
from app.tools import published_scholarships, scholarship_dict
from app.vectors import drop_scholarship, get_chunk_settings, index_scholarship, reindex_published, validate_chunk_sizes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escholar")


class AdviseRequest(BaseModel):
    profile: dict = Field(default_factory=dict)
    session_id: str | None = None
    simulate: str | None = None


class ConfirmRequest(BaseModel):
    plan_name: str | None = None


class SignupRequest(BaseModel):
    email: str
    password: str
    profile: dict = Field(default_factory=dict)


class LoginRequest(BaseModel):
    email: str
    password: str


class FirebaseAuthRequest(BaseModel):
    id_token: str
    profile: dict | None = None


class ProfileUpdate(BaseModel):
    profile: dict = Field(default_factory=dict)
    current_password: str | None = None
    new_password: str | None = None


class ChunkUpdate(BaseModel):
    small_chunk_size: int
    large_chunk_size: int
    chunk_overlap: int


class SourceCreate(BaseModel):
    url: str


class CrawlRequest(BaseModel):
    depth: int = 2


class SourceUpdate(BaseModel):
    name: str = ""
    provider: str = ""
    deadline: str = ""
    summary: str = ""
    required_documents: list[str] = Field(default_factory=list)
    eligibility_notes: str = ""
    criteria: list[dict] = Field(default_factory=list)
    sections: dict = Field(default_factory=dict)


def _error(status: int, message: str, errors: list[str] | None = None, session_id: str | None = None):
    body = {"message": message}
    if errors:
        body["errors"] = errors
    if session_id:
        body["session_id"] = session_id
    return JSONResponse(status_code=status, content=body)


def _new_session(db: Session, profile: dict, user_id: str | None = None) -> AdviceSession:
    now = datetime.now(timezone.utc)
    session = AdviceSession(
        id=f"ses_{uuid4().hex[:12]}",
        profile=profile,
        messages=[],
        tool_log=[],
        latest_eligibility=[],
        confirmed=False,
        status="draft",
        plan_id=None,
        user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.flush()
    return session


def _load_session(db: Session, session_id: str | None, profile: dict, user_id: str | None) -> AdviceSession:
    if not session_id:
        return _new_session(db, profile, user_id)
    session = db.get(AdviceSession, session_id)
    if session is None:
        raise UserInputError("That check could not be found. Start a new check.")
    if user_id and session.user_id and session.user_id != user_id:
        raise UserInputError("That check belongs to another account.")
    if user_id and not session.user_id:
        session.user_id = user_id
    if session.plan_id and profile != session.profile:
        raise UserInputError("This plan is already saved. Start a new check to use a different profile.")
    session.profile = profile
    flag_modified(session, "profile")
    return session


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    db = SessionLocal()
    try:
        seed_catalog(db)
        load_scrapes(db)
        _ensure_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="E-Scholar",
    summary="Scholarship adviser. Eligibility is decided in code; the model only chooses tools.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "catalog_count": db.query(Scholarship).count(),
        "model": settings.llm_model,
        "model_configured": settings.model_configured,
        "database": "sqlite" if settings.resolved_database_url.startswith("sqlite") else "postgres",
    }


@app.get("/api/meta")
def meta():
    return {
        "fields": FORM_FIELDS,
        "examples": EXAMPLES,
        "catalog_size": 5,
        "model": settings.llm_model,
        "model_configured": settings.model_configured,
        "levels": LEVELS,
        "level_forms": LEVEL_FORMS,
        "firebase": firebase_configured(),
    }


def _require_user(request: Request, db: Session) -> User:
    user = user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def _require_admin(request: Request, db: Session) -> User:
    user = _require_user(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator can review scholarship sources.")
    return user


def _ensure_admin(db: Session) -> None:
    email = normalize_email(settings.admin_email)
    password = settings.admin_password or ""
    if not email or len(password) < 6:
        return
    now = datetime.now(timezone.utc)
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(
            id=f"usr_{uuid4().hex[:12]}",
            email=email,
            password_hash=hash_password(password),
            role="admin",
            created_at=now,
        )
        db.add(user)
        db.add(UserProfile(user_id=user.id, student_name="Administrator", updated_at=now))
    else:
        user.role = "admin"
    db.commit()


def _owned_source(db: Session, source_id: str, user: User) -> Scholarship:
    del user
    row = db.get(Scholarship, source_id)
    if row is None or row.origin != "url":
        raise HTTPException(status_code=404, detail="That source was not found.")
    return row


@app.get("/api/catalog")
def catalog(db: Session = Depends(get_db)):
    return {"opportunities": [scholarship_dict(row) for row in published_scholarships(db)]}


@app.get("/api/plans")
def list_plans(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    query = db.query(ApplicationPlan)
    if user is None:
        query = query.filter(ApplicationPlan.user_id.is_(None))
    else:
        query = query.filter(ApplicationPlan.user_id == user.id)
    rows = query.order_by(ApplicationPlan.created_at.desc()).limit(20).all()
    return {"plans": [serialize_plan(row) for row in rows]}


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.get(ApplicationPlan, plan_id)
    if row is None or (row.user_id and (user is None or row.user_id != user.id)):
        raise HTTPException(status_code=404, detail="No saved plan with that id.")
    return serialize_plan(row)


@app.post("/api/signup")
def signup(body: SignupRequest, response: Response, db: Session = Depends(get_db)):
    errors = validate_account(body.email, body.password)
    profile, profile_errors = checked_profile(body.profile, require_level=True)
    errors.extend(profile_errors)
    if errors:
        return _error(400, "Some fields need correcting.", errors)
    email = normalize_email(body.email)
    if db.query(User).filter(User.email == email).one_or_none():
        return _error(400, "An account with that email already exists.")
    now = datetime.now(timezone.utc)
    user = User(
        id=f"usr_{uuid4().hex[:12]}",
        email=email,
        password_hash=hash_password(body.password),
        role="student",
        created_at=now,
    )
    stored = UserProfile(user_id=user.id, updated_at=now)
    write_profile(stored, profile, now)
    db.add(user)
    db.add(stored)
    token = open_session(db, user)
    db.commit()
    set_session_cookie(response, token)
    try:
        notify_for_user(db, user)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not match the new profile")
    return public_account(user, stored)


@app.post("/api/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        return _error(401, "Email or password is not correct.")
    token = open_session(db, user)
    db.commit()
    set_session_cookie(response, token)
    return public_account(user, db.get(UserProfile, user.id))


def _admin_email() -> str:
    return normalize_email(settings.admin_email)


@app.post("/api/auth/firebase")
def firebase_session(body: FirebaseAuthRequest, response: Response, db: Session = Depends(get_db)):
    if not firebase_configured():
        return _error(400, "Firebase sign-in is not configured on the server.")
    try:
        identity = verify_firebase_token(body.id_token)
    except FirebaseAuthError as exc:
        return _error(401, exc.message)
    email = normalize_email(identity["email"])
    uid = identity["uid"]
    user = db.query(User).filter(User.firebase_uid == uid).one_or_none()
    if user is None:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is not None:
            if user.firebase_uid and user.firebase_uid != uid:
                return _error(400, "That email is already linked to another sign-in.")
            user.firebase_uid = uid
    created = False
    stored = db.get(UserProfile, user.id) if user is not None else None
    if user is None:
        if not body.profile:
            return _error(400, "Create an account and choose a student type before signing in.")
        profile, errors = checked_profile(body.profile, require_level=True)
        if errors:
            return _error(400, "Some fields need correcting.", errors)
        now = datetime.now(timezone.utc)
        user = User(
            id=f"usr_{uuid4().hex[:12]}",
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            firebase_uid=uid,
            role="admin" if email and email == _admin_email() else "student",
            created_at=now,
        )
        stored = UserProfile(user_id=user.id, updated_at=now)
        write_profile(stored, profile, now)
        db.add(user)
        db.add(stored)
        created = True
    elif email and email == _admin_email():
        user.role = "admin"
    token = open_session(db, user)
    db.commit()
    set_session_cookie(response, token)
    if created:
        try:
            notify_for_user(db, user)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not match the new profile")
    return public_account(user, stored)


@app.post("/api/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_token(db, request.cookies.get("escholar_session"))
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    return public_account(user, db.get(UserProfile, user.id))


@app.put("/api/profile")
def update_profile(body: ProfileUpdate, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    profile, errors = checked_profile(body.profile, require_level=True)
    if body.new_password:
        if not verify_password(body.current_password or "", user.password_hash):
            errors.append("Current password is not correct.")
        errors.extend(validate_account(user.email, body.new_password))
        errors = [error for error in errors if not error.startswith("Enter a valid email")]
    if errors:
        return _error(400, "Some fields need correcting.", errors)
    stored = db.get(UserProfile, user.id)
    now = datetime.now(timezone.utc)
    if stored is None:
        stored = UserProfile(user_id=user.id, updated_at=now)
        db.add(stored)
    write_profile(stored, profile, now)
    if body.new_password:
        user.password_hash = hash_password(body.new_password)
    db.commit()
    try:
        notify_for_user(db, user)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not match the updated profile")
    return public_account(user, stored)


_fetch_times: dict[str, list[datetime]] = {}


def _allow_fetch(user_id: str) -> bool:
    now = datetime.now(timezone.utc)
    recent = [stamp for stamp in _fetch_times.get(user_id, []) if (now - stamp).total_seconds() < 3600]
    if len(recent) >= 8:
        _fetch_times[user_id] = recent
        return False
    recent.append(now)
    _fetch_times[user_id] = recent
    return True


def _apply_source_edit(row: Scholarship, body: SourceUpdate) -> None:
    row.name = body.name.strip()[:200] or "Untitled scholarship"
    row.provider = body.provider.strip()[:200] or row.provider
    row.deadline = body.deadline.strip()[:20]
    row.summary = body.summary.strip()[:2000]
    row.required_documents = [item.strip() for item in body.required_documents if item.strip()][:12]
    row.eligibility_notes = body.eligibility_notes.strip()[:2000]
    row.criteria = normalize_criteria(body.criteria, row.id)
    if body.sections:
        blocks = body.sections.get("blocks") if isinstance(body.sections.get("blocks"), dict) else {}
        row.sections = {
            "page_kind": body.sections.get("page_kind") or "scholarship",
            "study_level": str(body.sections.get("study_level") or "")[:40],
            "host_country": str(body.sections.get("host_country") or "")[:80],
            "related_pages": [
                {"title": str(item.get("title") or "")[:140], "url": str(item.get("url") or "")[:1000]}
                for item in (body.sections.get("related_pages") or [])
                if isinstance(item, dict)
            ][:12],
            "blocks": {str(key)[:40]: str(value or "")[:2000] for key, value in blocks.items()},
        }
        flag_modified(row, "sections")


@app.get("/api/sources")
def list_sources(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    rows = (
        db.query(Scholarship)
        .filter(Scholarship.origin == "url")
        .order_by(Scholarship.fetched_at.desc())
        .all()
    )
    return {"sources": [source_payload(row) for row in rows]}


@app.post("/api/sources")
def create_source(body: SourceCreate, request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    if not _allow_fetch(user.id):
        return _error(429, "Too many pages were fetched this hour. Try again later.")
    try:
        final_url, html = fetch_public_html(body.url)
        existing = db.query(Scholarship).filter(Scholarship.source_url == final_url).one_or_none()
        if existing is not None:
            if existing.submitted_by == user.id:
                return source_payload(existing)
            return _error(400, "That page is already in the catalog review.")
        extracted = extract_scholarship(html, final_url)
        source_id = f"SRC-{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        row = Scholarship(
            id=source_id,
            name=extracted["name"],
            provider=extracted["provider"],
            deadline=extracted["deadline"] or "",
            summary=extracted["summary"],
            required_documents=extracted["required_documents"],
            criteria=normalize_criteria(extracted["criteria"], source_id),
            source_url=final_url,
            status="draft",
            origin="url",
            eligibility_notes=extracted["eligibility_notes"],
            excerpt=extracted["excerpt"],
            sections=extracted.get("sections") or {},
            fetched_at=now,
            submitted_by=user.id,
        )
        db.add(row)
        db.commit()
        write_scrape(record_from_row(row))
        return source_payload(row)
    except SourceError as exc:
        db.rollback()
        return _error(400, exc.message)


def _draft_from_extract(db: Session, extracted: dict, user: User, depth: int) -> Scholarship:
    source_id = f"SRC-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    sections = dict(extracted.get("sections") or {})
    sections["crawl_depth"] = depth
    row = Scholarship(
        id=source_id,
        name=extracted["name"],
        provider=extracted["provider"],
        deadline=extracted["deadline"] or "",
        summary=extracted["summary"],
        required_documents=extracted["required_documents"],
        criteria=normalize_criteria(extracted["criteria"], source_id),
        source_url=extracted["source_url"],
        status="draft",
        origin="url",
        eligibility_notes=extracted["eligibility_notes"],
        excerpt=extracted["excerpt"],
        sections=sections,
        fetched_at=now,
        submitted_by=user.id,
    )
    db.add(row)
    return row


@app.post("/api/sources/{source_id}/crawl")
def crawl_source(source_id: str, body: CrawlRequest, request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    row = _owned_source(db, source_id, user)
    if body.depth < 1 or body.depth > 3:
        return _error(400, "Depth must be 1, 2, or 3.")
    limit = CRAWL_PAGE_CAP[body.depth]
    queue = [(row.source_url, 1, None)]
    seen = {row.source_url.rstrip("/")}
    pages = [{"id": row.id, "name": row.name, "url": row.source_url, "depth": 1, "status": "stored", "message": ""}]
    stored = 0
    robots: dict[str, bool] = {}
    with httpx.Client(timeout=12.0, follow_redirects=False, headers=FETCH_HEADERS) as client:
        while queue and len(seen) <= limit:
            url, depth, cached = queue.pop(0)
            html = cached
            if html is None and depth < body.depth:
                try:
                    final_url, html = fetch_public_html(url, client=client, robots=robots)
                except SourceError as exc:
                    pages.append({"id": "", "name": url, "url": url, "depth": depth, "status": "failed", "message": exc.message})
                    continue
            if depth >= body.depth or not html:
                continue
            for link in discover_links(html, url, limit):
                key = link.rstrip("/")
                if key in seen or len(seen) >= limit:
                    continue
                seen.add(key)
                existing = db.query(Scholarship).filter(Scholarship.source_url == link).one_or_none()
                if existing is not None:
                    pages.append(
                        {
                            "id": existing.id,
                            "name": existing.name,
                            "url": link,
                            "depth": depth + 1,
                            "status": "skipped",
                            "message": "Already stored.",
                        }
                    )
                    if depth + 1 < body.depth:
                        try:
                            final_url, child_html = fetch_public_html(link, client=client, robots=robots)
                        except SourceError:
                            continue
                        queue.append((final_url, depth + 1, child_html))
                    continue
                try:
                    final_url, child_html = fetch_public_html(link, client=client, robots=robots)
                except SourceError as exc:
                    pages.append({"id": "", "name": link, "url": link, "depth": depth + 1, "status": "failed", "message": exc.message})
                    continue
                if final_url.rstrip("/") in {item.rstrip("/") for item in seen if item != key}:
                    pages.append({"id": "", "name": final_url, "url": final_url, "depth": depth + 1, "status": "skipped", "message": "Already stored."})
                    continue
                seen.add(final_url.rstrip("/"))
                try:
                    extracted = extract_scholarship(child_html, final_url)
                    child = _draft_from_extract(db, extracted, user, depth + 1)
                    db.commit()
                    write_scrape(record_from_row(child))
                except SourceError as exc:
                    db.rollback()
                    pages.append({"id": "", "name": link, "url": link, "depth": depth + 1, "status": "failed", "message": exc.message})
                    continue
                except Exception:
                    db.rollback()
                    logger.exception("Could not read %s", link)
                    pages.append({"id": "", "name": link, "url": link, "depth": depth + 1, "status": "failed", "message": "This page could not be read."})
                    continue
                stored += 1
                logger.info("Stored %s %s", child.id, child.name)
                pages.append(
                    {"id": child.id, "name": child.name, "url": child.source_url, "depth": depth + 1, "status": "stored", "message": ""}
                )
                if depth + 1 < body.depth:
                    queue.append((child.source_url, depth + 1, child_html))
    return {
        "depth": body.depth,
        "limit": limit,
        "stored": stored,
        "skipped": sum(1 for item in pages if item["status"] == "skipped"),
        "failed": sum(1 for item in pages if item["status"] == "failed"),
        "pages": pages,
    }


@app.put("/api/sources/{source_id}")
def update_source(source_id: str, body: SourceUpdate, request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    row = _owned_source(db, source_id, user)
    try:
        _apply_source_edit(row, body)
    except SourceError as exc:
        return _error(400, exc.message)
    db.commit()
    write_scrape(record_from_row(row))
    return source_payload(row)


@app.post("/api/sources/{source_id}/publish")
def publish_source(source_id: str, body: SourceUpdate, request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    row = _owned_source(db, source_id, user)
    try:
        _apply_source_edit(row, body)
        validate_for_publish(
            {
                "name": row.name,
                "deadline": row.deadline,
                "summary": row.summary,
                "criteria": row.criteria,
                "sections": row.sections or {},
            }
        )
    except SourceError as exc:
        db.rollback()
        return _error(400, exc.message)
    row.status = "published"
    db.commit()
    write_scrape(record_from_row(row))
    try:
        index_scholarship(db, row)
        notify_for_scholarship(db, row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not embed the published scholarship")
    return source_payload(row)


@app.post("/api/sources/{source_id}/unpublish")
def unpublish_source(source_id: str, request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    row = _owned_source(db, source_id, user)
    row.status = "draft"
    drop_scholarship(db, row.id)
    db.commit()
    write_scrape(record_from_row(row))
    return source_payload(row)


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str, request: Request, db: Session = Depends(get_db)):
    user = _require_admin(request, db)
    row = _owned_source(db, source_id, user)
    if row.status == "published":
        return _error(400, "Unpublish the scholarship before deleting it.")
    drop_scholarship(db, row.id)
    db.delete(row)
    db.commit()
    remove_scrape(row.id)
    return {"ok": True}


def _chunk_status(db: Session) -> dict:
    row = get_chunk_settings(db)
    return {
        "small_chunk_size": row.small_chunk_size,
        "large_chunk_size": row.large_chunk_size,
        "chunk_overlap": row.chunk_overlap,
        "last_error": row.last_error or "",
        "chunk_count": db.query(ScholarshipChunk).count(),
        "embedded_count": db.query(ScholarshipChunk).filter(ScholarshipChunk.embedding.isnot(None)).count(),
        "pinecone_configured": bool(settings.pinecone_api_key.strip()),
        "pinecone_index": settings.pinecone_index,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "vector_store": "pinecone" if settings.pinecone_api_key.strip() else "local",
    }


@app.get("/api/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="The dashboard is for student accounts.")
    payload = dashboard_for(db, user)
    db.commit()
    return payload


@app.get("/api/admin/chunking")
def read_chunking(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    payload = _chunk_status(db)
    db.commit()
    return payload


@app.put("/api/admin/chunking")
def update_chunking(body: ChunkUpdate, request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    errors = validate_chunk_sizes(body.small_chunk_size, body.large_chunk_size, body.chunk_overlap)
    if errors:
        return _error(400, "Chunk sizes need correcting.", errors)
    row = get_chunk_settings(db)
    row.small_chunk_size = body.small_chunk_size
    row.large_chunk_size = body.large_chunk_size
    row.chunk_overlap = body.chunk_overlap
    row.updated_at = datetime.now(timezone.utc)
    totals = reindex_published(db)
    db.commit()
    return {**_chunk_status(db), **totals}


@app.post("/api/advise")
def advise(body: AdviseRequest, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    errors = validate_profile(body.profile)
    if errors:
        return _error(400, "Some fields need correcting.", errors)
    if body.simulate:
        return _error(
            502,
            "Simulated model failure. Nothing was saved. Your entries are still in the form. Retry when you are ready.",
        )

    profile = to_internal(body.profile)
    try:
        session = _load_session(db, body.session_id, profile, user.id if user else None)
        payload = agent.run_catalog(db, session)
        db.commit()
        return payload
    except UserInputError as exc:
        db.rollback()
        return _error(400, exc.message)
    except ModelError as exc:
        db.commit()
        return _error(502, exc.message, session_id=session.id)


@app.post("/api/sessions/{session_id}/confirm")
def confirm(session_id: str, body: ConfirmRequest, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    session = db.get(AdviceSession, session_id)
    if session is None:
        return _error(404, "That check could not be found. Start a new check.")
    if user and session.user_id and session.user_id != user.id:
        return _error(404, "That check could not be found. Start a new check.")
    if user and not session.user_id:
        session.user_id = user.id
    if session.plan_id:
        row = db.get(ApplicationPlan, session.plan_id)
        return {
            "session_id": session.id,
            "assistant_message": f"This plan was already saved as {session.plan_id}.",
            "profile": to_form(session.profile),
            "eligibility": session.latest_eligibility or [],
            "missing_fields": [],
            "awaiting_confirmation": False,
            "plan_preview": None,
            "saved_plan": serialize_plan(row) if row else None,
            "tool_log": [],
            "error": None,
            "model": settings.llm_model,
        }
    try:
        payload = agent.confirm_saved(db, session, body.plan_name or "")
        db.commit()
        return payload
    except UserInputError as exc:
        db.rollback()
        return _error(400, exc.message)
    except ModelError as exc:
        db.commit()
        return _error(502, exc.message, session_id=session.id)


@app.exception_handler(HTTPException)
async def http_exception(_request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, str):
        return JSONResponse(status_code=exc.status_code, content={"message": detail})
    return JSONResponse(status_code=exc.status_code, content=detail)


def _mount_frontend(application: FastAPI) -> None:
    dist = settings.resolved_frontend_dist
    index = dist / "index.html"
    if not index.is_file():
        return
    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="That API path was not found.")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


_mount_frontend(app)
