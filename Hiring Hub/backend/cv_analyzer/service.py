import secrets
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import (CandidateProfile, CandidateSkill, CVDocument, Organization, Position,
                 SessionLocal, utcnow)
from .derived import compute_derived, enforce_career_level
from .documents import SUPPORTED_EXT, filesystem_dates, load_document, sha256_file
from .extractor import ExtractionResult, extract_cv, screen_cv, screen_cv


# ---------- organizations / positions ----------
def create_organization(s: Session, name: str) -> Organization:
    org = Organization(name=name, api_key=secrets.token_urlsafe(32))
    s.add(org)
    s.commit()
    return org


def create_position(s: Session, org_id: int, title: str, description: Optional[str] = None,
                    custom_fields: Optional[list[dict]] = None) -> Position:
    pos = Position(org_id=org_id, title=title, description=description,
                   custom_fields=custom_fields or [])
    s.add(pos)
    s.commit()
    return pos


def import_job_postings(s: Session, org_id: int, folder: Path) -> list[Position]:
    """Create positions from text job postings, skipping titles already imported."""
    positions = []
    for path in sorted(folder.glob("*.txt")):
        description = path.read_text(encoding="utf-8-sig").strip()
        if not description:
            continue
        title = next((line.strip() for line in description.splitlines() if line.strip()), path.stem)
        existing = s.scalar(select(Position).where(Position.org_id == org_id,
                                                   Position.title == title))
        if existing is None:
            existing = next((position for position in
                             s.scalars(select(Position).where(Position.org_id == org_id)).all()
                             if position.title.lstrip("\ufeff") == title), None)
            if existing is not None and existing.title != title:
                existing.title = title
                s.commit()
        if existing:
            if existing.description != description:
                existing.description = description
                s.commit()
            positions.append(existing)
            continue
        positions.append(create_position(s, org_id, title, description))
    return positions


# ---------- ingestion ----------
def register_file(s: Session, org_id: int, position_id: Optional[int], src_path: str | Path,
                  original_filename: Optional[str] = None) -> tuple[CVDocument, bool]:
    """Copy file into storage and create a pending CVDocument. Returns (doc, created)."""
    src_path = Path(src_path)
    ext = src_path.suffix.lower()
    if ext not in SUPPORTED_EXT:
        raise ValueError(f"Unsupported file type {ext}")

    file_hash = sha256_file(src_path)
    existing = s.scalar(select(CVDocument).where(
        CVDocument.org_id == org_id,
        CVDocument.position_id.is_(position_id) if position_id is None
        else CVDocument.position_id == position_id,
        CVDocument.file_hash == file_hash,
    ))
    if existing:
        return existing, False

    created, modified = filesystem_dates(src_path)
    dest_dir = config.STORAGE_DIR / str(org_id) / str(position_id or "unassigned")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{file_hash}{ext}"
    shutil.copy2(src_path, dest)

    doc = CVDocument(org_id=org_id, position_id=position_id,
                     original_filename=original_filename or src_path.name,
                     stored_path=str(dest), file_hash=file_hash,
                     file_created_at=created, file_modified_at=modified, status="pending")
    s.add(doc)
    s.commit()
    return doc, True


def process_document(doc_id: int) -> str:
    """Run extraction for one document. Uses its own session (safe for background threads).

    DB transactions are kept short: nothing is held open during the slow LLM calls, otherwise parallel
    workers hit "database is locked" on SQLite."""
    with SessionLocal() as s:
        doc = s.get(CVDocument, doc_id)
        if doc is None:
            return "missing"
        doc.status, doc.error = "processing", None
        stored_path = doc.stored_path
        pos = doc.position
        pos_title, pos_desc = (pos.title, pos.description) if pos else (None, None)
        custom = list(pos.custom_fields or []) if pos else []
        s.commit()                                   # also ends the transaction

        try:
            loaded = load_document(stored_path, dpi=config.IMAGE_DPI, max_pages=config.MAX_PAGES)

            screening = None
            if config.SCREENING_ENABLED and pos_desc:
                screening, _, _ = screen_cv(loaded, pos_title, pos_desc)
            rejected = screening is not None and (
                not screening.relevant or screening.score < config.MIN_RELEVANCE_SCORE)
            result = derived = None
            if not rejected:
                result = extract_cv(loaded, custom_fields=custom)
                derived = compute_derived(result.data, config.SHORT_TENURE_MONTHS, config.GAP_MONTHS)

            # ---- short write transaction ----
            doc.page_count = loaded.page_count
            doc.pdf_created_at = loaded.pdf_created_at
            doc.pdf_modified_at = loaded.pdf_modified_at
            if rejected:
                # not a fit: store nothing about the candidate, only why the file was skipped
                if doc.profile is not None:
                    s.delete(doc.profile)
                missing = "; ".join(screening.missing_requirements)
                doc.status, doc.processed_at = "rejected", utcnow()
                doc.error = (f"Not relevant (score {screening.score}): {screening.reason} "
                             f"Missing: {missing}")
            else:
                _save_profile(s, doc, result, derived)
                doc.status, doc.processed_at = "done", utcnow()
            s.commit()
        except Exception as e:  # noqa: BLE001
            s.rollback()
            doc = s.get(CVDocument, doc_id)
            doc.status, doc.error = "failed", f"{type(e).__name__}: {e}"
            s.commit()
        return doc.status


