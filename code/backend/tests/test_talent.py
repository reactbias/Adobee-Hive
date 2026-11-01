"""Talent search: a job posting read into requirements, and the person cards that cover them.

The corpus is the one the rest of the suite already trusts, `testdata/vaults/`, published through the same
`build_card` the seeder uses. Nothing here is written to fit a card: the postings are what a recruiter would
paste, and the assertions are about who should be asked and why.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app import blocklist, hive, llm, services, talent

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
POSTINGS = ROOT / "testdata" / "postings"

SOFTWARE = """Senior Software Engineer (Cloud & Backend)

We are looking for a Senior Software Engineer to design and run cloud-based backend services.

Requirements:
- 5+ years of professional software engineering experience
- Strong Python; experience with microservices and REST APIs
- Hands-on cloud experience (AWS, Azure or GCP), containers (Docker/Kubernetes), CI/CD
- Experience with SQL/NoSQL databases and data pipelines
- Nice to have: Terraform / infrastructure as code, mentoring junior engineers
"""

FRONTEND = """Frontend Developer (m/w/d) - Zürich

We are building an online shop and need someone to own the part customers see.

Requirements:
- 5+ years of professional frontend development experience
- Strong TypeScript; experience with Vue or React
- Experience with component libraries and design systems

Nice to have:
- Accessibility (WCAG) know-how
"""

WRITER = """Technical Writer

