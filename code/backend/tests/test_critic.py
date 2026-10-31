"""The critic always argues for the strongest alternative, and concedes only when the pick wins on the facts."""

from app import critic, replies


def _discover(*matches, excluded=()):
    """A hive_discover step as the booking agent saw it."""
    return {"tool": "hive_discover", "input": {}, "output": {"matches": list(matches), "excluded": list(excluded)}}


def _match(card_id, name, score, price, why=()):
    return {"id": card_id, "name": name, "score": score, "from_price_chf": price, "why": list(why)}


PICK = _match("hotel-rheinblick", "Hotel Rheinblick", 82, 180, ["has quiet, dog-friendly"])
BOOKING = {"card_id": "hotel-rheinblick", "unit_id": "river"}


def test_it_challenges_a_cheaper_rival_and_concedes_when_the_pick_ranks_higher():
    rival = _match("hotel-gare", "Gare Central", 61, 140)
    out = critic.challenge([_discover(PICK, rival)], BOOKING, "en")
    assert out["verdict"] == "agree"
    assert out["rival"] == "Gare Central"
    assert out["challenge"] == replies.say(
        "en", "critic.cheaper", rival="Gare Central", diff=40, name="Hotel Rheinblick"
    )
    assert "82" in out["answer"] and "61" in out["answer"]


def test_it_holds_its_concern_when_the_rival_ranks_at_least_as_high():
    rival = _match("hotel-gare", "Gare Central", 90, 140)
    out = critic.challenge([_discover(PICK, rival)], BOOKING, "en")
    assert out["verdict"] == "concern"
    assert out["note"] == replies.say("en", "critic.hold", rival="Gare Central")


def test_alone_at_the_top_it_asks_whether_the_search_was_too_narrow():
    out = critic.challenge([_discover(PICK, excluded=[{"id": "a"}, {"id": "b"}])], BOOKING, "de")
    assert out["verdict"] == "agree"
    assert out["challenge"] == replies.say("de", "critic.alone", name="Hotel Rheinblick")
    assert out["answer"] == replies.say("de", "critic.alone.answer", n=2)


def test_a_pick_the_hive_never_ranked_is_a_concern():
    out = critic.challenge([_discover(_match("x", "Other", 50, 100))], BOOKING, "fr")
    assert out["verdict"] == "concern"
    assert out["note"] == replies.say("fr", "critic.unranked")
