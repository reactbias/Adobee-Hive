import os
import shutil
import tempfile
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Header, HTTPException,
                     Query, UploadFile)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .db import (CandidateProfile, CandidateSkill, CVDocument, ChatSession, Organization, Position,
                 SessionLocal, init_db)
from .documents import SUPPORTED_EXT
from .recruiter_agent import (all_candidate_ids, apply_recruiter_request, candidate_briefs,
                              reset_filters)
from .service import (create_organization, create_position, import_job_postings,
                      process_document, register_file)


@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CV Analyzer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- dependencies ----------
def get_db():
    with SessionLocal() as s:
        yield s


def current_org(x_api_key: str = Header(...), db: Session = Depends(get_db)) -> Organization:
    org = db.scalar(select(Organization).where(Organization.api_key == x_api_key))
    if not org:
        raise HTTPException(401, "Invalid API key")
    return org


def require_admin(x_admin_token: str = Header(...)):
    if x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(401, "Invalid admin token")


def _position_or_404(db: Session, org: Organization, position_id: int) -> Position:
    pos = db.get(Position, position_id)
    if not pos or pos.org_id != org.id:
        raise HTTPException(404, "Position not found")
    return pos


def _doc_or_404(db: Session, org: Organization, doc_id: int) -> CVDocument:
    doc = db.get(CVDocument, doc_id)
    if not doc or doc.org_id != org.id:
        raise HTTPException(404, "CV not found")
    return doc


# ---------- request models ----------
class OrgCreate(BaseModel):
    name: str


class CustomFieldSpec(BaseModel):
    name: str                       # e.g. "team_size_managed"
    description: Optional[str] = None  # e.g. "Largest team the candidate managed (number)"


class PositionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    custom_fields: list[CustomFieldSpec] = []


# ---------- admin ----------
@app.post("/admin/organizations", dependencies=[Depends(require_admin)])
def admin_create_org(body: OrgCreate, db: Session = Depends(get_db)):
    try:
        org = create_organization(db, body.name)
    except IntegrityError:
        raise HTTPException(409, "Organization already exists")
    return {"id": org.id, "name": org.name, "api_key": org.api_key, "positions": []}


@app.post("/admin/organizations/{org_id}/import-job-postings",
          dependencies=[Depends(require_admin)])
