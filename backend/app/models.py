from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Scholarship(Base):
    __tablename__ = "scholarships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    deadline: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    required_documents: Mapped[list] = mapped_column(JSON, nullable=False)
    criteria: Mapped[list] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published")
    origin: Mapped[str] = mapped_column(String(20), default="seed", server_default="seed")
    eligibility_notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    excerpt: Mapped[str] = mapped_column(Text, default="", server_default="")
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ApplicationPlan(Base):
    __tablename__ = "application_plans"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_name: Mapped[str] = mapped_column(String(200), nullable=False)
    student_name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    opportunities: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AdviceSession(Base):
    __tablename__ = "advice_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tool_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    latest_eligibility: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    plan_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="student", server_default="student")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    student_name: Mapped[str] = mapped_column(String(200), default="")
    field_of_study: Mapped[str] = mapped_column(String(120), default="")
    gpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_of_study: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    citizenship: Mapped[str] = mapped_column(String(80), default="")
    degree_level: Mapped[str] = mapped_column(String(40), default="")
    gender: Mapped[str] = mapped_column(String(40), default="")
    financial_need: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    english_test: Mapped[str] = mapped_column(String(40), default="")
    english_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    student_level: Mapped[str] = mapped_column(String(40), default="", server_default="")
    institution: Mapped[str] = mapped_column(String(200), default="", server_default="")
    grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stream: Mapped[str] = mapped_column(String(80), default="", server_default="")
    research_interest: Mapped[str] = mapped_column(Text, default="", server_default="")
    prior_field: Mapped[str] = mapped_column(String(120), default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChunkSetting(Base):
    __tablename__ = "chunk_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    small_chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=400)
    large_chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    last_error: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScholarshipChunk(Base):
    __tablename__ = "scholarship_chunks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scholarship_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    vector_id: Mapped[str] = mapped_column(String(40), default="", server_default="")
    section: Mapped[str] = mapped_column(String(40), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    scholarship_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    email_status: Mapped[str] = mapped_column(String(20), nullable=False, default="skipped")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
