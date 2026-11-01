"""The hiring REST endpoints: what the page calls, and the two things it must never let a caller do.

A recruiter's agent can not say yes for a person (there is no field for it), and a person's own answer, given on the
hub, outranks the line in their folder and is the only thing that opens an `ask`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config, folders, hive

ROOT = Path(__file__).resolve().parents[3]
CANDIDATES = ROOT / "testdata" / "candidates"
JOB = "Senior Software Engineer\n\nRequirements:\n- 5+ years of software engineering\n- Strong Python; Kubernetes"


@pytest.fixture
def hub(client, fresh_hub, seed_vaults, monkeypatch):
    """The eight CV-based candidates on an empty hub, folders in reach, and no owner token set."""
    monkeypatch.setattr(config, "FOLDER_ROOT", CANDIDATES)
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "")
    folders.reset()
    for vault in sorted(v for v in CANDIDATES.iterdir() if v.is_dir()):
        hive.publish(seed_vaults.build_card(vault))
    yield client
    folders.reset()


def _ranking(res) -> dict[str, dict]:
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["ranking"]}


def test_a_posting_in_a_shortlist_out(hub):
    res = hub.post("/api/hr/shortlist", json={"job": JOB, "limit": 3})
    assert res.status_code == 200
    body = res.json()
    assert len(body["matches"]) == 3 and body["job"]["min_years"] == 5.0
    top = body["matches"][0]
    assert top["evidence"] and "contact" not in top and "@" not in str(body)
    assert any(r["label"] == "Python" for r in body["job"]["requirements"])


def test_the_shortlist_follows_the_posting(hub):
    software = hub.post("/api/hr/shortlist", json={"job": JOB}).json()
    marketing = hub.post("/api/hr/shortlist", json={"job": "Marketing Manager\n\n- B2B marketing; SEO"}).json()
    assert marketing["matches"][0]["id"] == "hannah-fischer"
    assert "hannah-fischer" not in {m["id"] for m in software["matches"]}


def test_bad_input_is_refused_before_any_work(hub):
    assert hub.post("/api/hr/shortlist", json={"job": ""}).status_code == 422
    assert hub.post("/api/hr/shortlist", json={"job": "x" * 7000}).status_code == 422
    assert hub.post("/api/hr/shortlist", json={"job": JOB, "limit": 99}).status_code == 422
    assert hub.post("/api/hr/shortlist", json={"job": "   "}).status_code == 400, "blank text has no posting in it"


def test_an_interview_follows_each_persons_own_answer(hub):
    by_id = _ranking(hub.post("/api/hr/interview", json={"job": JOB, "limit": 8}))
    assert by_id["elena-rostova"]["status"] == "interviewed"
    assert by_id["lena-frei"]["status"] == "awaiting_consent"
    assert by_id["oliver-grant"]["status"] == "declined"
    assert by_id["elena-rostova"]["transcript"][0]["answer"]["quotes"]


def test_the_asking_agent_can_not_say_yes_for_a_person(hub):
    res = hub.post("/api/hr/interview", json={"job": JOB, "limit": 8, "approve": ["lena-frei", "oliver-grant"]})
    by_id = _ranking(res)
    assert by_id["lena-frei"]["status"] == "awaiting_consent" and by_id["oliver-grant"]["status"] == "declined"
    assert not folders.can_read("lena-frei/cv.json", "hiring-agent")


def test_a_persons_yes_on_the_hub_opens_an_ask_and_their_no_closes_a_yes(hub):
    said = hub.post("/api/hr/screening/lena-frei", json={"screening": "yes"})
    assert said.status_code == 200 and said.json() == {"card_id": "lena-frei", "screening": "yes"}
    hub.post("/api/hr/screening/elena-rostova", json={"screening": "no"})
    by_id = _ranking(hub.post("/api/hr/interview", json={"job": JOB, "limit": 8}))
    assert by_id["lena-frei"]["status"] == "interviewed", "their answer on the hub outranks `ask` in the folder"
    assert by_id["elena-rostova"]["status"] == "declined", "and a later no outranks the yes in the folder"
    hub.post("/api/hr/screening/elena-rostova", json={"screening": "yes"})
    assert _ranking(hub.post("/api/hr/interview", json={"job": JOB, "limit": 8}))["elena-rostova"]["status"] == (
        "interviewed"
    ), "the newest answer wins"


def test_a_screening_answer_needs_the_owner_token_when_the_hub_sets_one(hub, monkeypatch):
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "s3cret")
    url, body = "/api/hr/screening/lena-frei", {"screening": "yes"}
    assert hub.post(url, json=body).status_code == 403
    assert hub.post(url, json=body, headers={"X-Owner-Token": "wrong"}).status_code == 403
    assert hub.post(url, json=body, headers={"X-Owner-Token": "s3cret"}).status_code == 200


def test_a_screening_answer_is_one_of_three_and_for_a_card_that_exists(hub):
    assert hub.post("/api/hr/screening/lena-frei", json={"screening": "maybe"}).status_code == 422
    assert hub.post("/api/hr/screening/nobody-here", json={"screening": "yes"}).status_code == 400