def admin_import_job_postings(org_id: int, db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    folder = Path(__file__).resolve().parent.parent / "job_postings"
    positions = import_job_postings(db, org.id, folder)
    return {    "positions": [{"id": p.id, "title": p.title} for p in positions]}


@app.post("/admin/organizations/bootstrap", dependencies=[Depends(require_admin)])
def admin_bootstrap_org(body: OrgCreate, db: Session = Depends(get_db)):
    org = db.scalar(select(Organization).where(Organization.name == body.name))
    if org is None:
        org = create_organization(db, body.name)
    positions = db.scalars(select(Position).where(Position.org_id == org.id)).all()
    return {"id": org.id, "name": org.name, "api_key": org.api_key,
    "positions": [{"id": p.id, "title": p.title} for p in positions]}


# ---------- positions ----------
@app.post("/positions")
def new_position(body: PositionCreate, org=Depends(current_org), db: Session = Depends(get_db)):
    try:
        pos = create_position(db, org.id, body.title, body.description,
                              [c.model_dump() for c in body.custom_fields])
    except IntegrityError:
        raise HTTPException(409, "Position with this title already exists")
    return {"id": pos.id, "title": pos.title, "custom_fields": pos.custom_fields}


@app.get("/positions")
def list_positions(org=Depends(current_org), db: Session = Depends(get_db)):
    rows = db.scalars(select(Position).where(Position.org_id == org.id)).all()
    result = []
    for p in rows:
        counts = dict(db.execute(
            select(CVDocument.status, func.count(CVDocument.id))
            .where(CVDocument.org_id == org.id, CVDocument.position_id == p.id)
            .group_by(CVDocument.status)
        ).all())
        result.append({
            "id": p.id, "title": p.title, "description": p.description,
            "custom_fields": p.custom_fields,
            "applicants_count": sum(counts.values()),
            "status_counts": counts,
        })
    return result


# ---------- CVs ----------
@app.post("/positions/{position_id}/cvs")
def upload_cvs(position_id: int, background: BackgroundTasks,
               files: list[UploadFile] = File(...),
               org=Depends(current_org), db: Session = Depends(get_db)):
    pos = _position_or_404(db, org, position_id)
    results = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in SUPPORTED_EXT:
            results.append({"filename": f.filename, "status": "rejected",
                            "reason": f"unsupported type {ext}"})
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(f.file, tmp)
            tmp_path = tmp.name
        try:
            doc, created = register_file(db, org.id, pos.id, tmp_path, f.filename)
        finally:
            os.unlink(tmp_path)
        if created:
            background.add_task(process_document, doc.id)
        results.append({"id": doc.id, "filename": doc.original_filename,
                        "status": doc.status if not created else "queued",
                        "duplicate": not created})
    return results


@app.get("/cvs")
def list_cvs(position_id: Optional[int] = None, status: Optional[str] = None,
             org=Depends(current_org), db: Session = Depends(get_db)):
    q = select(CVDocument).where(CVDocument.org_id == org.id)
    if position_id is not None:
        q = q.where(CVDocument.position_id == position_id)
    if status:
        q = q.where(CVDocument.status == status)
    out = []
    for d in db.scalars(q.order_by(CVDocument.uploaded_at.desc())).all():
        p = d.profile
        out.append({
            "id": d.id, "filename": d.original_filename, "position_id": d.position_id,
            "status": d.status, "error": d.error,
            "full_name": p.full_name if p else None,
            "current_job_title": p.current_job_title if p else None,
            "total_years_experience": p.total_years_experience if p else None,
            "key_takeaways": p.key_takeaways if p else [],
        })
    return out


@app.get("/cvs/{doc_id}")
def get_cv(doc_id: int, org=Depends(current_org), db: Session = Depends(get_db)):
    d = _doc_or_404(db, org, doc_id)
    p = d.profile
    return {
        "document": {"id": d.id, "filename": d.original_filename, "status": d.status,
                     "error": d.error, "page_count": d.page_count,
                     "pdf_created_at": d.pdf_created_at, "pdf_modified_at": d.pdf_modified_at,
                     "uploaded_at": d.uploaded_at, "processed_at": d.processed_at},
        "extraction": p.data if p else None,
        "derived": p.derived if p else None,
        "usage": {"model": p.model, "prompt_tokens": p.prompt_tokens,
                  "completion_tokens": p.completion_tokens} if p else None,
    }


@app.post("/cvs/{doc_id}/reprocess")
def reprocess(doc_id: int, background: BackgroundTasks,
              org=Depends(current_org), db: Session = Depends(get_db)):
    d = _doc_or_404(db, org, doc_id)
    d.status = "pending"
    db.commit()
    background.add_task(process_document, d.id)
    return {"id": d.id, "status": "queued"}


@app.get("/candidates/search")
def search_by_skills(skill: list[str] = Query(...), match: Literal["all", "any"] = "all",
                     position_id: Optional[int] = None,
                     org=Depends(current_org), db: Session = Depends(get_db)):
    """/candidates/search?skill=python&skill=azure&match=all"""
    norms = sorted({s.strip().lower() for s in skill})
    q = (select(CandidateSkill.profile_id)
         .join(CandidateProfile, CandidateProfile.id == CandidateSkill.profile_id)
         .where(CandidateSkill.org_id == org.id, CandidateSkill.skill_normalized.in_(norms))
         .group_by(CandidateSkill.profile_id))
    if position_id is not None:
        q = q.where(CandidateProfile.position_id == position_id)
    if match == "all":
        q = q.having(func.count(func.distinct(CandidateSkill.skill_normalized)) == len(norms))
    ids = db.scalars(q).all()
    profiles = db.scalars(select(CandidateProfile).where(CandidateProfile.id.in_(ids))).all()
    return [{"document_id": p.document_id, "full_name": p.full_name,
             "current_job_title": p.current_job_title,
             "total_years_experience": p.total_years_experience} for p in profiles]

# ---------- recruiter filter agent ----------
# The frontend owns the filter state: it keeps the list of candidate ids currently in play and sends
# it back with every new request, so filters stack. Reset = start again from all candidates.
class FilterRequest(BaseModel):
    request: str                     # e.g. "only people from Swiss cities"
    ids: Optional[list[int]] = None  # current candidate ids; omit to start from all of the position


class ChatSessionRequest(BaseModel):
    messages: list[dict] = []
    current_candidate_ids: list[int] = []


def _filter_response(db: Session, r) -> dict:
    return {"ids": r.ids, "count": len(r.ids), "action": r.action, "explanation": r.explanation,
            "previous_count": r.previous_count, "removed": r.removed, "plan": r.plan,
            "trace": r.trace, "candidates": candidate_briefs(db, r.ids)}


@app.get("/positions/{position_id}/candidates")
def position_candidates(position_id: int, org=Depends(current_org), db: Session = Depends(get_db)):
    _position_or_404(db, org, position_id)
    ids = all_candidate_ids(db, org.id, position_id)
    return {"ids": ids, "count": len(ids), "candidates": candidate_briefs(db, ids)}


@app.post("/positions/{position_id}/filter")
def filter_candidates(position_id: int, body: FilterRequest,
                      org=Depends(current_org), db: Session = Depends(get_db)):
    _position_or_404(db, org, position_id)
    return _filter_response(db, apply_recruiter_request(db, org.id, position_id, body.request, body.ids))


@app.post("/positions/{position_id}/filter/reset")
def reset_candidate_filters(position_id: int, org=Depends(current_org), db: Session = Depends(get_db)):
    _position_or_404(db, org, position_id)
    return _filter_response(db, reset_filters(db, org.id, position_id))


@app.get("/chat-sessions")
def list_chat_sessions(org=Depends(current_org), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ChatSession)
        .where(ChatSession.org_id == org.id)
        .order_by(ChatSession.updated_at.desc())
    ).all()
    positions = {
        p.id: p.title for p in db.scalars(select(Position).where(Position.org_id == org.id)).all()
    }
    return [{
        "id": row.id,
        "position_id": row.position_id,
        "position_title": positions.get(row.position_id, "Deleted position"),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "messages": row.messages or [],
        "current_candidate_ids": row.current_candidate_ids or [],
    } for row in rows]


