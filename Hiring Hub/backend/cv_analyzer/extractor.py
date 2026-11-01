import base64
from dataclasses import dataclass
from datetime import date
from typing import Optional

from openai import (APIConnectionError, APITimeoutError, InternalServerError,
                    OpenAI, RateLimitError)
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from . import config
from .documents import LoadedDocument
from .schemas import CVExtraction, RelevanceScreening
import ssl

import httpx

SYSTEM_PROMPT = """
You are an expert HR data analyst. You receive the pages of ONE candidate CV as images
(the primary source: use them to understand layout, columns and sections). Optionally you
also receive the raw PDF text layer and embedded hyperlinks; use those to copy exact
spellings of names, emails, phone numbers and URLs.

Extract the information into the provided JSON schema.

GENERAL RULES
- Extract only what is stated or directly inferable from clear context. Never invent
  companies, dates, degrees, skills or links.
- Unknown single value -> null. Nothing found for a list -> []. Never use placeholders
  such as "Not Available" or "None Mentioned".
- Dates: "YYYY-MM" if the month is known, otherwise "YYYY". Ongoing roles: end_date
  "Present" and is_current = true.
- If a role only gives a duration ("5 years") and no calendar dates, set start_date and end_date to null
  and fill duration_months. NEVER infer or back-calculate calendar dates that are not on the CV.
- Write descriptions in English; keep proper nouns (companies, schools, products) as written.
- Deduplicate lists. Keep skills short and canonical ("Python", not "Python programming").

FIELD GUIDANCE
- job_category (per role) / job_categories (overall): broad families such as "Data Science",
  "Software Engineering", "Network Engineering", "Sales", "Finance", "HR", "Marketing",
  "Operations", "Design", "Product Management", "Management". Include all families if the
  candidate transitioned between domains.
- industry / industry_sectors: infer from company or context; null if unclear.
- achievements: measurable outcomes (numbers, %, scale, impact). Plain duties go into
  responsibilities.
- technical_skills: languages, frameworks, methods, technical domains.
  software_and_tools: concrete products used hands-on (Excel, Jira, SAP, Tableau, AWS ...).
  soft_skills: only if stated or clearly demonstrated.
- highest_education_level: the highest completed (or clearly ongoing) degree level.
- continuous_learning: courses, MOOCs, bootcamps, self-study, recent certifications.
- quality.generic_phrases: up to 5 vague statements lacking context/action/result.
- quality.unsubstantiated_skills: skills listed but not backed by any role, project or achievement.
- key_takeaways: up to 5 short themes that summarise the profile.
- additional_info: ANY relevant information that does not fit another field, e.g. work permit /
  visa, nationality, date of birth, availability / notice period, salary expectations,
  driving license, security clearance, military service, hobbies, references.
  Use a short snake_case key.
- total_years_experience: compute from the work-history dates up to today's date (given in the
  user message). Ignore claims such as "over 8 years" in the summary.
- career_level: based on the most recent role. Staff / Principal / Lead / Architect -> "Lead/Principal";
  people managers -> "Manager"; Head of / Director -> "Director"; VP / C-level -> "Executive".
- All country fields: full English country name ("United States", "Germany", "Switzerland").
- technical_skills / software_and_tools: short canonical names (1-3 words). Do not turn summary
  phrases into skills ("high-throughput data pipelines" is not a skill). Put each item in only ONE
  of the two lists. Name cloud services consistently with the vendor prefix ("AWS EC2", "AWS S3").
- team_size_managed: only formal reporting lines. Mentoring does not count; mention it in
  responsibilities instead.
- custom_fields: answer exactly the custom questions listed in the user message, one entry per
  question, in the same order and with the same field_name. If not found: value null,
  confidence "not_found". If no questions are listed, return [].
""".strip()

_client: Optional[OpenAI] = None


def _build_http_client() -> httpx.Client:
    """Use the Windows certificate store (needed behind the corporate proxy)."""
    try:
        import truststore
        verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        verify = True
    return httpx.Client(verify=verify, timeout=config.OPENAI_TIMEOUT)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            http_client=_build_http_client(),
            max_retries=0,   # tenacity already retries; avoid retrying twice
        )
    return _client


@dataclass
class ExtractionResult:
    data: CVExtraction
    model: str
    prompt_tokens: int
    completion_tokens: int