Requirements:
- Runbooks and release notes for engineering teams
- Fluent English; German is a plus
- Sits next to engineers and writes down what they know
"""


def _seed_vaults():
    """Load tools/seed_vaults.py as a module; it is a script, not part of the app package."""
    if "seed_vaults" in sys.modules:
        return sys.modules["seed_vaults"]
    spec = importlib.util.spec_from_file_location("seed_vaults", BACKEND / "tools" / "seed_vaults.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_vaults"] = module
    spec.loader.exec_module(module)
    return module


def publish_people() -> list[str]:
    """Publish every person vault in the test corpus, the way the seeder does, and return their ids."""
    seed = _seed_vaults()
    names = sorted(n for n, kind in seed.KIND.items() if kind == "person")
    for name in names:
        hive.publish(seed.build_card(seed.VAULTS / name))
    return names


@pytest.fixture
def people(fresh_hub) -> list[str]:
    """The eighteen people of the test corpus on an empty hub."""
    return publish_people()


def _by_label(job: talent.Job) -> dict[str, talent.Requirement]:
    return {r.label: r for r in job.requirements}


# --- reading the posting -------------------------------------------------------------------------------------


def test_a_run_of_alternatives_is_one_requirement_not_three():
    job = talent.parse_job(SOFTWARE)
    cloud = next(r for r in job.requirements if "AWS" in r.options)
    assert {"AWS", "Azure", "GCP"} <= set(cloud.options)
    assert cloud.kind == "must"
    assert sum("Azure" in r.options for r in job.requirements) == 1


def test_the_posting_is_split_into_what_it_asks_for():
    job = talent.parse_job(SOFTWARE)
    labels = [r.label for r in job.requirements]
    assert job.title == "Senior Software Engineer (Cloud & Backend)"
    assert job.min_years == 5.0
    for wanted in ("Python", "microservices", "REST APIs", "CI/CD", "data pipelines"):
        assert any(wanted in label for label in labels), f"{wanted} should be a requirement of its own: {labels}"
    kinds = {r.label: r.kind for r in job.requirements}
    assert kinds["Terraform / infrastructure as code"] == "nice"
    assert kinds["mentoring junior engineers"] == "nice"
    assert kinds["Python"] == "must"
    assert any(r.kind in ("role", "must") and "software" in r.label.lower() for r in job.requirements)
    assert job.parsed_by == "rules"


def test_a_plus_makes_one_piece_nice_to_have_and_a_language_is_a_fact_not_a_skill():
    job = talent.parse_job(WRITER)
    assert job.languages == ["en"], "'Fluent English' is a filter to check, not a skill to find"
    assert not any("English" in r.label for r in job.requirements)
    assert not any(r.kind == "must" and "German" in r.label for r in job.requirements)


def test_a_place_in_the_title_or_a_location_line_is_read_and_remote_cancels_it():
    assert talent.parse_job(FRONTEND).location == "Zürich"
    assert talent.parse_job("Analyst\n\nLocation: Basel, Switzerland\n- SQL").location == "Basel"
    assert talent.parse_job("Analyst - Basel\n\nFully remote.\n- SQL").remote_ok is True


def test_bullets_without_a_heading_are_requirements_and_responsibilities_are_not():
    job = talent.parse_job("Baker\n- Sourdough\n- Early mornings")
    assert [r.kind for r in job.requirements if r.kind != "role"] == ["must", "must"]
    job = talent.parse_job("Baker\n\nResponsibilities:\n- Open the shop\n\nRequirements:\n- Sourdough")
    assert [r.label for r in job.requirements if r.kind == "must"] == ["Sourdough"]


def test_two_verbs_on_one_object_are_one_requirement():
    job = talent.parse_job("Marketing Manager\n\n- Experience planning and managing campaign budgets")
    labels = [r.label for r in job.requirements if r.kind == "must"]
    assert labels == ["planning and managing campaign budgets"]


def test_an_empty_posting_is_refused_with_a_next_step():
    with pytest.raises(hive.HiveError, match="job posting"):
        talent.parse_job("  \n ")


def test_the_cv_projects_own_posting_parses_the_same(tmp_path):
    """The posting the CV analyzer was built around, read here without any change."""
    text = ROOT.parent / "project" / "job_postings" / "senior_software_engineer.txt"
    if not text.exists():
        pytest.skip("the project folder is not next to the repository")
    job = talent.parse_job(text.read_text(encoding="utf-8"))
    assert job.min_years == 5.0 and any("AWS" in r.options for r in job.requirements)


def test_words_are_compared_by_stem_and_a_few_aliases():
    assert talent.tokens("software engineering") == talent.tokens("Software Engineers")
    assert talent.tokens("Postgres") == talent.tokens("PostgreSQL")
    assert talent.tokens("K8s") == talent.tokens("Kubernetes")
    assert talent.tokens("Amazon Web Services") == talent.tokens("AWS")
    assert talent.tokens("development") == talent.tokens("developer")
    assert talent.tokens("Strong hands-on experience with Python") == talent.tokens("Python")


# --- searching the cards -------------------------------------------------------------------------------------


def test_the_frontend_developer_comes_first_and_the_backend_one_is_left_out(people):
    found = talent.search(talent.parse_job(FRONTEND))
    ids = [m["id"] for m in found["matches"]]
    assert ids[0] == "jonas-brun"
    assert "ilaria-conti" in ids[:3], "a React developer writing in Italian is still a frontend developer"
    assert "renzo-balmer" not in ids[:3], "Go on the server is not what the posting asks for"
    top = found["matches"][0]
    assert top["musts_met"] >= 3
    covered = {e["requirement"]: e for e in top["evidence"] if e["covered"]}
    assert covered["TypeScript"]["how"] == "literal" and "TypeScript" in covered["TypeScript"]["quote"]
    assert found["ranking_policy"].startswith("Share of the posting")


def test_a_card_is_not_found_by_what_it_needs(people):
    """Niko Ferrer is *looking for* a frontend contractor. That makes him the opposite of one."""
    found = talent.search(talent.parse_job(FRONTEND), limit=20)
    assert "niko-ferrer" not in {m["id"] for m in found["matches"][:5]}
    assert hive.get_card("niko-ferrer")["needs"], "the premise: he does list a need"
    quotes = [e.get("quote", "") for m in found["matches"] for e in m["evidence"] if m["id"] == "niko-ferrer"]
    assert not any("frontend contractor" in q for q in quotes)


def test_the_technical_writer_is_the_person_who_writes_runbooks(people):
    found = talent.search(talent.parse_job(WRITER))
    assert found["matches"][0]["id"] == "anouk-pfister"
    assert found["matches"][0]["score"] > found["matches"][1]["score"] + 10


def test_a_card_with_nothing_to_say_to_the_posting_is_listed_with_that_reason(people):
    found = talent.search(talent.parse_job(WRITER), limit=3)
    left_out = {e["id"]: e for e in found["excluded"]}
    assert "schnittwerk-bern" not in left_out, "only people are searched by default"
    assert left_out["ilaria-conti"]["why_not"] == ["nothing on the card speaks to any requirement"]
    assert found["considered"] == 18


def test_every_result_carries_its_reasons_and_no_contact_details(people):
    found = talent.search(talent.parse_job(SOFTWARE))
    for match in found["matches"]:
        assert match["evidence"] and match["signature_valid"] is True
        assert "contact" not in match and "email" not in str(match).lower()
    assert talent.search(talent.parse_job(SOFTWARE)) == found, "the same posting gives the same answer"


def test_a_stated_language_that_is_missing_excludes_and_a_silent_card_does_not(fresh_hub):
    base = {"kind": "person", "offers": [{"title": "Runbook writing", "summary": "Runbooks for engineers."}]}
    hive.publish({**base, "id": "p-german", "slug": "p-german", "name": "A", "languages": ["de"]})
    hive.publish({**base, "id": "p-silent", "slug": "p-silent", "name": "B"})
    hive.publish({**base, "id": "p-both", "slug": "p-both", "name": "C", "languages": ["de", "en"]})
    found = talent.search(talent.parse_job("Technical Writer\n\nRequirements:\n- Runbooks\n- Fluent English"))
    assert {m["id"] for m in found["matches"]} == {"p-silent", "p-both"}
    assert next(e for e in found["excluded"] if e["id"] == "p-german")["why_not"] == ["does not list en"]
    assert next(m for m in found["matches"] if m["id"] == "p-silent")["not_stated"] == ["languages not stated"]


def test_a_place_only_excludes_when_the_card_names_another_and_remote_lifts_it(fresh_hub):
    base = {"kind": "person", "offers": [{"title": "Bookkeeping", "summary": "Monthly books."}]}
    hive.publish({**base, "id": "p-basel", "slug": "p-basel", "name": "A", "location": "Basel"})
    hive.publish({**base, "id": "p-bern", "slug": "p-bern", "name": "B", "location": "Bern"})
    hive.publish({**base, "id": "p-none", "slug": "p-none", "name": "C"})
    onsite = talent.search(talent.parse_job("Bookkeeper - Basel\n\nRequirements:\n- Bookkeeping"))
    assert {m["id"] for m in onsite["matches"]} == {"p-basel", "p-none"}
    assert "tied to Basel" in next(e for e in onsite["excluded"] if e["id"] == "p-bern")["why_not"][0]
    remote = talent.search(talent.parse_job("Bookkeeper - Basel\n\nThis role is fully remote.\n- Bookkeeping"))
    assert {m["id"] for m in remote["matches"]} == {"p-basel", "p-bern", "p-none"}


def test_a_requirement_is_met_by_something_that_implies_it_and_the_result_says_so(fresh_hub):
    hive.publish({"id": "p-react", "slug": "p-react", "kind": "person", "name": "R", "offers": ["React shop builds"]})
    found = talent.search(talent.parse_job("Frontend Developer\n\nRequirements:\n- Frontend development"))
    evidence = found["matches"][0]["evidence"][0]
    assert (evidence["how"], evidence["covered"]) == ("related", True)
    assert evidence["strength"] < 1.0, "implying the thing is worth less than saying it"
    assert "react" in talent.parse_job("Frontend Developer\n\n- Frontend development").requirements[0].related


def test_a_near_miss_only_counts_when_the_semantic_floor_clears_and_is_labelled_similar(fresh_hub):
    hive.publish({"id": "p-cut", "slug": "p-cut", "kind": "person", "name": "H", "offers": ["Cut, wash and finish"]})
    found = talent.search(talent.parse_job("Hairdresser\n\nRequirements:\n- Haircut"))
    evidence = found["matches"][0]["evidence"][0]
    assert (evidence["how"], evidence["covered"]) == ("similar", True)
    assert evidence["strength"] < 1.0, "close is worth less than the thing"
    assert talent.search(talent.parse_job("Welder\n\n- Welding"))["matches"] == [], "nothing under the floor counts"


def test_stated_experience_counts_toward_the_score_and_unstated_is_not_held_against_a_card(fresh_hub):
    base = {"kind": "person", "offers": ["Python services"]}
    hive.publish({**base, "id": "p-old", "slug": "p-old", "name": "A", "description": "Python for nine years."})
    hive.publish({**base, "id": "p-new", "slug": "p-new", "name": "B", "description": "Python for two years."})
    hive.publish({**base, "id": "p-nil", "slug": "p-nil", "name": "C"})
    found = talent.search(talent.parse_job("Engineer\n\nRequirements:\n- 5+ years of Python"))
    by_id = {m["id"]: m for m in found["matches"]}
    assert by_id["p-old"]["years"] == {"stated": 9.0, "note": "states 9 years; 5+ asked"}
    assert by_id["p-new"]["score"] < by_id["p-old"]["score"]
    assert by_id["p-nil"]["years"]["stated"] is None and "not stated" in by_id["p-nil"]["years"]["note"]
    assert by_id["p-nil"]["score"] >= by_id["p-new"]["score"], "silence is not a short CV"


def test_blocked_and_withdrawn_people_are_not_searched(people):
    blocklist.block("entity", "jonas-brun", "test")
    ids = {m["id"] for m in talent.search(talent.parse_job(FRONTEND), limit=20)["matches"]}
    assert "jonas-brun" not in ids and "ilaria-conti" in ids


def test_being_shortlisted_is_logged_for_the_person_and_the_posting_is_not(people):
    from app import db

    found = talent.search(talent.parse_job("Quasar Wrangler Q7 Zephyr\n\n- React"))
    assert "ilaria-conti" in {m["id"] for m in found["matches"]}
    assert hive.owner_overview("ilaria-conti")["last_7_days"]["shown"] == 1
    with db.cursor() as cur:
        details = {r[0] for r in cur.execute("SELECT detail FROM hive_events WHERE kind = 'shown'").fetchall()}
    assert details == {"talent search"}, "what was logged is that they were looked at, never the posting"


# --- the optional model step ---------------------------------------------------------------------------------


def _model(monkeypatch, answer):
    """Switch a model on for one test and make it say `answer` (or raise it), counting how often it was asked."""
    asked = []

    def structured(system, user, schema, **kwargs):
        asked.append(user)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(services, "enabled", lambda: True)
    monkeypatch.setattr(llm, "structured", structured)
    return asked


def test_without_a_model_the_posting_is_not_sent_anywhere(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no model is configured, so none may be called")

    monkeypatch.setattr(services, "enabled", lambda: False)
    monkeypatch.setattr(llm, "structured", boom)
    job = talent.widen(talent.parse_job(FRONTEND))
    assert job.parsed_by == "rules"


def test_a_model_only_adds_terms_and_the_rules_still_do_the_matching(fresh_hub, monkeypatch):
    job = talent.parse_job("Hairdresser\n\nRequirements:\n- Colouring")
    index = next(i for i, r in enumerate(job.requirements) if r.label == "Colouring")
    asked = _model(
        monkeypatch,
        {
            "requirements": [
                {"id": index, "related": ["balayage", "Färben", "hair dye", "x" * 80, ""]},
                {"id": 99, "related": ["ignored"]},
                {"id": "nope", "related": ["ignored"]},
            ]
        },
    )
    widened = talent.widen(job)
    assert widened.parsed_by == "rules+model" and len(asked) == 1
    assert "Colouring" in asked[0] and "Hairdresser" in asked[0], "the model is shown the requirements"
    assert widened.requirements[index].related == ["balayage", "Färben", "hair dye"]
    hive.publish(
        {"id": "p-colour", "slug": "p-colour", "kind": "person", "name": "C", "offers": ["Balayage and toning"]}
    )
    hive.publish({"id": "p-none", "slug": "p-none", "kind": "person", "name": "N", "offers": ["Bookkeeping"]})
    found = talent.search(widened)
    assert [m["id"] for m in found["matches"]] == ["p-colour"]
    evidence = next(e for e in found["matches"][0]["evidence"] if e["requirement"] == "Colouring")
    assert evidence["how"] == "related" and evidence["strength"] < 1.0, "a model's term never beats the thing itself"


def test_a_model_that_fails_leaves_the_posting_as_the_rules_read_it(monkeypatch):
    _model(monkeypatch, llm.LLMError("declined"))
    job = talent.widen(talent.parse_job(FRONTEND))
    assert job.parsed_by == "rules" and job.requirements[0].related
