"""
Recruiter filter agent.

The frontend keeps the list of candidate ids that are currently "in play" and sends it back with each
new request. The agent only ever narrows that list, so filters stack indefinitely; a reset is simply
a call without ids (or `reset_filters`), which starts again from every candidate of the position.

    ids = all_candidate_ids(s, org_id, position_id)                       # initial / reset
    r = apply_recruiter_request(s, org_id, position_id,
                                "only people based in Swiss cities", ids)  # r.ids is the new list
    r = apply_recruiter_request(s, org_id, position_id,
                                "with at least 5 years of Python", r.ids)  # narrows r.ids further

The LLM does NOT see candidate data row by row and does NOT write free-form SQL. It translates the
request into a small, validated filter spec (semantic understanding: "Swiss cities" -> Zurich, Basel,
Bern, ...; "cloud" -> AWS, Azure, GCP, ...). The spec is then executed deterministically, so equal
candidates always get equal results: two near-identical CVs are both kept or both dropped, and a
"top N" request keeps everybody tied at the cut-off.
"""
import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import date
from dataclasses import dataclass, field
from typing import Literal, Optional

from openai import (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import (retry, retry_if_exception_type, stop_after_attempt, wait_exponential)

from . import config
from .db import CandidateProfile
from .extractor import get_client

FilterField = Literal[
    "location",            # current city/region + country of residence
    "country_worked",      # any country the candidate has worked in
    "skill",               # technical skills + tools + soft skills + certifications (the split between
                           # technical/tool is inconsistent in CVs, so it is not exposed separately)
    "certification", "language",
    "job_title",           # current OR past job titles
    "current_job_title",
    "job_category", "industry", "company",
    "career_level", "education_level", "field_of_study",
    "years_experience", "num_jobs", "avg_tenure_months", "team_size_managed",
    "additional_info",     # visa, notice period, nationality, ... (key + value text)
    "any_text",            # last resort: full-text over the whole extracted profile
]
NUMERIC_FIELDS = {"years_experience", "num_jobs", "avg_tenure_months", "team_size_managed"}


class Condition(BaseModel):
    field: FilterField
    op: Literal["any", "all", "none", "gte", "lte"] = Field(
        description="any = has at least one of values; all = has every value; none = has none of "
                    "values (exclusion); gte/lte = numeric comparison using `number`")
    values: list[str] = Field(description="Expanded, concrete search terms. Empty for gte/lte.")
    number: Optional[float] = Field(description="Only for gte/lte, else null")
    requirement: str = Field(description="The condition restated as a plain sentence about a candidate, "
                                         "e.g. 'Has at least 5 years of professional experience'")


class Ordering(BaseModel):
    field: Literal["years_experience", "num_jobs", "avg_tenure_months", "team_size_managed"]
    direction: Literal["desc", "asc"]
    limit: int = Field(description="Keep this many; candidates tied at the cut-off are all kept")


class FilterPlan(BaseModel):
    action: Literal["filter", "reset", "no_filter"] = Field(
        description="reset = recruiter wants to clear all filters / start over; "
                    "no_filter = the message is not a candidate-filtering request")
    conditions: list[Condition] = Field(description="ALL conditions must hold (AND)")
    ordering: Optional[Ordering]
    explanation: str = Field(description="One sentence for the recruiter: what is being applied")


SYSTEM_PROMPT = """
You translate a recruiter's natural-language request into a structured filter over a candidate database.
The candidates currently in play are narrowed by your conditions; you never see individual candidates.

RULES
- Understand the MEANING, then expand into concrete terms the data would contain:
  "Swiss cities" -> location any [Zurich, ZÃ¼rich, Basel, Bern, Geneva, GenÃ¨ve, Lausanne, Lugano, Switzerland, ...];
  "cloud experience" -> skill any [AWS, Azure, GCP, Google Cloud, Kubernetes, ...];
  "senior or above" -> career_level any [Senior, Lead/Principal, Manager, Director, Executive];
  "master or higher" -> education_level any [Master, MBA, PhD, Postdoc].
  Include common spelling / language variants and the country name together with its cities.
- Use the DATA OVERVIEW (values that really exist for the current candidates) to choose terms; you may
  add terms not listed there when the request implies them.
- RECALL matters: for each concept list 6-15 related terms - synonyms, abbreviations, singular/plural,
  neighbouring technologies or job titles, local-language names ("cloud" -> AWS, Azure, GCP, Google Cloud,
  EC2, S3, Lambda, serverless, IaaS; "backend" -> server-side, API, microservices, Django, Flask, Spring).
  Matching already tolerates accents and small spelling errors, so do not add typos.
- Be precise about granularity: a city request ("not from Zurich") uses only that city and its spelling
  variants, NEVER its country or region. Add the country only when the request names a country/region
  or a group of cities. For exclusions (op none) do the opposite of the recall rule and expand narrowly - a wrong expansion silently removes
  good candidates.
- Never add skill terms the recruiter did not ask for; "some cloud platform" is ONE condition (op any)
  while "Python" is a separate condition. Use op all only when every listed value is required.
- One recruiter request may need several conditions (they are ANDed). Use op "none" for exclusions
  ("not from Berlin", "no job hoppers" -> avg_tenure_months gte 24).
- "at least N years" -> years_experience gte N. "between" -> two conditions.
- Pick the narrowest sensible field; use any_text only when no specific field fits.
- "top N / most experienced N" -> ordering with limit. Do not use ordering unless a count is requested.
- If the recruiter wants to clear/reset/start over -> action "reset". If the same message also asks for something ("start over and show X"), keep action
  "reset" AND encode X as conditions.
- If the message is not about filtering candidates -> action "no_filter".
- Keep earlier filters implicit: they are already applied to the candidate list. Only encode the NEW request.
""".strip()


# ---------- candidate view used for matching ----------
def _norm(v) -> str:
    """Lower-case, accent-folded (Zürich == zurich), whitespace-collapsed."""
    s = unicodedata.normalize("NFKD", str(v or "").replace("ß", "ss"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def _candidate_values(p: CandidateProfile) -> dict[str, list[str]]:
    d, dv = p.data or {}, p.derived or {}
    work = d.get("work_experience", [])
    edu = d.get("education", [])
    titles = [w.get("job_title") for w in work if w.get("job_title")]
    add = [f"{a['key']} {a['value']}" for a in (p.additional_info or [])]
    base = {
        "location": [p.location, p.country],
        "country_worked": list(p.countries_worked or []),
        "technical_skill": list(p.technical_skills or []),
        "tool": list(p.software_and_tools or []),
        "soft_skill": list(p.soft_skills or []),
        "certification": [c.get("name") for c in d.get("certifications", [])],
        "language": [l.get("language") for l in (p.languages or [])],
        "job_title": titles + [p.current_job_title],
        "current_job_title": [p.current_job_title],
        "job_category": list(p.job_categories or []),
        "industry": list(p.industry_sectors or []),
        "company": list(p.companies or []),
        "career_level": [p.career_level],
        "education_level": [p.highest_education_level],
        "field_of_study": [e.get("field_of_study") for e in edu] + [e.get("degree") for e in edu],
        "additional_info": add,
    }
    # skills are also searched in the role descriptions: technologies are often only named there
    work_text = [t for w in work for t in (w.get("responsibilities") or []) + (w.get("achievements") or [])]
    base["skill"] = (list(p.technical_skills or []) + list(p.software_and_tools or [])
                     + list(p.soft_skills or []) + base["certification"] + work_text)
    base["any_text"] = [json.dumps(d, ensure_ascii=False, default=str)]
    num = {"years_experience": p.total_years_experience, "num_jobs": p.num_jobs,
           "avg_tenure_months": p.avg_tenure_months,
           "team_size_managed": dv.get("max_team_size_managed")}
    out = {k: [_norm(x) for x in v if x] for k, v in base.items()}
    out.update({f"#{k}": [v] for k, v in num.items() if v is not None})
    return out


FUZZY_MIN_LEN = 5          # shorter terms ("AWS", "Go", "SQL") must match exactly
FUZZY_RATIO = 0.86         # tolerance for typos / spelling variants ("Kubernets", "Zurch")
FUZZY_RATIO_EXCLUDE = 0.93  # stricter when the match REMOVES a candidate


def _has(term: str, haystack: list[str], ratio: float = FUZZY_RATIO) -> bool:
    t = _norm(term)
    if not t:
        return False
    pat = re.compile(rf"(?<!\w){re.escape(t)}(?!\w)")
    if any(pat.search(h) for h in haystack):
        return True
    if len(t) < FUZZY_MIN_LEN:
        return False
    n = len(t.split())
    for h in haystack:
        if len(h) > 3000:                       # whole-profile text: exact match only
            continue
        words = h.split()
        for i in range(max(1, len(words) - n + 1)):
            w = " ".join(words[i:i + n]).strip(".,;:()")
            if abs(len(w) - len(t)) <= 2 and SequenceMatcher(None, t, w).ratio() >= ratio:
                return True
    return False


def _matches(cand: dict, c: Condition) -> Optional[bool]:
    """True/False, or None when a numeric value is not stored for this candidate (-> LLM reads the CV)."""
    if c.field in NUMERIC_FIELDS:
        vals = cand.get(f"#{c.field}")
        if not vals or c.number is None:
            return None
        return vals[0] >= c.number if c.op == "gte" else vals[0] <= c.number
    hay = cand.get(c.field, [])
    if c.op == "any":
        return any(_has(v, hay) for v in c.values)
    if c.op == "all":
        return all(_has(v, hay) for v in c.values)
    if c.op == "none":
        return not any(_has(v, hay, FUZZY_RATIO_EXCLUDE) for v in c.values)
    return False


def _validate(plan: FilterPlan) -> None:
    for c in plan.conditions:
        if c.field in NUMERIC_FIELDS:
            if c.op not in ("gte", "lte") or c.number is None:
                raise ValueError(f"Numeric field {c.field} needs op gte/lte and a number")
        elif c.op in ("gte", "lte") or not c.values:
            raise ValueError(f"Field {c.field} needs op any/all/none with at least one value")


# ---------- public API ----------
@dataclass
class FilterResult:
    ids: list[int]                       # candidate (profile) ids that remain -> send back next time
    action: str                          # filter | reset | no_filter
    explanation: str
    previous_count: int
    plan: Optional[dict] = None          # the executed filter spec (for display / audit)
    trace: list[dict] = field(default_factory=list)   # candidates left after each condition

    @property
    def removed(self) -> int:
        return self.previous_count - len(self.ids)


def all_candidate_ids(s: Session, org_id: int, position_id: Optional[int] = None) -> list[int]:
    q = select(CandidateProfile.id).where(CandidateProfile.org_id == org_id)
    if position_id is not None:
        q = q.where(CandidateProfile.position_id == position_id)
    return list(s.scalars(q.order_by(CandidateProfile.id)))


def candidate_briefs(s: Session, ids: list[int]) -> list[dict]:
    """Small rows for the frontend table (keeps the order of `ids`)."""
    rows = {p.id: p for p in s.scalars(select(CandidateProfile).where(CandidateProfile.id.in_(ids)))} \
        if ids else {}
    return [{"id": p.id, "document_id": p.document_id, "full_name": p.full_name, "email": p.email,
             "location": p.location, "current_job_title": p.current_job_title,
             "career_level": p.career_level, "total_years_experience": p.total_years_experience,
             "key_takeaways": p.key_takeaways} for i in ids if (p := rows.get(i))]


def reset_filters(s: Session, org_id: int, position_id: Optional[int] = None) -> FilterResult:
    ids = all_candidate_ids(s, org_id, position_id)
    return FilterResult(ids, "reset", "All filters cleared.", len(ids))


def _overview(profiles: list[CandidateProfile]) -> str:
    def uniq(vals, n=60):
        seen = {}
        for v in vals:
            if v:
                seen[v] = seen.get(v, 0) + 1
        return [k for k, _ in sorted(seen.items(), key=lambda kv: -kv[1])][:n]

    skills = [x for p in profiles for x in (p.technical_skills or []) + (p.software_and_tools or [])]
    return json.dumps({
        "candidates": len(profiles),
        "locations": uniq(p.location for p in profiles),
        "countries": uniq(p.country for p in profiles),
        "countries_worked": uniq(x for p in profiles for x in p.countries_worked or []),
        "job_categories": uniq(x for p in profiles for x in p.job_categories or []),
        "industries": uniq(x for p in profiles for x in p.industry_sectors or []),
        "career_levels": uniq(p.career_level for p in profiles),
        "education_levels": uniq(p.highest_education_level for p in profiles),
        "languages": uniq(l.get("language") for p in profiles for l in p.languages or []),
        "top_skills": uniq(skills, 150),
    }, ensure_ascii=False)


@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def plan_request(request: str, overview: str, model: Optional[str] = None) -> FilterPlan:
    client = get_client()
    model = model or config.OPENAI_MODEL
    parse = getattr(client.chat.completions, "parse", None) or client.beta.chat.completions.parse
    extra = {} if model.startswith(("o1", "o3", "o4", "gpt-5")) else {"temperature": 0}
    completion = parse(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": f"DATA OVERVIEW (current candidates):\n{overview}\n\n"
                                              f"RECRUITER REQUEST:\n{request}"}],
        response_format=FilterPlan,
        **extra,
    )
    msg = completion.choices[0].message
    if getattr(msg, "refusal", None):
        raise RuntimeError(f"Model refused: {msg.refusal}")
    if msg.parsed is None:
        raise RuntimeError("Model returned no parsable filter plan")
    return msg.parsed


VERIFY_PROMPT = """
You check whether candidates meet ONE requirement, using only the extracted CV data of each candidate
(JSON: work history with dates/durations, education, summary, additional info ...). The structured
number for this requirement is missing, so work it out from the text, e.g. add up role durations or
count from the dates (today's date is given). Do not guess: if the CV gives no basis, answer false.
Return one verdict per candidate id.
""".strip()


class Verdict(BaseModel):
    id: int
    meets: bool
    evidence: str = Field(description="Short quote or calculation from the CV that justifies the verdict")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def verify_requirement(requirement: str, items: list[tuple[int, str]],
                       model: Optional[str] = None) -> dict[int, Verdict]:
    """LLM reads the stored CV text of candidates whose structured value is missing."""
    client = get_client()
    model = model or config.OPENAI_MODEL
    parse = getattr(client.chat.completions, "parse", None) or client.beta.chat.completions.parse
    extra = {} if model.startswith(("o1", "o3", "o4", "gpt-5")) else {"temperature": 0}
    body = "\n\n".join(f"--- CANDIDATE id={i} ---\n{text[:8000]}" for i, text in items)
    completion = parse(
        model=model,
        messages=[{"role": "system", "content": VERIFY_PROMPT},
                  {"role": "user", "content": f"Today: {date.today():%Y-%m-%d}\nREQUIREMENT: {requirement}\n\n{body}"}],
        response_format=Verdicts,
        **extra,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Model returned no parsable verdicts")
    return {v.id: v for v in parsed.verdicts}


def execute_plan(profiles: list[CandidateProfile], plan: FilterPlan,
                 verify: bool = True) -> tuple[list[int], list[dict]]:
    """Apply a validated plan. Deterministic except for candidates whose numeric value is missing:
    those are decided by an LLM that reads their stored CV data. Ties/identical CVs are never dropped."""
    _validate(plan)
    by_id = {p.id: p for p in profiles}
    cands = [(p.id, _candidate_values(p)) for p in profiles]
    trace = []
    for c in plan.conditions:
        results = [(i, v, _matches(v, c)) for i, v in cands]
        unknown = [(i, v) for i, v, r in results if r is None]
        llm_ok: dict[int, Verdict] = {}
        if unknown and verify:
            items = [(i, json.dumps(by_id[i].data, ensure_ascii=False, default=str)) for i, _ in unknown]
            for k in range(0, len(items), 15):
                llm_ok.update(verify_requirement(c.requirement, items[k:k + 15]))
        cands = [(i, v) for i, v, r in results
                 if r is True or (r is None and llm_ok.get(i) and llm_ok[i].meets)]
        trace.append({"field": c.field, "op": c.op, "values": c.values, "number": c.number,
                      "remaining": len(cands), "llm_checked": len(unknown) if verify else 0,
                      "llm_evidence": {i: x.evidence for i, x in llm_ok.items()}})
    if plan.ordering and cands:
        o = plan.ordering
        key = f"#{o.field}"
        known = [(i, v) for i, v in cands if v.get(key)]
        known.sort(key=lambda t: t[1][key][0], reverse=(o.direction == "desc"))
        if len(known) > o.limit > 0:
            cutoff = known[o.limit - 1][1][key][0]
            known = [t for t in known if (t[1][key][0] >= cutoff if o.direction == "desc"
                                          else t[1][key][0] <= cutoff)]   # ties all stay
        cands = known
        trace.append({"field": o.field, "op": f"top {o.limit} {o.direction}",
                      "remaining": len(cands)})
    return [i for i, _ in cands], trace


def apply_recruiter_request(s: Session, org_id: int, position_id: Optional[int], request: str,
                            current_ids: Optional[list[int]] = None,
                            model: Optional[str] = None) -> FilterResult:
    """Narrow `current_ids` (None = every candidate of the position) by a natural-language request."""
    if current_ids is None:
        current_ids = all_candidate_ids(s, org_id, position_id)
    q = select(CandidateProfile).where(CandidateProfile.org_id == org_id,
                                       CandidateProfile.id.in_(current_ids))
    if position_id is not None:                  # candidates of other jobs can never leak in
        q = q.where(CandidateProfile.position_id == position_id)
    profiles = list(s.scalars(q)) if current_ids else []
    current = [p.id for p in profiles]          # ignore ids from other orgs / deleted candidates

    plan = plan_request(request, _overview(profiles), model)
    if plan.action == "reset":
        if not plan.conditions and not plan.ordering:
            return reset_filters(s, org_id, position_id)
        # "forget everything and show X": restart from all candidates, then apply the new request only
        q = select(CandidateProfile).where(CandidateProfile.org_id == org_id)
        if position_id is not None:
            q = q.where(CandidateProfile.position_id == position_id)
        profiles = list(s.scalars(q))
        ids, trace = execute_plan(profiles, plan)
        return FilterResult(ids, "reset", plan.explanation, len(current), plan.model_dump(), trace)
    if plan.action == "no_filter" or (not plan.conditions and not plan.ordering):
        return FilterResult(current, "no_filter", plan.explanation, len(current), plan.model_dump())

    ids, trace = execute_plan(profiles, plan)
    return FilterResult(ids, "filter", plan.explanation, len(current), plan.model_dump(), trace)
