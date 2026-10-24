"""E-Scholar API. The React app is served from the same host after it is built."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import app.agent as agent
from app.agent import ModelError, UserInputError, user_message
from app.catalog import seed_catalog
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import AdviceSession, ApplicationPlan, Scholarship
from app.plans import serialize_plan
from app.profile import EXAMPLES, FORM_FIELDS, to_form, to_internal, validate_profile
from app.tools import scholarship_dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escholar")


class AdviseRequest(BaseModel):
    profile: dict = Field(default_factory=dict)
    session_id: str | None = None
    simulate: str | None = None


class ConfirmRequest(BaseModel):
    plan_name: str | None = None


def _error(status: int, message: str, errors: list[str] | None = None, session_id: str | None = None):
    body = {"message": message}
    if errors:
        body["errors"] = errors
    if session_id:
        body["session_id"] = session_id
    return JSONResponse(status_code=status, content=body)


def _new_session(db: Session, profile: dict) -> AdviceSession:
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
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.flush()
    return session


def _load_session(db: Session, session_id: str | None, profile: dict) -> AdviceSession:
    if not session_id:
        return _new_session(db, profile)
    session = db.get(AdviceSession, session_id)
    if session is None:
        raise UserInputError("That check could not be found. Start a new check.")
    if session.plan_id and profile != session.profile:
        raise UserInputError("This plan is already saved. Start a new check to use a different profile.")
    session.profile = profile
    flag_modified(session, "profile")
    return session


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_catalog(db)
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
    }


@app.get("/api/catalog")
def catalog(db: Session = Depends(get_db)):
    rows = db.query(Scholarship).order_by(Scholarship.id).all()
    return {"opportunities": [scholarship_dict(row) for row in rows]}


@app.get("/api/plans")
def list_plans(db: Session = Depends(get_db)):
    rows = db.query(ApplicationPlan).order_by(ApplicationPlan.created_at.desc()).limit(20).all()
    return {"plans": [serialize_plan(row) for row in rows]}


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str, db: Session = Depends(get_db)):
    row = db.get(ApplicationPlan, plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No saved plan with that id.")
    return serialize_plan(row)


@app.post("/api/advise")
def advise(body: AdviseRequest, db: Session = Depends(get_db)):
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
        session = _load_session(db, body.session_id, profile)
        intent = "recheck" if session.messages else "advise"
        text = user_message(profile, intent, None, [])
        payload = agent.run_agent(db, session, text, intent, agent.default_complete)
        db.commit()
        return payload
    except UserInputError as exc:
        db.rollback()
        return _error(400, exc.message)
    except ModelError as exc:
        db.commit()
        return _error(502, exc.message, session_id=session.id)


@app.post("/api/sessions/{session_id}/confirm")
def confirm(session_id: str, body: ConfirmRequest, db: Session = Depends(get_db)):
    session = db.get(AdviceSession, session_id)
    if session is None:
        return _error(404, "That check could not be found. Start a new check.")
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
    eligible_ids = [
        item["opportunity_id"]
        for item in (session.latest_eligibility or [])
        if item["status"] == "eligible"
    ]
    try:
        session.requested_plan_name = (body.plan_name or "").strip()
        text = user_message(session.profile, "confirm", body.plan_name, eligible_ids)
        payload = agent.run_agent(db, session, text, "confirm", agent.default_complete)
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
