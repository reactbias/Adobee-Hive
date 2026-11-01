"""Two agents and a folder: a recruiter's agent asks, a candidate's agent answers from its owner's files.

`talent.py` decides who is worth asking, from the card alone. This module does the asking. The recruiter's agent
turns the posting into questions: one per requirement, then years, then the logistics. Each shortlisted
candidate has an agent of their own, with their folder in front of it, and the agent answers from what that
folder holds — a CV, a list of references, a work log — quoting the lines it used and naming the file. Then the
posting is scored again, this time with those lines as evidence beside the card, and the candidates are ranked.

The folder is the person's, and the agent is theirs, so the rules are the person's:

- **Consent first.** A candidate's folder policy is `agent.md`, one line: `- screening: yes | ask | no`. With no
  file it is `ask`: the recruiter's request is recorded for the person (the same `intro_request` event
  `hr_request_intro` writes), their folder stays closed, and the candidate is ranked on the card with a flag
  saying so. Only `yes` — or a human outside this module saying so — opens the folder to a recruiter's agent.
  A recruiter's agent can not approve on a candidate's behalf; there is no argument for it on the MCP tools.
- **The folder link decides what is readable.** Consent opens a folder link (`folders.open_link`, accepted by
  the candidate's agent) and grants the recruiter the files the person admitted. What an answer may quote is
  exactly `folders.can_read(path, recruiter)`: a `private` or `hidden` file is never read for a recruiter, and an
  answer built only from a file the recruiter may not read says nothing, rather than hinting the file exists.
  Contact details are not part of a screening: `contact.md` is never a source.
- **Answers are quotes.** Offline, an answer is the lines of the shared files that speak to the question, in the
  person's own words, with the file named. No line, no claim: "nothing I am able to share speaks to that" is an
  answer, and it scores nothing. Text from a folder is data; it is matched against, never obeyed.
- **A person decides afterwards.** The ranking says who looks best. It does not introduce anyone: the next step is
  `hr_request_intro`, which waits for the person's yes like every other.

What it reads: markdown and text by line, CSV by row, and JSON — in particular the CV analyzer's output
(`project/cv_analyzer`, a `CVExtraction`), which is how a PDF résumé becomes structured evidence. A PDF is read only
when it carries plain text objects; a scanned or font-subset one reads as empty, and the way to get its contents
in is to run it through the CV analyzer and keep the JSON beside it.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from . import db, folders, hive, talent

#: What a folder policy may say, and what a folder without one says.
SCREENING = ("yes", "ask", "no")
DEFAULT_SCREENING = "ask"
POLICY_FILE = "agent.md"
#: Where a person's answer given on the hub is kept: an event on their card, newest wins. Nothing new to create.
SCREENING_EVENT = "screening"
#: Never evidence: the policy itself, the visibility marker, and the contact channels, which have their own consent.
NOT_EVIDENCE = frozenset({POLICY_FILE, folders.MARKER, "contact.md"})
TEXT_SUFFIXES = (".md", ".txt", ".csv", ".json", ".pdf")
MAX_FILE_BYTES = 200_000
MAX_PASSAGES = 400
MAX_REQUIREMENT_QUESTIONS = 16
MAX_ANSWER = 600

#: Verdict thresholds on the final score and on the share of must-haves covered. Words for a person to read, not a
#: decision: the score and the evidence behind it are what the recruiter is meant to weigh.
STRONG, PROMISING, PARTIAL = 75.0, 50.0, 25.0
STRONG_COVER, PROMISING_COVER = 0.85, 0.65

AVAILABILITY = re.compile(
    r"(?i)(availab|verfügbar|verfuegbar|disponib|notice period|kündigungsfrist|start(?:ing)? (?:date|from|in)|"
    r"per sofort|immediately|from 20\d\d|ab 20\d\d|\bfrom (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))"
)
RATE = re.compile(
    r"(?i)(CHF|EUR|€|\$|salary|gehalt|honorar|tarif|stundensatz|day rate|hourly|per (?:hour|day)|/ ?(?:day|hour|h)\b)"
)


# --- what a folder holds -----------------------------------------------------------------------------------


def _pdf_text(body: bytes) -> str:
    """The text objects of a simple PDF, or an empty string when there are none to read.

    A fixed, honest subset: `(…) Tj` strings in plain or Flate streams. Fonts with custom encodings, scans
    and anything encrypted read as empty on purpose — wrong text is worse than none.
    """
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", body, re.S):
        raw = match.group(1)
        with contextlib.suppress(zlib.error):
            raw = zlib.decompress(raw)
        chunks.append(raw)
    lines: list[str] = []
    for chunk in chunks:
        for string in re.findall(rb"\(((?:\\.|[^\\()])*)\)\s*Tj", chunk):
            text = re.sub(rb"\\([()\\])", rb"\1", string)
            try:
                lines.append(text.decode("utf-8"))
            except UnicodeDecodeError:
                lines.append(text.decode("cp1252", errors="replace"))
    return "\n".join(line.strip() for line in lines if line.strip())


def _text_lines(text: str) -> list[str]:
    """Markdown or plain text as the lines worth quoting: bullets without their dash, sentences of prose."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or set(line) <= set("-=_*| "):
            continue
        line = re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", line)
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", line) if len(s.split()) >= 2]
    return out


