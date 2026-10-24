from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text
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


class ApplicationPlan(Base):
    __tablename__ = "application_plans"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_name: Mapped[str] = mapped_column(String(200), nullable=False)
    student_name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    opportunities: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