def _build_user_content(doc: LoadedDocument, custom_fields: list[dict]) -> list[dict]:
    parts: list[dict] = [{
        "type": "text",
        "text": f"Today's date: {date.today():%Y-%m}. "
                f"Here is a CV with {len(doc.images)} page image(s). Extract it into the schema.",
    }]
    for img, mime in doc.images:
        b64 = base64.b64encode(img).decode("ascii")
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}})

    if config.INCLUDE_TEXT_LAYER and doc.text:
        parts.append({"type": "text",
                      "text": "PDF text layer (reading order may be imperfect):\n"
                              + doc.text[: config.MAX_TEXT_CHARS]})
    if doc.links:
        parts.append({"type": "text", "text": "Embedded hyperlinks:\n" + "\n".join(doc.links)})

    if custom_fields:
        lines = [f"{i}. field_name: {f['name']} | question: {f.get('description') or f['name']}"
                 for i, f in enumerate(custom_fields, 1)]
        parts.append({"type": "text", "text": "Custom questions for custom_fields:\n" + "\n".join(lines)})
    else:
        parts.append({"type": "text", "text": "No custom questions: return custom_fields as []."})
    return parts


@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def extract_cv(doc: LoadedDocument, custom_fields: Optional[list[dict]] = None,
               model: Optional[str] = None) -> ExtractionResult:
    client = get_client()
    model = model or config.OPENAI_MODEL
    custom_fields = custom_fields or []

    # `parse` moved out of beta in recent SDK versions; support both.
    parse = getattr(client.chat.completions, "parse", None) or client.beta.chat.completions.parse

    # reasoning models don't accept temperature
    extra = {} if model.startswith(("o1", "o3", "o4", "gpt-5")) else {"temperature": 0}

    completion = parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_content(doc, custom_fields)},
        ],
        response_format=CVExtraction,
        **extra,
    )
    msg = completion.choices[0].message
    if getattr(msg, "refusal", None):
        raise RuntimeError(f"Model refused: {msg.refusal}")
    if msg.parsed is None:
        raise RuntimeError("Model returned no parsable output")

    usage = completion.usage
    return ExtractionResult(
        data=msg.parsed,
        model=completion.model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )

SCREENING_PROMPT = """
You are a pragmatic recruiter doing a first, generous screening pass (a human reviews the shortlist later). You receive ONE candidate CV (page images, optionally
the text layer) and a job posting. Decide whether the candidate is a plausible fit and should be
considered for this job.

- relevant = true if the candidate's experience/education overlaps with the core of the posting (same
  or adjacent professional field). Be lenient on seniority, years of experience and missing
  nice-to-haves: one or two gaps are fine, the recruiter can filter later. Only reject candidates
  from an unrelated field or far below the level (e.g. students without professional experience).
- Judge on evidence in the CV; do not assume skills that are not shown.
- A candidate in the same professional field who has fewer years than asked, a different stack, or is
  one level below (e.g. a 3-year Java/Azure backend engineer for a Python/AWS senior role) is a
  plausible fit: score 45-60, relevant = true. Missing years or tools alone never justify rejection.
- score: 0-30 unrelated field, 31-39 weak, 40-74 plausible fit with gaps, 75-100 strong fit.
- relevant must be consistent with the score (relevant only if score >= 40).
- Write reason in English, 1-2 sentences.
""".strip()


@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def screen_cv(doc: LoadedDocument, job_title: str, job_description: str,
              model: Optional[str] = None) -> tuple[RelevanceScreening, int, int]:
    """Check CV fit against a job posting. Returns (screening, prompt_tokens, completion_tokens)."""
    client = get_client()
    model = model or config.OPENAI_MODEL
    parse = getattr(client.chat.completions, "parse", None) or client.beta.chat.completions.parse
    extra = {} if model.startswith(("o1", "o3", "o4", "gpt-5")) else {"temperature": 0}

    parts: list[dict] = [{
        "type": "text",
        "text": f"JOB POSTING\nTitle: {job_title}\n\n{job_description}\n\n"
                f"CANDIDATE CV ({len(doc.images)} page image(s)):",
    }]
    for img, mime in doc.images:
        b64 = base64.b64encode(img).decode("ascii")
        # "auto" is enough to judge fit and cheaper than the "high" used for extraction
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    if config.INCLUDE_TEXT_LAYER and doc.text:
        parts.append({"type": "text", "text": "PDF text layer:\n" + doc.text[: config.MAX_TEXT_CHARS]})

    completion = parse(
        model=model,
        messages=[{"role": "system", "content": SCREENING_PROMPT},
                  {"role": "user", "content": parts}],
        response_format=RelevanceScreening,
        **extra,
    )
    msg = completion.choices[0].message
    if getattr(msg, "refusal", None):
        raise RuntimeError(f"Model refused: {msg.refusal}")
    if msg.parsed is None:
        raise RuntimeError("Model returned no parsable screening output")
    usage = completion.usage
    return (msg.parsed, usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0)
