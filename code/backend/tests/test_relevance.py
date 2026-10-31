"""A card answers only what it covers. No forced matches: an honest "nobody offers this yet", counted as demand."""

import json
from datetime import date

import pytest

from app import config, hive, llm
from app.domains import explore

NOV = date(2026, 11, 2)

# Requests no card in the Hive covers, in four languages, with typos, places and nonsense.
UNCOVERED = [
    "I need a taxi from Basel SBB to Aesch",
    "taxi from ssb to aesch",
    "book me a taxi",
    "Ich brauche ein Taxi vom Bahnhof SBB nach Aesch",
    "Un taxi de la gare de Bâle à Aesch, s'il vous plaît",
    "Mi serve un taxi dalla stazione di Basilea ad Aesch",
    "Find me a dentist in Basel",
    "Where can I get my car repaired?",
    "Two concert tickets for Saturday",
    "asdkjh qwrtz plmok",
    "???",
    "a" * 400,
]


@pytest.mark.parametrize("question", UNCOVERED)
def test_nothing_is_forced_on_a_request_no_card_covers(client, question):
    out = explore.ask(question, today=NOV)
    assert out["replies"] == [], question
    assert out["pending"] is None
    assert out["unserved"] is True


@pytest.mark.parametrize(
    "question",
    [
        "I want a vacation somewhere warm",
        "Ich möchte Ferien irgendwo am Strand",
        "Je cherche des vacances au soleil",
        "Vorrei una vacanza al mare",
        "Plan me an adventrue under 500 CHF",  # typo
        "A holiday with wildlife",
    ],
)
def test_an_open_travel_wish_finds_the_travel_card(client, question):
    out = explore.ask(question, today=NOV)
    assert [r["card_id"] for r in out["replies"]] == ["x-bekenya"], question
    assert out["unserved"] is False


def test_a_place_name_alone_does_not_make_a_card_relevant(client):
    # Endress+Hauser's card says "near Basel" and BaselHack is in Basel; neither drives taxis.
    out = explore.ask("taxi to Basel", today=NOV)
    assert out["replies"] == []


def test_named_businesses_and_their_topics_still_match(client):
    assert explore.ask("What's on at BaselHack?", today=NOV)["replies"][0]["card_id"] == "x-baselhack"
    assert explore.ask("Can someone automate my workflow with AI?", today=NOV)["replies"][0]["card_id"] == "x-4xor"


def test_unserved_requests_reach_the_demand_map_without_the_question(client):
    before = hive.demand_map()["unserved_searches"]
    explore.ask("I need a taxi from Basel SBB to Aesch", today=NOV)
    after = hive.demand_map()
    assert after["unserved_searches"] == before + 1
    taxi = next(f for f in after["features"] if f["feature"] == "taxi")
    assert taxi["unserved"] >= 1
    assert not any("aesch" in f["feature"].lower() for f in after["features"])  # never the person's words


def test_the_model_judges_relevance_and_can_drop_a_card(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    seen = {}

    def judge(system, user, schema, **kw):
        seen["user"] = user
        return {"covering": [], "reason": "No card offers rides."}

    monkeypatch.setattr(llm, "structured", judge)
    out = explore.ask("I want a vacation somewhere warm", today=NOV, judge=True)
    assert out["replies"] == [] and out["unserved"] is True
    assert out["relevance"]["by"] == "model"
    assert "BeKenya" in seen["user"]  # the model saw the cards as data


def test_the_model_can_find_a_card_the_words_missed(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: {"covering": ["x-bekenya"], "reason": "a getaway"})
    out = explore.ask("Somewhere far away to switch off for two weeks", today=NOV, judge=True)
    assert [r["card_id"] for r in out["replies"]] == ["x-bekenya"]


def test_a_model_failure_falls_back_to_the_offline_judgement(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)

    def boom(*a, **k):
        raise llm.LLMError("timeout")

    monkeypatch.setattr(llm, "structured", boom)
    out = explore.ask("I want a vacation somewhere warm", today=NOV, judge=True)
    assert [r["card_id"] for r in out["replies"]] == ["x-bekenya"]
    assert out["relevance"]["by"] == "offline"
    assert explore.ask("taxi from ssb to aesch", today=NOV, judge=True)["replies"] == []


def test_the_model_cannot_invent_a_card(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: {"covering": ["hotel-rheinblick", "x-nope"], "reason": ""})
    out = explore.ask("taxi from ssb to aesch", today=NOV, judge=True)
    assert out["replies"] == []


def test_the_api_answers_an_uncovered_request_honestly(client):
    r = client.post("/api/ask", json={"question": "taxi from ssb to aesch"})
    assert r.status_code == 200
    body = r.json()
    assert body["replies"] == [] and body["unserved"] is True


def test_the_spoken_answer_gets_no_preference_or_approval_it_does_not_have(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    seen = {}

    def capture(system, user, schema, **kw):
        seen["system"], seen["data"] = system, json.loads(user)
        return {"answer": "BeKenya runs safaris."}

    monkeypatch.setattr(llm, "structured", capture)
    explore.phrase(explore.ask("What safaris are there?", today=NOV))
    assert "preference" not in seen["data"] and "pending" not in seen["data"]
    explore.phrase(explore.ask("Plan me an adventure", mood="stressed", today=NOV))
    assert seen["data"]["preference"]["mood"] == "stressed" and seen["data"]["pending"] is True
