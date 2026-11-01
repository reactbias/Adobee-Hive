import re
from datetime import date
from typing import Optional

from .schemas import CVExtraction

_ONGOING = {"present", "current", "now", "today", "ongoing", "heute", "actuel"}
_DEGREE_RANK = {"High School": 1, "Vocational": 2, "Certificate/Diploma": 2, "Associate": 3,
                "Bachelor": 4, "Master": 5, "MBA": 5, "PhD": 6, "Postdoc": 7, "Other": 0}


def _parse_ym(value: Optional[str], today: date) -> Optional[date]:
    if not value:
        return None
    v = value.strip().lower()
    if v in _ONGOING:
        return today
    m = re.search(r"(\d{4})(?:-(\d{1,2}))?", v)
    if not m:
        return None
    month = int(m.group(2) or 1)
    return date(int(m.group(1)), month if 1 <= month <= 12 else 1, 1)


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def compute_derived(ex: CVExtraction, short_tenure_months: int = 24, gap_months: int = 6) -> dict:
    today = date.today().replace(day=1)

    jobs = []
    for w in ex.work_experience:
        start = _parse_ym(w.start_date, today)
        end = today if w.is_current else _parse_ym(w.end_date, today)
        if start and end and end >= start:
            dur = _months(start, end) + 1
        else:
            dur = w.duration_months
        jobs.append((w, start, end, dur))

    durations = [d for *_, d in jobs if d is not None]
    short_tenures = [
        {"job_title": w.job_title, "company": w.company, "duration_months": d}
        for w, _, _, d in jobs
        if d is not None and d < short_tenure_months and not w.is_current
        and w.employment_type not in ("Internship", "Contract", "Freelance")
    ]

    # Employment gaps + total experience from merged intervals (handles overlapping jobs)
    intervals = sorted([(s, e) for _, s, e, _ in jobs if s and e and e >= s])
    gaps, merged = [], []
    for s, e in intervals:
        if merged and _months(merged[-1][1], s) - 1 >= gap_months:
            gaps.append({"from": merged[-1][1].strftime("%Y-%m"), "to": s.strftime("%Y-%m"),
                         "months": _months(merged[-1][1], s) - 1})
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    computed_months = sum(_months(s, e) + 1 for s, e in merged)

    countries = list({w.country.strip().lower(): w.country.strip()
                      for w in ex.work_experience if w.country}.values())
    companies = list(dict.fromkeys(w.company.strip() for w in ex.work_experience if w.company))

    grad_years = []
    for ed in ex.education:
        d = _parse_ym(ed.graduation_date, today)
        if d:
            grad_years.append(d.year)
    latest_grad = max(grad_years) if grad_years else None

    highest = ex.highest_education_level
    if highest is None and ex.education:
        levels = [e.degree_level for e in ex.education if e.degree_level]
        highest = max(levels, key=lambda l: _DEGREE_RANK.get(l, 0)) if levels else None

    c = ex.contact
    missing_contact = [k for k, v in {"email": c.email, "phone": c.phone}.items() if not v]
    max_team = max((w.team_size_managed for w in ex.work_experience if w.team_size_managed), default=None)

    return {
        "num_jobs": len(ex.work_experience),
        "companies": companies,
        "avg_tenure_months": round(sum(durations) / len(durations), 1) if durations else None,
        "short_tenures": short_tenures,
        "num_short_tenures": len(short_tenures),
        "employment_gaps": gaps,
        "computed_years_experience": round(computed_months / 12, 1) if computed_months else None,
        "countries_worked": countries,
        "worked_multiple_countries": len(countries) > 1,
        "latest_graduation_year": latest_grad,
        "years_since_graduation": (today.year - latest_grad) if latest_grad else None,
        "highest_education_level": highest,
        "max_team_size_managed": max_team,
        "contact_complete": not missing_contact,
        "contact_missing": missing_contact,
        "has_linkedin": any(s.platform == "LinkedIn" for s in ex.social_links),
        "has_github": any(s.platform == "GitHub" for s in ex.social_links),
    }

_SENIORITY = ["Student/Intern", "Entry", "Mid", "Senior", "Lead/Principal", "Manager", "Director", "Executive"]
_TITLE_LEVELS = [(r"\b(chief|cto|ceo|cfo|coo|vp|vice president)\b", "Executive"),
                 (r"\b(director|head of)\b", "Director"),
                 (r"\b(staff|principal|lead|architect)\b", "Lead/Principal")]


def enforce_career_level(title: Optional[str], level: Optional[str]) -> Optional[str]:
    """The LLM sometimes ignores the title->level rule; raise the level if the title demands it."""
    for pattern, forced in _TITLE_LEVELS:
        if title and re.search(pattern, title.lower()):
            if level not in _SENIORITY or _SENIORITY.index(level) < _SENIORITY.index(forced):
                return forced
            break
    return level
