"""Seeds a throw-away DB with synthetic candidates and runs stacked recruiter requests (uses the LLM).
Usage: python test_recruiter.py
"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
from cv_analyzer import config  # noqa: E402  (.env overrides env vars, so patch config before db import)

config.DATABASE_URL = f"sqlite:///{(tmp / 'test.db').as_posix()}"
config.STORAGE_DIR = tmp / "storage"

from cv_analyzer.db import CandidateProfile, CVDocument, Organization, Position, SessionLocal, init_db  # noqa: E402
from cv_analyzer.recruiter_agent import (all_candidate_ids, apply_recruiter_request,  # noqa: E402
                                         reset_filters)

# name, location, country, title, level, years, tech skills, tools, countries worked
CANDS = [
    ("Anna Keller",   "Zurich",   "Switzerland", "Backend Engineer",  "Senior", 8.0, ["Python", "Microservices"], ["AWS", "Docker"], ["Switzerland"]),
    ("Anna Keller 2", "Zurich",   "Switzerland", "Backend Engineer",  "Senior", 8.0, ["Python", "Microservices"], ["AWS", "Docker"], ["Switzerland"]),  # near-twin
    ("Luca Meier",    "Basel",    "Switzerland", "Software Engineer", "Mid",    3.0, ["Java"],                    ["Azure"],         ["Switzerland"]),
    ("Jonas Weber",   "Berlin",   "Germany",     "DevOps Engineer",   "Senior", 7.0, ["Python", "Terraform"],     ["AWS", "Kubernetes"], ["Germany"]),
    ("Sara Lopez",    "Madrid",   "Spain",       "Data Engineer",     "Mid",    4.5, ["Python", "SQL"],           ["GCP"],           ["Spain", "Switzerland"]),
    ("Mike Brown",    "Seattle, WA", "United States", "Staff Software Engineer", "Lead/Principal", 12.0, ["Python", "Go"], ["AWS", "Terraform"], ["United States"]),
    ("Eva Novak",     "Geneva",   "Switzerland", "Frontend Developer", "Entry", 1.0, ["JavaScript"],              ["Figma"],         ["Switzerland"]),
]


def seed():
    init_db()
    with SessionLocal() as s:
        org = Organization(name="T", api_key="k")
        s.add(org); s.flush()
        pos = Position(org_id=org.id, title="Eng", description="x", custom_fields=[])
        s.add(pos); s.flush()
        for i, (n, loc, ctry, title, lvl, yrs, tech, tools, cw) in enumerate(CANDS, 1):
            doc = CVDocument(org_id=org.id, position_id=pos.id, original_filename=f"{n}.pdf",
                             stored_path="-", file_hash=str(i), status="done")
            s.add(doc); s.flush()
            data = {"work_experience": [{"job_title": title}], "education": [], "certifications": []}
            s.add(CandidateProfile(document_id=doc.id, org_id=org.id, position_id=pos.id, full_name=n,
                                   location=loc, country=ctry, current_job_title=title, career_level=lvl,
                                   total_years_experience=yrs, technical_skills=tech,
                                   software_and_tools=tools, countries_worked=cw, num_jobs=2,
                                   data=data, derived={}, languages=[], additional_info=[]))
        s.commit()
        return org.id, pos.id


def names(s, ids):
    rows = s.query(CandidateProfile.id, CandidateProfile.full_name).filter(CandidateProfile.id.in_(ids)).all()
    return sorted(n for _, n in rows)


org_id, pos_id = seed()
with SessionLocal() as s:
    ids = all_candidate_ids(s, org_id, pos_id)
    print(f"start: {len(ids)} candidates")
    for req in ["only people based in Swiss cities",
                "with at least 5 years of experience",
                "who know Python and some cloud platform",
                "not from Zurich"]:
        r = apply_recruiter_request(s, org_id, pos_id, req, ids)
        print(f"\n> {req}\n  {r.action}: {r.explanation}\n  {r.previous_count} -> {len(r.ids)}: {names(s, r.ids)}")
        print("  trace:", r.trace)
        ids = r.ids
    r = apply_recruiter_request(s, org_id, pos_id, "actually, start over and clear everything", ids)
    print(f"\n> start over\n  {r.action}: {len(r.ids)} candidates")
    r = apply_recruiter_request(s, org_id, pos_id, "the 1 most experienced Swiss-based candidate", r.ids)
    print(f"\n> top-1 tie test\n  {r.explanation}\n  {names(s, r.ids)}   (both Anna twins must stay)")
    r = apply_recruiter_request(s, org_id, pos_id, "what's the weather like?", r.ids)
    print(f"\n> off-topic\n  {r.action}: ids unchanged = {len(r.ids)}")
    print(f"\nreset helper: {len(reset_filters(s, org_id, pos_id).ids)} candidates")


# ---- numeric value missing in the structured columns -> LLM must read the stored CV text ----
with SessionLocal() as s:
    org = s.query(Organization).first()
    pos = s.query(Position).first()
    for j, (n, jobs) in enumerate([
            ("Unknown Years A", [("Backend Engineer", "Acme", "2015-03", "2024-06")]),
            ("Unknown Years B", [("Junior Developer", "Beta", "2025-01", "2025-09")])], 100):
        doc = CVDocument(org_id=org.id, position_id=pos.id, original_filename=f"{n}.pdf",
                         stored_path="-", file_hash=str(j), status="done")
        s.add(doc); s.flush()
        data = {"work_experience": [{"job_title": t, "company": c, "start_date": a, "end_date": b}
                                    for t, c, a, b in jobs], "education": [], "certifications": []}
        s.add(CandidateProfile(document_id=doc.id, org_id=org.id, position_id=pos.id, full_name=n,
                               location="Bern", country="Switzerland", total_years_experience=None,
                               data=data, derived={}, languages=[], additional_info=[]))
    s.commit()
    r = apply_recruiter_request(s, org.id, pos.id, "at least 5 years of experience, based in Bern")
    print("\n> missing-number fallback:", names(s, r.ids), "(expected only Unknown Years A)")
    for t in r.trace:
        print("  ", t["field"], t["op"], "llm_checked:", t["llm_checked"], t["llm_evidence"])
