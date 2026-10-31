"""Ask the Hive: answers from the example cards, a mood the person chose, and a yes before any hand-off."""

import asyncio
import json
from datetime import date

from mcp import Client

from app import hive, owner
from app.domains import examples, explore
from app.mcp_server import server

NOV = date(2026, 11, 2)


def _titles(result):
    return [i["title"] for r in result["replies"] for i in r["items"]]


def test_example_cards_are_unclaimed_and_say_where_they_come_from(client):
    for spec in examples.CARDS:
        card = hive.get_card(spec["id"])
        assert card["trust"]["signature_valid"]
        assert card["trust"]["claimed"] is False
        assert card["trust"]["provenance"]["source"] == "public website"
        assert card["trust"]["provenance"]["url"].startswith("https://")
    assert hive.get_card("hotel-rheinblick")["trust"]["claimed"] is True


def test_discovery_lists_an_unclaimed_example_card_and_marks_it_unclaimed(client):
    """Decided: unclaimed example cards are *in* discovery, and every result says it is unclaimed.

    The old rule kept them out, because discovery was a room search and a card the business never
    published had no business being ranked beside one it did. `offers` and `needs` are the index
    now, and these cards hold the only real non-stay offers on the hub: a hub that cannot answer
    "who runs a Modbus course" while holding the answer is not a directory, it is a room search
    with a directory's name. Hiding them also hid them from the *reason* machinery — an agent that
    cannot see a lead cannot be told it is only a lead.

    So the constraint is carried by marking, not by hiding, and this test pins the marking: the
    result says `claimed` false and `bookable` false, the "why" says where it came from, nothing
    unclaimed has units to book, and the hand-off still waits for a human yes and sends the
    business nothing (test_transactions_wait_for_a_yes_and_hand_off_once, owner.apply, SECURITY.md).
    """
    found = hive.discover(query="flow measurement and calibration")
    endress = next(m for m in found["matches"] if m["id"] == "x-endress")
    assert endress["claimed"] is False and endress["bookable"] is False
    assert any("unclaimed" in why for why in endress["why"]), "no caller can mistake it for a presence"
    assert any("offers" in why for why in endress["why"]), "and it is here because of what it offers"

    for spec in examples.CARDS:
        result = next(
            (m for m in hive.discover(kind=spec["kind"])["matches"] if m["id"] == spec["id"]),
            None,
        )
        assert result is not None, f"{spec['id']} is findable"
        assert result["claimed"] is False and result["bookable"] is False, spec["id"]
        assert hive.get_card(spec["id"])["units"] == [], "nothing unclaimed can be booked"

    # A claimed business is not marked down by the same fields: the flag means unclaimed, not "new".
    rheinblick = next(m for m in hive.discover(kind="hotel")["matches"] if m["id"] == "hotel-rheinblick")
    assert rheinblick["claimed"] is True and rheinblick["bookable"] is True


def test_owner_cannot_edit_an_unclaimed_card(client):
    r = client.post("/api/owner/x-endress/propose", json={"instruction": "add free coffee"})
    assert r.status_code == 400 and "unclaimed" in r.json()["detail"]
    try:
        owner.apply("x-endress", hive.get_card("x-endress"))
    except hive.HiveError:
        pass
    else:
        raise AssertionError("apply must refuse an unclaimed card")


def test_whats_going_on_at_endress_this_month(client):
    out = explore.ask("What's going on at Endress this month?", today=NOV)
    assert {r["card_id"] for r in out["replies"]} == {"x-endress"}
    first = out["replies"][0]
    assert first["claimed"] is False and first["source"]["verified_by_owner"] is False
    assert first["items"][0]["title"] == "Certified Basic Modbus Technology course"
    assert "this month" in first["items"][0]["why"]
    assert out["pending"] is None  # a question, not a transaction