def _save_profile(s: Session, doc: CVDocument, result: ExtractionResult, derived: dict):
    if doc.profile is not None:          # reprocessing -> replace
        s.delete(doc.profile)
        s.flush()

    ex = result.data
    p = CandidateProfile(
        document_id=doc.id, org_id=doc.org_id, position_id=doc.position_id,
        full_name=ex.contact.full_name, email=ex.contact.email, phone=ex.contact.phone,
        location=ex.contact.location, country=ex.contact.country,
        current_job_title=ex.current_job_title, career_level=enforce_career_level(ex.current_job_title, ex.career_level),
        total_years_experience=derived["computed_years_experience"] or ex.total_years_experience,
        highest_education_level=derived["highest_education_level"],
        num_jobs=derived["num_jobs"], num_short_tenures=derived["num_short_tenures"],
        avg_tenure_months=derived["avg_tenure_months"],
        worked_multiple_countries=derived["worked_multiple_countries"],
        contact_complete=derived["contact_complete"],
        years_since_graduation=derived["years_since_graduation"],
        cv_language=ex.cv_language,
        job_categories=ex.job_categories, industry_sectors=ex.industry_sectors,
        companies=derived["companies"], technical_skills=ex.technical_skills,
        soft_skills=ex.soft_skills, software_and_tools=ex.software_and_tools,
        languages=[l.model_dump() for l in ex.languages],
        countries_worked=derived["countries_worked"], key_takeaways=ex.key_takeaways,
        additional_info=[a.model_dump() for a in ex.additional_info],
        custom_fields=[c.model_dump() for c in ex.custom_fields],
        data=ex.model_dump(), derived=derived, model=result.model,
        prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
    )

    seen = set()
    groups = [("technical", ex.technical_skills), ("soft", ex.soft_skills),
              ("tool", ex.software_and_tools), ("language", [l.language for l in ex.languages]),
              ("certification", [c.name for c in ex.certifications])]
    for skill_type, values in groups:
        for v in values:
            norm = v.strip().lower()
            if norm and (norm, skill_type) not in seen:
                seen.add((norm, skill_type))
                p.skills.append(CandidateSkill(org_id=doc.org_id, skill=v.strip(),
                                               skill_normalized=norm, skill_type=skill_type))
    s.add(p)


# ---------- export for the pandas / dataframe-agent step ----------
LIST_COLS = ["job_categories", "industry_sectors", "companies", "technical_skills", "soft_skills",
             "software_and_tools", "countries_worked", "key_takeaways"]


def to_dataframe(s: Session, org_id: int, position_id: Optional[int] = None) -> pd.DataFrame:
    q = (select(CandidateProfile, CVDocument)
         .join(CVDocument, CandidateProfile.document_id == CVDocument.id)
         .where(CandidateProfile.org_id == org_id))
    if position_id is not None:
        q = q.where(CandidateProfile.position_id == position_id)

    rows = []
    for p, d in s.execute(q).all():
        row = {
            "profile_id": p.id, "document_id": d.id, "filename": d.original_filename,
            "position_id": p.position_id, "full_name": p.full_name, "email": p.email,
            "phone": p.phone, "location": p.location, "current_job_title": p.current_job_title,
            "career_level": p.career_level, "total_years_experience": p.total_years_experience,
            "highest_education_level": p.highest_education_level, "num_jobs": p.num_jobs,
            "num_short_tenures": p.num_short_tenures, "avg_tenure_months": p.avg_tenure_months,
            "worked_multiple_countries": p.worked_multiple_countries,
            "contact_complete": p.contact_complete,
            "years_since_graduation": p.years_since_graduation,
            "languages": [l["language"] for l in p.languages],
            "job_titles": [w["job_title"] for w in p.data["work_experience"] if w["job_title"]],
            "certifications": [c["name"] for c in p.data["certifications"]],
            "degrees": [e["degree"] for e in p.data["education"] if e["degree"]],
            "fields_of_study": [e["field_of_study"] for e in p.data["education"] if e["field_of_study"]],
            "additional_info": {a["key"]: a["value"] for a in p.additional_info},
            "pdf_created_at": d.pdf_created_at, "pdf_modified_at": d.pdf_modified_at,
        }
        for col in LIST_COLS:
            row[col] = getattr(p, col)
        for cf in p.custom_fields:                    # custom fields become real columns
            row[f"custom.{cf['field_name']}"] = cf["value"]
        rows.append(row)

    df = pd.DataFrame(rows)
    for col in LIST_COLS + ["languages", "job_titles", "certifications", "degrees"]:
        if col in df:
            df[f"{col}_count"] = df[col].apply(len)
    return df