@app.get("/positions/{position_id}/chat-session")
def get_chat_session(position_id: int, org=Depends(current_org), db: Session = Depends(get_db)):
    _position_or_404(db, org, position_id)
    row = db.scalar(select(ChatSession).where(
        ChatSession.org_id == org.id,
        ChatSession.position_id == position_id,
    ))
    if row is None:
        return {
            "id": None,
            "position_id": position_id,
            "messages": [],
            "current_candidate_ids": [],
            "candidates": [],
        }
    return {
        "id": row.id,
        "position_id": row.position_id,
        "messages": row.messages or [],
        "current_candidate_ids": row.current_candidate_ids or [],
        "candidates": candidate_briefs(db, row.current_candidate_ids or []),
    }


@app.put("/positions/{position_id}/chat-session")
def save_chat_session(position_id: int, body: ChatSessionRequest,
                      org=Depends(current_org), db: Session = Depends(get_db)):
    _position_or_404(db, org, position_id)
    row = db.scalar(select(ChatSession).where(
        ChatSession.org_id == org.id,
        ChatSession.position_id == position_id,
    ))
    if row is None:
        row = ChatSession(
            org_id=org.id,
            position_id=position_id,
            messages=body.messages,
            current_candidate_ids=body.current_candidate_ids,
        )
        db.add(row)
    else:
        row.messages = body.messages
        row.current_candidate_ids = body.current_candidate_ids
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "position_id": row.position_id,
        "messages": row.messages or [],
        "current_candidate_ids": row.current_candidate_ids or [],
    }