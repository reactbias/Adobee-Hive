"""Synthetic demo data: two jobs and ~60 fictional candidates. No real people.

Runs automatically on boot when the database is empty (SEED_ON_EMPTY=true),
or by hand: python -m app.seed
"""

import random

from . import db

JOBS = [
    {
        "id": "job-fullstack",
        "title": "Full-stack Engineer (Python / React)",
        "location": "Basel, Switzerland",
        "description": "Build our recruiting platform. FastAPI, React, SQL, cloud. 3+ years. German is a plus.",
    },
    {
        "id": "job-designer",
        "title": "Product Designer",
        "location": "Zurich, Switzerland",
        "description": "Own the UX of our applicant app. Figma, user research, Adobe CC. Hybrid.",
    },
]

FIRST = ["Lena", "Noah", "Mia", "Luca", "Aylin", "Jonas", "Sara", "Elias", "Nina", "Arjun", "Mei", "Omar",
         "Chiara", "David", "Fatima", "Leon", "Sofia", "Yusuf", "Anna", "Mateo", "Hana", "Felix", "Zoe", "Ravi"]
LAST = ["Meier", "Keller", "Rossi", "Nguyen", "Yilmaz", "Huber", "Schmid", "Khan", "Fischer", "Bianchi",
        "Wang", "Haddad", "Brunner", "Patel", "Weber", "Moreau", "Gerber", "Rahimi", "Baumann", "Costa"]
CITIES = ["Basel, Switzerland", "Zurich, Switzerland", "Bern, Switzerland", "Lausanne, Switzerland",
          "Freiburg, Germany", "Mulhouse, France", "Berlin, Germany", "Geneva, Switzerland"]
COMPANIES = ["Roche", "Novartis", "Syngenta", "Endress+Hauser", "Coop", "Swisscom", "Migros", "a Basel startup",
             "Lonza", "Bâloise", "SBB", "Google Zurich", "Siemens", "local agency"]
TRACKS = {
    "engineer": {
        "roles": ["Software Engineer", "Backend Developer", "Frontend Developer", "Data Engineer", "Full-stack Developer"],
        "skills": ["Python", "TypeScript", "JavaScript", "React", "FastAPI", "Django", "SQL", "PostgreSQL", "DuckDB",
                   "Docker", "Kubernetes", "AWS", "Azure", "Go", "Java", "Terraform", "LLM", "Machine Learning"],
        "edu": ["BSc Computer Science, FHNW", "MSc Computer Science, ETH Zurich", "BSc Informatics, University of Basel",
                "Apprenticeship Informatiker EFZ", "MSc Data Science, EPFL"],
    },
    "designer": {
        "roles": ["UX Designer", "Product Designer", "UI Designer", "Visual Designer", "UX Researcher"],
        "skills": ["Figma", "Photoshop", "Illustrator", "InDesign", "After Effects", "UX Research", "Prototyping",
                   "Design Systems", "HTML", "CSS", "Accessibility"],
        "edu": ["BA Visual Communication, HGK Basel", "BA Interaction Design, ZHdK", "MA Design, ECAL",
                "BSc Media Informatics, FHNW"],
    },
}
LANGS = ["English", "German", "French", "Italian", "Spanish", "Turkish", "Mandarin", "Hindi", "Arabic"]


def _seniority(years: float) -> str:
    return "junior" if years < 2 else "mid" if years < 5 else "senior" if years < 10 else "lead"


def candidates(n: int = 60, seed: int = 42) -> list[tuple[dict, str]]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        track_name = "engineer" if i % 3 else "designer"
        track = TRACKS[track_name]
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        years = round(rng.uniform(0.5, 14), 1)
        role = rng.choice(track["roles"])
        company = rng.choice(COMPANIES)
        skills = rng.sample(track["skills"], k=rng.randint(3, 7))
        langs = ["English"] + rng.sample([l for l in LANGS if l != "English"], k=rng.randint(0, 2))
        city = rng.choice(CITIES)
        start = 2026 - int(years)
        experiences = [
            {"company": company, "role": role, "start_year": max(start, 2026 - 3), "end_year": None,
             "description": f"{role} working with {', '.join(skills[:2])}."},
        ]
        if years > 3:
            experiences.append({"company": rng.choice(COMPANIES), "role": rng.choice(track["roles"]),
                                "start_year": start, "end_year": 2026 - 3, "description": "Earlier role."})
        parsed = {
            "full_name": name,
            "email": f"{name.lower().replace(' ', '.')}@example.com",
            "location": city,
            "headline": f"{_seniority(years).title()} {role} · {', '.join(skills[:3])}",
            "current_role": role,
            "current_company": company,
            "years_experience": years,
            "seniority": _seniority(years),
            "skills": skills,
            "languages": langs,
            "highest_education": rng.choice(track["edu"]),
            "summary": f"{role} with {years} years of experience, currently at {company}. Strongest in {skills[0]} and {skills[1]}.",
            "remote_ok": rng.random() < 0.5,
            "experiences": experiences,
            "_job": "job-designer" if track_name == "designer" else "job-fullstack",
            "_stage": rng.choices(db.STAGES, weights=[50, 20, 10, 6, 2, 12])[0],
        }
        out.append((parsed, f"Synthetic CV for {name}"))
    return out


def run() -> int:
    for job in JOBS:
        db.upsert_job(job)
    created = 0
    for parsed, raw in candidates():
        cid = db.insert_candidate(parsed, job_id=parsed["_job"], raw_text=raw, filename="seed", source="seed")
        db.set_stage(cid, parsed["_stage"])
        created += 1
    return created


def seed_if_empty() -> None:
    if db.count("candidates") == 0:
        run()


if __name__ == "__main__":
    db.init()
    print(f"Seeded {run()} candidates")
