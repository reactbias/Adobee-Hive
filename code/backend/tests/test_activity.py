"""The live activity feed: one line per agent step, from the Hive's own cards to the web scout, never a person."""

import pytest

from app import activity, db, hive_seed
from tests.test_hive import REQUEST
from tests.test_scout import web  # noqa: F401  (the fake public web fixture)


def _since(client, after: int = 0) -> list[dict]:
    return client.get("/api/activity", params={"after": after}).json()["events"]


def _last(client) -> int:
    return client.get("/api/activity").json()["last"]


def test_a_booking_shows_every_step_from_discovery_to_receipt(client):
    start = _last(client)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    lines = _since(client, start)
    assert [e["step"] for e in lines] == ["discover", "verify", "availability", "hold", "review", "review"]
    assert lines[0]["agent"] == "traveller" and lines[0]["source"] == "partner" and lines[0]["count"] >= 1
    assert lines[1]["outcome"] == "valid" and lines[1]["business"] == "Hotel Rheinblick"
    assert lines[3]["outcome"] == "held"
    assert {e["agent"] for e in lines[4:]} == {"verifier", "critic"}
    assert len({e["run"] for e in lines}) == 1  # one run, one group

    mid = _last(client)
    client.post("/api/agent/approve", json={"pending": out["pending"]})
    (confirm,) = _since(client, mid)
    assert (confirm["step"], confirm["outcome"], confirm["business"]) == ("confirm", "confirmed", "Hotel Rheinblick")


def test_no_line_ever_carries_the_guest_or_their_words(client):
    start = _last(client)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    client.post("/api/agent/approve", json={"pending": out["pending"]})
    client.post("/api/ask", json={"question": "Book me a safari with BeKenya"})
    feed = str(_since(client, start))
    assert "Mara" not in feed and "Keller" not in feed and "safari" not in feed.lower()


def test_a_request_without_dates_shows_the_question_back(client):
    start = _last(client)
    client.post("/api/agent", json={"messages": [{"role": "user", "content": "Book me a hotel in Basel"}]})
    assert [(e["step"], e["outcome"]) for e in _since(client, start)] == [("clarify", "asked")]


def test_any_business_answers_from_cards_and_says_when_it_can_only_hand_off(client):
    start = _last(client)
    out = client.post("/api/ask", json={"question": "Book me a safari with BeKenya"}).json()
    lines = _since(client, start)
    assert lines[0]["step"] == "relevance" and lines[0]["outcome"] == "covered" and lines[0]["count"] >= 1
    answers = [e for e in lines if e["step"] == "discover"]
    assert answers and answers[0]["business"] == "BeKenya" and answers[0]["source"] == "web"  # unclaimed card
    (hold,) = [e for e in lines if e["step"] == "hold"]
    assert hold["outcome"] == "handoff_only"  # an unclaimed card cannot be booked automatically

    mid = _last(client)
    client.post("/api/ask/approve", json={"id": out["pending"]["id"]})
    (handoff,) = _since(client, mid)
    assert (handoff["step"], handoff["outcome"], handoff["business"]) == ("handoff", "handed_off", "BeKenya")


def test_nothing_in_the_hive_hands_over_to_the_scout(client, web):  # noqa: F811
    start = _last(client)
    client.post("/api/ask", json={"question": "I need a taxi from Basel SBB to Aesch at 17:00"})
    assert ("relevance", "none") in [(e["step"], e["outcome"]) for e in _since(client, start)]

    mid = _last(client)
    client.post("/api/ask/scout", json={"question": "I need a taxi from Basel SBB to Aesch at 17:00"})
    lines = _since(client, mid)
    assert lines[0]["agent"] == "scout" and lines[0]["step"] == "scout" and lines[0]["outcome"] == "found"
    verified = [e for e in lines if e["step"] == "verify"]
    assert verified[0]["outcome"] == "added" and verified[0]["business"] == "Taxi Muster Aesch"
    assert verified[0]["source"] == "web"


def test_the_feed_is_capped_and_newest_last(client, monkeypatch):
    monkeypatch.setattr(activity, "MAX_EVENTS", 5)
    for i in range(8):
        activity.record([activity.event("traveller", "discover", outcome="none", count=i)])
    feed = client.get("/api/activity").json()["events"]
    assert len(feed) == 5 and [e["count"] for e in feed] == [3, 4, 5, 6, 7]


def test_only_known_steps_and_short_names_are_stored(client):
    with pytest.raises(ValueError):
        activity.event("traveller", "whatever")
    with pytest.raises(ValueError):
        activity.event("someone", "discover")
    line = activity.event("hive", "discover", business="x" * 500, outcome="matched")
    assert len(line["business"]) <= activity.MAX_NAME


def test_the_feed_is_kept_in_the_database_and_cleared_by_a_reset(client):
    activity.record([activity.event("hive", "discover", outcome="none")])
    with db.cursor() as cur:
        assert cur.execute("SELECT count(*) FROM hive_activity").fetchone()[0] >= 1
    assert "hive_activity" in hive_seed.TABLES


def test_the_feed_answers_with_a_bounded_page(client):
    assert client.get("/api/activity", params={"limit": 0}).status_code == 422
    assert client.get("/api/activity", params={"limit": 1000}).status_code == 422
