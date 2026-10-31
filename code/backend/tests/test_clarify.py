"""When a request lacks what the agents need, they ask one short question, then carry on in the same conversation."""

import asyncio

import pytest

from app import agent
from app.domains import explore


def _run(*user_turns, locale="en"):
    messages = []
    for i, text in enumerate(user_turns):
        messages.append({"role": "user", "content": text})
        if i < len(user_turns) - 1:
            messages.append({"role": "assistant", "content": "(reply)"})
    return asyncio.run(agent.run(messages, locale=locale))


@pytest.mark.parametrize(
    ("text", "needs"),
    [
        ("Book me a hotel in Basel", ["dates", "name"]),
        ("Book me a quiet room near Basel SBB, 2026-11-13 to 2026-11-15", ["name"]),
        ("Book me a room, my name is Mara Keller", ["dates"]),
    ],
)
def test_a_booking_without_dates_or_a_name_asks_first(client, text, needs):
    out = _run(text)
    assert out["needs"] == needs
    assert out["pending"] is None
    assert not any(s["tool"] == "hive_book" for s in out["steps"])
    assert out["reply"].endswith("?")


def test_the_answer_continues_the_same_booking(client):
    out = _run("Book me a quiet room near Basel SBB", "2026-11-13 to 2026-11-15, my name is Mara Keller")
    assert not out.get("needs")
    held = out["pending"]["input"]
    assert (held["check_in"], held["check_out"], held["guest_name"]) == ("2026-11-13", "2026-11-15", "Mara Keller")


def test_just_looking_needs_no_questions(client):
    assert not _run("Find me a dog-friendly hotel near Basel SBB").get("needs")


@pytest.mark.parametrize("locale", ["en", "de", "fr", "it"])
def test_the_question_is_in_the_app_language(client, locale):
    reply = _run("Book me a hotel in Basel", locale=locale)["reply"]
    others = {loc: _run("Book me a hotel in Basel", locale=loc)["reply"] for loc in ("en", "de", "fr", "it")}
    assert sum(r == reply for r in others.values()) == 1  # each language has its own question


@pytest.mark.parametrize(
    ("question", "clarify"),
    [
        ("book me a taxi", ["route", "time"]),
        ("Ich brauche ein Taxi", ["route", "time"]),
        ("un taxi demain à 8h", ["route"]),
        ("taxi from Basel SBB to Aesch", ["time"]),
    ],
)
def test_a_ride_without_route_or_time_asks_first(client, question, clarify):
    out = explore.ask(question)
    assert out["clarify"] == clarify
    assert out["replies"] == [] and out["unserved"] is False  # not counted as demand until it is complete


def test_a_complete_ride_request_asks_nothing(client):
    out = explore.ask("book me a taxi from Basel SBB to Aesch at 17:00")
    assert out["clarify"] == [] and out["unserved"] is True


def test_places_alone_are_not_an_open_question(client):
    out = explore.ask("from Basel SBB to Aesch at 17:00")
    assert out["replies"] == [] and out["unserved"] is True