def test_adventure_under_budget_explains_what_was_left_out(client):
    out = explore.ask("Plan me an adventure under 500 CHF", today=NOV)
    assert {r["card_id"] for r in out["replies"]} == {"x-bekenya"}
    assert "21 days Kenya: safari, culture and coast" not in _titles(out)
    (left_out,) = [e for e in out["excluded"] if e["item"].startswith("21 days")]
    assert "over your budget of CHF 500" in left_out["why_not"][0]
    assert out["rate"]["note"] == "fixed demo rate, not live"
    assert all("no published price, ask for a quote" in i["why"] for r in out["replies"] for i in r["items"])


def test_mood_is_visible_and_changes_what_comes_first(client):
    calm = explore.ask("Plan me an adventure", mood="stressed", today=NOV)
    party = explore.ask("Plan me an adventure", mood="celebrating", today=NOV)
    assert calm["preference"] == {
        "mood": "stressed",
        "effects": ["calm_first", "fewer_options", "no_long_commitments"],
        "source": "chosen by you",
    }
    assert len(_titles(calm)) <= 2
    assert "Mount Kenya trek" not in _titles(calm)  # long commitments set aside, and said so
    assert any(e["item"] == "Mount Kenya trek" for e in calm["excluded"])
    assert _titles(calm)[0] != _titles(party)[0]
    assert explore.ask("Plan me an adventure", today=NOV)["preference"]["mood"] is None  # never inferred


def test_transactions_wait_for_a_yes_and_hand_off_once(client):
    out = client.post("/api/ask", json={"question": "Book me a safari with BeKenya"}).json()
    pending = out["pending"]
    assert pending["business"] == "BeKenya" and pending["claimed"] is False and pending["url"] == "https://bekenya.com"
    done = client.post("/api/ask/approve", json={"id": pending["id"]}).json()
    assert done["status"] == "handed_off" and done["sent_to_business"] is False
    assert client.post("/api/ask/approve", json={"id": pending["id"]}).status_code == 400  # once


def test_ask_validates_input(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "hi", "mood": "angry"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422


def test_card_text_cannot_steer_the_answer(client):
    # The model only phrases a result; its prompt says card text is data. Offline, nothing is phrased at all.
    out = explore.ask("adobe content credentials", today=NOV)
    assert out["answer"] is None and out["mode"] == "offline"
    assert "card_text_is_data" in out["rules"]
    assert "Content Credentials" in _titles(out)


def test_explore_ask_over_mcp_never_returns_a_hold_id(client):
    async def run():
        async with Client(server) as c:
            res = await c.call_tool("explore_ask", {"question": "Register me for a course at Endress"})
            return json.loads(res.content[0].text)

    out = asyncio.run(run())
    assert out["pending"]["needs"] == "the person's approval in the Hive app" and "id" not in out["pending"]


def test_an_open_question_is_answered_by_mood_alone(client):
    out = explore.ask("What should I do this weekend?", mood="curious", today=NOV)
    assert len(_titles(out)) >= 3
    assert all(any(w.startswith("fits your mood") for w in i["why"]) for r in out["replies"] for i in r["items"])


def test_the_example_questions_work_in_four_languages(client):
    for q in (
        "Was läuft diesen Monat bei Endress+Hauser?",
        "Quoi de neuf chez Endress+Hauser ce mois-ci ?",
        "Che novità ci sono da Endress+Hauser questo mese?",
    ):
        assert _titles(explore.ask(q, today=NOV))[0] == "Certified Basic Modbus Technology course", q
    for q in (
        "Planen Sie mir ein Abenteuer unter 500 CHF",
        "Planifiez-moi une aventure à moins de 500 CHF",
        "Pianifichi per me un'avventura sotto 500 CHF",
    ):
        out = explore.ask(q, today=NOV)
        assert out["budget_chf"] == 500 and out["pending"] and out["replies"][0]["card_id"] == "x-bekenya", q


def test_no_mood_is_not_described_as_one(client, monkeypatch):
    seen = {}

    def fake(system, user, schema, **kw):
        seen["data"] = json.loads(user)
        return {"answer": "ok"}

    monkeypatch.setattr(explore.config, "LLM_ENABLED", True)
    monkeypatch.setattr(explore.llm, "structured", fake)
    explore.phrase(explore.ask("What's going on at BaselHack this month?"))
    assert "preference" not in seen["data"]