def _csv_lines(text: str) -> list[str]:
    """A CSV as one line per row, "column: value; column: value", so a row can be quoted as it stands."""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return []
    head = [h.strip() for h in rows[0]]
    return ["; ".join(f"{h}: {v.strip()}" for h, v in zip(head, row, strict=False) if v.strip()) for row in rows[1:]]


def _chunks(label: str, items: Iterable[Any], size: int = 5) -> list[str]:
    """A long list as lines of a few items each, so a quote stays short and still names its section."""
    flat = [str(i).strip() for i in items if i and str(i).strip()]
    return [f"{label}: {', '.join(flat[i : i + size])}" for i in range(0, len(flat), size)]


def cv_lines(data: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """A CV analyzer extraction as lines of evidence, and the facts that are numbers.

    Accepts the pipeline's whole output (`{"document", "extraction", "derived"}`) or a bare `CVExtraction`. Contact
    details are not read at all. What comes back: one line per job responsibility and achievement with the role
    and company in front of it, so a quote is self-explaining, and the skills in short groups.
    """
    cv = data.get("extraction") if isinstance(data.get("extraction"), dict) else data
    derived = data.get("derived") if isinstance(data.get("derived"), dict) else {}
    lines: list[str] = []
    for key in ("professional_summary", "current_job_title"):
        if cv.get(key):
            lines.append(str(cv[key]))
    for job in cv.get("work_experience") or []:
        title = job.get("job_title") or "Role"
        where = f" at {job['company']}" if job.get("company") else ""
        span = f" ({job.get('start_date') or '?'}–{job.get('end_date') or '?'})" if job.get("start_date") else ""
        lines.append(f"{title}{where}{span}")
        for item in [*(job.get("responsibilities") or []), *(job.get("achievements") or [])]:
            lines.append(f"{title}{where}: {item}")
    for edu in cv.get("education") or []:
        lines.append(", ".join(str(edu[k]) for k in ("degree", "field_of_study", "institution") if edu.get(k)))
    lines += [str(c.get("name")) for c in cv.get("certifications") or [] if c.get("name")]
    lines += _chunks("Technical skills", cv.get("technical_skills") or [])
    lines += _chunks("Tools", cv.get("software_and_tools") or [])
    lines += _chunks("Strengths", cv.get("soft_skills") or [])
    lines += _chunks(
        "Languages", [f"{x.get('language')} ({x.get('proficiency') or 'n/a'})" for x in cv.get("languages") or []]
    )
    for project in cv.get("projects") or []:
        lines.append(f"{project.get('name') or 'Project'}: {project.get('description', '')}")
    lines += [str(t) for t in cv.get("key_takeaways") or []]
    facts: dict[str, Any] = {}
    years = cv.get("total_years_experience") or derived.get("computed_years_experience")
    if years:
        facts["years"] = float(years)
        lines.append(f"{float(years):g} years of professional experience")
    place = ", ".join(
        str(cv.get("contact", {}).get(k)) for k in ("location", "country") if cv.get("contact", {}).get(k)
    )
    if place:
        facts["place"] = place
        lines.append(f"Based in {place}")
    return [line for line in lines if line.strip()], facts


def _json_lines(text: str) -> tuple[list[str], dict[str, Any]]:
    """A JSON file as lines: a CV extraction in the analyzer's shape, or any other document leaf by leaf."""
    try:
        data = json.loads(text)
    except ValueError:
        return [], {}
    if isinstance(data, dict) and ("extraction" in data or "work_experience" in data):
        return cv_lines(data)
    leaves: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and node.strip():
            leaves.append(f"{key}: {node}" if key else node)

    walk(data)
    return leaves, {}


@dataclass
class Disclosure:
    """What one candidate's agent may use for one recruiter: lines, where each came from, and what it counts as."""

    units: list[talent.Unit] = field(default_factory=list)
    visibility: dict[str, str] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def files(self) -> list[str]:
        """The files this recruiter may read, which is all an answer can ever quote."""
        return sorted(self.visibility)


# --- the candidate's agent -------------------------------------------------------------------------------


@dataclass
class Answer:
    """What a candidate's agent said to one question, and what it rests on."""

    text: str
    support: str  # direct | related | weak | none
    strength: float = 0.0
    quotes: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """The answer as the transcript shows it."""
        return {"text": self.text, "support": self.support, "strength": round(self.strength, 2), "quotes": self.quotes}


@dataclass
class Question:
    """One thing the recruiter's agent asks, and what it is about."""

    id: str
    text: str
    kind: str  # requirement | years | availability | rate | place | follow_up
    requirement: talent.Requirement | None = None


class CandidateAgent:
    """The agent that sits with one person's folder and speaks for them to a recruiter's agent."""

    def __init__(self, card: dict[str, Any]) -> None:
        """Bind to a published card; its id is the handle of the folder that belongs to it."""
        self.card = card
        self.handle = folders.handle_for(card["id"])

    # policy and consent

    def _own(self, rel: str) -> bytes:
        """One of this person's own files, read as its owner."""
        return folders.read(f"{self.handle}/{rel}", self.handle)

    def entries(self) -> list[dict[str, Any]]:
        """The person's whole folder, as they see it. Empty when this hub holds none."""
        return folders.files(self.handle)

    def policy(self) -> str:
        """What this person has said about screening interviews: yes, ask or no. `ask` when they have said nothing.

        Their latest answer through `set_screening` (the person, on the hub) outranks the line in their folder's
        `agent.md`, because a later decision is the one they mean. Neither is the recruiter's to set.
        """
        with db.cursor() as cur:
            row = cur.execute(
                "SELECT detail FROM hive_events WHERE card_id = ? AND kind = ? ORDER BY created_at DESC LIMIT 1",
                [self.card["id"], SCREENING_EVENT],
            ).fetchone()
        if row and row[0] in SCREENING:
            return row[0]
        if not any(e["path"] == POLICY_FILE for e in self.entries()):
            return DEFAULT_SCREENING
        text = self._own(POLICY_FILE).decode("utf-8", errors="replace")
        found = re.search(r"(?im)^\s*[-*]?\s*screening\s*:\s*(\w+)", text)
        value = found.group(1).lower() if found else ""
        return value if value in SCREENING else DEFAULT_SCREENING

    def consent(self, recruiter: str, job_title: str, approved: bool = False) -> dict[str, Any]:
        """Whether the folder opens for this recruiter, and what that opened.

        `approved` is the person's yes given somewhere other than this process (a click, a signed message). It
        is a Python argument and not a tool argument on purpose: the recruiter's agent must not be able to say it.
        """
        if not self.entries():
            return {"state": "no_folder", "why": "this hub holds no folder for them; ranked on their card alone"}
        policy = self.policy()
        if policy == "no":
            return {"state": "declined", "why": "their folder says they do not take screening interviews"}
        if policy == "ask" and not approved:
            message = f"Screening interview for: {job_title[:120]}"
            hive.record_event(
                self.card["id"], "intro_request", json.dumps({"from": recruiter[:200], "message": message})
            )
            return {
                "state": "awaiting_consent",
                "why": "they have asked to be asked; the request is recorded for them and their folder stays closed",
            }
        folders.open_link(recruiter, self.handle, auto_accept=True, by=self.handle)
        granted = []
        for entry in self.entries():
            if entry["path"] in NOT_EVIDENCE or not entry["path"].lower().endswith(TEXT_SUFFIXES):
                continue
            if entry["visibility"] in (folders.PUBLIC_SUMMARY, folders.SHARED):
                folders.grant(f"{self.handle}/{entry['path']}", recruiter)
                granted.append(entry["path"])
        return {
            "state": "granted",
            "why": "their folder says yes" if policy == "yes" else "approved",
            "granted": granted,
        }

    # what may be used

    def open_for(self, recruiter: str) -> Disclosure:
        """The lines of this folder that `recruiter` may read, and nothing else.

        Every file is asked about with `folders.can_read` for that recruiter, so this is the folder link's own
        rule and not a second copy of it: no link and no grant leaves only what is `public`.
        """
        disclosure = Disclosure()
        for entry in self.entries():
            rel = entry["path"]
            if rel in NOT_EVIDENCE or not rel.lower().endswith(TEXT_SUFFIXES) or entry["bytes"] > MAX_FILE_BYTES:
                continue
            if not folders.can_read(f"{self.handle}/{rel}", recruiter):
                continue
            body = self._own(rel)
            lines, facts = self._lines(rel, body)
            disclosure.visibility[rel] = entry["visibility"]
            disclosure.facts.update(facts)
            field_ = "cv" if rel.lower().endswith(".json") else "folder"
            for line in lines[:MAX_PASSAGES]:
                if (u := talent.unit(field_, line, source=rel)) is not None:
                    disclosure.units.append(u)
        return disclosure

    @staticmethod
    def _lines(rel: str, body: bytes) -> tuple[list[str], dict[str, Any]]:
        """A file's lines by what it is, and the numeric facts it states."""
        suffix = rel.lower().rsplit(".", 1)[-1]
        if suffix == "pdf":
            return _text_lines(_pdf_text(body)), {}
        text = body.decode("utf-8", errors="replace")
        if suffix == "json":
            return _json_lines(text)
        if suffix == "csv":
            return _csv_lines(text), {}
        return _text_lines(text), {}

    # answering

    def answer(self, question: Question, disclosure: Disclosure, used: set[str]) -> Answer:
        """Answer one question from `disclosure`, quoting lines not already quoted in `used`."""
        if question.kind == "requirement" and question.requirement is not None:
            return self._about(question.requirement, disclosure, used)
        if question.kind == "follow_up" and question.requirement is not None:
            return self._about(question.requirement, disclosure, used, more=True)
        if question.kind == "years":
            return self._years(disclosure)
        pattern = {"availability": AVAILABILITY, "rate": RATE, "place": None}[question.kind]
        return self._by_pattern(question.kind, pattern, disclosure, used)

    @staticmethod
    def _quote(e: talent.Evidence) -> dict[str, str]:
        """One line, as a quote that names the file it came from."""
        assert e.unit is not None
        return {"text": talent._clip(e.unit.text, 160), "source": e.unit.source}

    def _about(
        self, requirement: talent.Requirement, disclosure: Disclosure, used: set[str], more: bool = False
    ) -> Answer:
        """What the shared files say about one requirement: the best lines for it, in the person's own words."""
        # A follow-up asks for something further, so it skips what was quoted for this requirement already. A
        # first answer does not: one line may well be the best evidence for two different requirements.
        skip = used if more else set()
        found = [e for e in talent.rank(requirement, disclosure.units, top=6) if e.unit and e.unit.text not in skip]
        if not found:
            best = talent.match(requirement, [u for u in disclosure.units if u.text not in skip])
            found = [best] if best.unit else []
        label = requirement.label
        if not found:
            said = "Nothing further" if more else "Nothing"
            return Answer(f"{said} in what I am able to share speaks to {label}.", "none")
        top = found[0]
        quotes = [self._quote(e) for e in found[:2]]
        used.update(e.unit.text for e in found[:2] if e.unit)
        lines = " ".join(f"“{q['text']}” ({q['source']})" for q in quotes)
        if top.how == "literal" and top.strength >= talent.COVERED:
            return Answer(f"Yes, {label}: {lines}", "direct", top.strength, quotes)
        if top.covered:
            return Answer(f"Close to {label}, not exactly: {lines}", "related", top.strength, quotes)
        return Answer(f"Only loosely related to {label}: {lines}", "weak", top.strength, quotes)

    def _years(self, disclosure: Disclosure) -> Answer:
        """How long, from a number the shared files state, or from a line that says so."""
        if "years" in disclosure.facts:
            years = disclosure.facts["years"]
            source = next((u.source for u in disclosure.units if u.field == "cv"), "cv.json")
            return Answer(
                f"About {years:g} years of professional experience.",
                "direct",
                1.0,
                [{"text": f"{years:g} years", "source": source}],
            )
        for u in disclosure.units:
            if (years := talent.years_in(u.text)) is not None:
                quote = {"text": talent._clip(u.text, 160), "source": u.source}
                return Answer(
                    f"About {years:g} years, by my own account: “{quote['text']}” ({u.source}).",
                    "related",
                    0.6,
                    [quote],
                )
        return Answer("My shared files do not state how many years.", "none")

    def _by_pattern(self, kind: str, pattern: re.Pattern[str] | None, disclosure: Disclosure, used: set[str]) -> Answer:
        """Logistics are not skills: lines are chosen by what they say (a date, a price), not by requirement words."""
        pool = [u for u in disclosure.units if u.text not in used]
        if kind == "place":
            facts = disclosure.facts.get("place")
            lines = [
                u
                for u in pool
                if re.search(r"(?i)\b(based in|remote|zürich|zurich|basel|bern|hybrid|on-?site)\b", u.text)
            ]
            if facts and not lines:
                return Answer(f"Based in {facts}.", "direct", 1.0, [{"text": f"Based in {facts}", "source": "cv.json"}])
        else:
            assert pattern is not None
            lines = [u for u in pool if pattern.search(u.text)]
        if not lines:
            what = {"availability": "when I could start", "rate": "my rates", "place": "where I am based"}[kind]
            return Answer(f"My shared files do not say {what}; that would be a question for the person.", "none")
        lines = list({u.text.lower(): u for u in lines}.values())
        quotes = [{"text": talent._clip(u.text, 160), "source": u.source} for u in lines[:2]]
        return Answer(" ".join(f"“{q['text']}” ({q['source']})" for q in quotes), "direct", 1.0, quotes)


# --- the recruiter's agent -------------------------------------------------------------------------------


class RecruiterAgent:
    """The agent that works for the company: it reads the posting as questions and the answers as a ranking."""

    def __init__(self, handle: str, job: talent.Job) -> None:
        """A recruiter's agent has a handle on the hub (its end of every folder link) and the posting it works to."""
        self.handle = handle
        self.job = job

    def questions(self) -> list[Question]:
        """The posting as questions: each requirement, then years, then the logistics."""
        asked: list[Question] = []
        ordered = sorted(self.job.requirements, key=lambda r: {"must": 0, "role": 1, "nice": 2}[r.kind])
        for n, req in enumerate(ordered, 1):
            if req.kind == "nice":
                text = f"Do you have experience with {req.label}? It is a plus for this role."
            else:
                text = f"What is your hands-on experience with {req.label}? Concrete work, tools, how long."
            asked.append(Question(f"q{n}", text, "requirement", req))
        asked = asked[:MAX_REQUIREMENT_QUESTIONS]
        if self.job.min_years:
            asked.append(
                Question(
                    "years",
                    f"How many years of professional experience do you have? We ask for {self.job.min_years:g}+.",
                    "years",
                )
            )
        asked.append(Question("availability", "When could you start, and at what workload?", "availability"))
        if self.job.location:
            where = f"{self.job.location}, or remote" if self.job.remote_ok else self.job.location
            asked.append(Question("place", f"Where are you based, and would {where} work for you?", "place"))
        asked.append(Question("rate", "What are your rates?", "rate"))
        return asked

    def follow_up(self, question: Question, answer: Answer) -> Question | None:
        """One more question when an answer was thin: ask for a concrete example, once."""
        if question.kind == "requirement" and answer.support in ("related", "weak") and question.requirement:
            label = question.requirement.label
            return Question(
                f"{question.id}b",
                f"Can you give one concrete example involving {label}?",
                "follow_up",
                question.requirement,
            )
        return None

    @staticmethod
    def verdict(result: talent.Scored) -> str:
        """Words for a score: strong, promising, partial or weak. The number and the evidence are what to read."""
        covered = result.musts_met / len(result.musts) if result.musts else 1.0
        if result.score >= STRONG and covered >= STRONG_COVER:
            return "strong"
        if result.score >= PROMISING and covered >= PROMISING_COVER:
            return "promising"
        return "partial" if result.score >= PARTIAL else "weak"


def set_screening(card_id: str, screening: str) -> dict[str, Any]:
    """Record a person's answer to screening interviews: yes, ask or no. Their card must exist on this hub.

    The caller is whoever holds this hub's owner credential, which is one shared secret and not an account
    (see LIMITS.md), so what this proves is "an owner of something here", the same standing as a card edit.
    """
    if screening not in SCREENING:
        raise hive.HiveError(f"screening must be one of {', '.join(SCREENING)}")
    card = hive.get_card(card_id)
    hive.record_event(card["id"], SCREENING_EVENT, screening)
    return {"card_id": card["id"], "screening": screening}


# --- the interview -----------------------------------------------------------------------------------------


def interview(agent: CandidateAgent, recruiter: RecruiterAgent, consent: dict[str, Any]) -> dict[str, Any]:
    """Run one interview: the recruiter's questions to one candidate's agent, and the rescoring from the answers."""
    disclosure = agent.open_for(recruiter.handle)
    quoted: dict[str, set[str]] = {}  # the lines already used, per subject
    transcript: list[dict[str, Any]] = []

    def turn(question: Question) -> Answer:
        about = question.requirement.label if question.requirement else question.kind
        answer = agent.answer(question, disclosure, quoted.setdefault(about, set()))
        transcript.append(
            {
                "question": question.text,
                "about": about,
                "answer": answer.to_dict() | {"text": answer.text[:MAX_ANSWER]},
            }
        )
        return answer

    for question in recruiter.questions():
        answer = turn(question)
        if follow_up := recruiter.follow_up(question, answer):
            turn(follow_up)
    final = talent.score(
        recruiter.job, agent.card, extra=disclosure.units, years=disclosure.facts.get("years"), years_from="CV shows"
    )
    hive.record_event(agent.card["id"], "interviewed", f"agent {recruiter.handle}")
    return {"consent": consent, "read": disclosure.files, "transcript": transcript, "final": final}


def run(
    posting: str | talent.Job,
    *,
    recruiter: str = "recruiter",
    limit: int = 5,
    approve: Iterable[str] = (),
    kinds: tuple[str, ...] = (talent.KIND,),
) -> dict[str, Any]:
    """The whole path: search the cards, ask each shortlisted person's agent, rank on what came back.

    `approve` names candidates whose person has said yes outside this call. It exists for tests, a command-line
    demo and a future owner-side button; no MCP tool passes it, so a recruiter's agent can not self-approve.
    """
    job = posting if isinstance(posting, talent.Job) else talent.parse_job(posting)
    handle = folders.handle_for(recruiter)
    folders.claim(handle)
    agent = RecruiterAgent(handle, job)
    found = talent.search(job, limit=limit, kinds=kinds)
    approved = {a.lower() for a in approve}
    ranked: list[dict[str, Any]] = []
    for match in found["matches"]:
        card = hive.get_card(match["id"])
        candidate = CandidateAgent(card)
        if candidate.handle == handle:
            continue
        consent = candidate.consent(handle, job.title, approved=card["id"].lower() in approved)
        entry: dict[str, Any] = {
            "id": card["id"],
            "name": card["name"],
            "stage1_score": match["score"],
            "consent": consent,
        }
        if consent["state"] == "granted":
            done = interview(candidate, agent, consent)
            final: talent.Scored = done["final"]
            entry |= {
                "status": "interviewed",
                "score": round(final.score, 1),
                "verdict": agent.verdict(final),
                "musts_met": final.musts_met,
                "musts_total": len(final.musts),
                "strengths": [e.requirement.label for e in final.evidence if e.covered],
                "gaps": final.gaps,
                "years": {"stated": final.years, "note": final.years_note},
                "read": done["read"],
                "transcript": done["transcript"],
            }
        else:
            entry |= {
                "status": consent["state"],
                "score": match["score"],
                "verdict": "not interviewed",
                "musts_met": match["musts_met"],
                "musts_total": match["musts_total"],
                "strengths": [e["requirement"] for e in match["evidence"] if e["covered"]],
                "gaps": match["gaps"],
                "years": match["years"],
            }
        ranked.append(entry)
    ranked.sort(key=lambda r: (-r["score"], r["id"]))
    for position, entry in enumerate(ranked, 1):
        entry["rank"] = position
    return {
        "job": job.to_dict(),
        "recruiter": handle,
        "ranking": ranked,
        "excluded": found["excluded"],
        "summary": summarise(job, ranked, found["considered"]),
        "next_step": (
            "Nobody has been introduced. To meet someone, hr_request_intro waits for that person's yes; "
            "anyone marked awaiting_consent has a recorded request and an unopened folder."
        ),
        "ranking_policy": talent.RANKING_POLICY,
    }


def summarise(job: talent.Job, ranked: list[dict[str, Any]], considered: int) -> str:
    """A paragraph a recruiter can read first. Written from the numbers, so it can not say more than they do."""
    done = [r for r in ranked if r["status"] == "interviewed"]
    waiting = [r for r in ranked if r["status"] == "awaiting_consent"]
    head = (
        f"{considered} people on this hub were read against “{job.title}”; "
        f"{len(ranked)} were worth asking, {len(done)} were interviewed."
    )
    if not done:
        asked = ", ".join(r["name"] for r in waiting[:5])
        return head + (
            f" None could be interviewed: {asked} have been asked and must say yes first." if waiting else ""
        )
    best = done[0]
    line = (
        f" Best: {best['name']}, {best['score']:g}/100 ({best['verdict']}), "
        f"covering {best['musts_met']} of {best['musts_total']} must-haves."
    )
    if best["gaps"]:
        line += f" Not shown for: {', '.join(best['gaps'][:4])}."
    if waiting:
        line += f" Still waiting on a yes: {', '.join(r['name'] for r in waiting[:5])}."
    return head + line
