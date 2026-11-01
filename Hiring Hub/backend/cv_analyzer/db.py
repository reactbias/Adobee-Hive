from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

from . import config


def utcnow():
    return datetime.now(timezone.utc)


_is_sqlite = config.DATABASE_URL.startswith("sqlite")
engine = create_engine(config.DATABASE_URL,
                       connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {})

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")   # better concurrent reads/writes
        cur.close()
        dbapi_conn.isolation_level = None      # we emit BEGIN ourselves (see below)

    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn):
        # Take the write lock up front. A deferred read->write upgrade fails instantly with
        # "database is locked" (the busy timeout is ignored) when another worker committed meanwhile.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    api_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    positions: Mapped[list["Position"]] = relationship(back_populates="organization",
                                                       cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("org_id", "title"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # [{"name": "team_size_managed", "description": "Largest team the candidate managed"}]
    custom_fields: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="positions")
    documents: Mapped[list["CVDocument"]] = relationship(back_populates="position")


class CVDocument(Base):
    __tablename__ = "cv_documents"
    __table_args__ = (UniqueConstraint("org_id", "position_id", "file_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[Optional[int]] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"), index=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    file_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    file_modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    pdf_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    pdf_modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|processing|done|failed
    error: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    position: Mapped[Optional[Position]] = relationship(back_populates="documents")
    profile: Mapped[Optional["CandidateProfile"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False)


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("cv_documents.id", ondelete="CASCADE"), unique=True)
    org_id: Mapped[int] = mapped_column(index=True)
    position_id: Mapped[Optional[int]] = mapped_column(index=True)

    # scalar, filterable columns
    full_name: Mapped[Optional[str]] = mapped_column(String(300))
    email: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(100))
    location: Mapped[Optional[str]] = mapped_column(String(300))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    current_job_title: Mapped[Optional[str]] = mapped_column(String(300))
    career_level: Mapped[Optional[str]] = mapped_column(String(50))
    total_years_experience: Mapped[Optional[float]] = mapped_column(Float)
    highest_education_level: Mapped[Optional[str]] = mapped_column(String(50))
    num_jobs: Mapped[int] = mapped_column(Integer, default=0)
    num_short_tenures: Mapped[int] = mapped_column(Integer, default=0)
    avg_tenure_months: Mapped[Optional[float]] = mapped_column(Float)
    worked_multiple_countries: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    years_since_graduation: Mapped[Optional[int]] = mapped_column(Integer)
    cv_language: Mapped[Optional[str]] = mapped_column(String(50))

    # list columns (JSON)
    job_categories: Mapped[list] = mapped_column(JSON, default=list)
    industry_sectors: Mapped[list] = mapped_column(JSON, default=list)
    companies: Mapped[list] = mapped_column(JSON, default=list)
    technical_skills: Mapped[list] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list] = mapped_column(JSON, default=list)
    software_and_tools: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    countries_worked: Mapped[list] = mapped_column(JSON, default=list)
    key_takeaways: Mapped[list] = mapped_column(JSON, default=list)
    additional_info: Mapped[list] = mapped_column(JSON, default=list)
    custom_fields: Mapped[list] = mapped_column(JSON, default=list)

    # full outputs
    data: Mapped[dict] = mapped_column(JSON)       # complete LLM extraction
    derived: Mapped[dict] = mapped_column(JSON)    # deterministic metrics

    model: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped[CVDocument] = relationship(back_populates="profile")
    skills: Mapped[list["CandidateSkill"]] = relationship(cascade="all, delete-orphan")


class CandidateSkill(Base):
    """Normalized skills for fast filtering ('who knows Python AND Azure?')."""
    __tablename__ = "candidate_skills"
    __table_args__ = (Index("ix_skill_org_name", "org_id", "skill_normalized"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[int] = mapped_column(Integer)
    skill: Mapped[str] = mapped_column(String(200))
    skill_normalized: Mapped[str] = mapped_column(String(200))
    skill_type: Mapped[str] = mapped_column(String(30))  # technical|soft|tool|language|certification


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("org_id", "position_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"), index=True)
    messages: Mapped[list] = mapped_column(JSON, default=list)
    current_candidate_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


def init_db():
    Base.metadata.create_all(engine)