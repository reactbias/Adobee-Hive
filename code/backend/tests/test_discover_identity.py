"""The requester's own name is not a thing to rank on, and a stated constraint is (#95).

A hotel booking for "Mara Keller" once ranked a hand-off-only Kenya safari first, because the guest's own
first name matched BeKenya's *Maasai Mara* offer and the offers side pays more than prose does. Meanwhile
the hotel that actually fitted — quiet, dog-friendly, a late check-in kiosk, CHF 128, 1.9 km from Basel SBB
— scored 0 for both `constraints` and `proximity`, because nothing had parsed the sentence into the
structured ask that `hive.fit` can check.

Both halves are handled in `main.py`'s `_discovery_stay`: it parses a stay request into features, landmark,
budget and dates, and strips the declared identity before the text is ranked. These tests pin the outcome
rather than the parser, so the invariant survives a rewrite of how it is done:

- varying only the guest's name must not change which hotels are eligible or the order they come in;
- the stated constraints must actually earn `constraints` and `proximity` points;
- an unclaimed, unbookable lead must not come first for a booking request.

`tests/test_hive.py` owns the end-to-end booking; this file owns the ranking.
"""

from __future__ import annotations

import pytest

ASK = "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in."

#: The same request, signed with different fictional names — including one whose first name is a word in
#: another card's offers ("Mara" is in BeKenya's Maasai Mara), which is the bug this file exists for.
NAMES = ["Mara Keller", "Ruedi Brun", "Chiara Rossi", "Jean Dupont", "Anna Müller", "Basel Hotelier"]


def _discover(client, query: str) -> dict:
    """What the REST door returns for a free-text query, which is the path a real caller takes.

    Through the API rather than `hive.discover` on purpose: identity stripping and constraint parsing live
    in the endpoint, so calling the core directly would test a different thing from the one that broke.
    """
    found = client.get("/api/hive/discover", params={"query": query})
    assert found.status_code == 200, found.text
    return found.json()


def _scoring(found: dict) -> list[str]:
    """The ids that actually scored, best first."""
    return [m["id"] for m in found["matches"] if m["score"] > 0]


@pytest.mark.parametrize("name", NAMES)
def test_the_guests_name_changes_nothing_about_the_ranking(client, name):
    """Who is asking is not evidence about who should answer.

    The whole request is held still and only the fictional name varies, so a difference in the result can
    only have come from the name. "Mara" is the case that was really broken; the others are there so the
    test cannot pass by special-casing one string.
    """
    baseline = _scoring(_discover(client, ASK))
    assert baseline, "the ask must match somebody, or this test proves nothing"
    assert _scoring(_discover(client, f"{ASK} My name is {name}.")) == baseline


def test_a_name_that_is_also_a_word_in_someone_elses_offer_earns_them_nothing(client):
    """The named bug: a guest called Mara must not promote the Maasai Mara safari.

    Checked by score rather than by position, because "not first" would still pass if the safari had merely
    slipped to second while being paid for the guest's name.
    """
    with_name = _discover(client, f"{ASK} My name is Mara Keller.")
    for match in with_name["matches"] + with_name["excluded"]:
        if "kenya" in match["id"].lower():
            offers = match["score_breakdown"]["offers_needs"]
            assert offers == 0, (match["id"], match["why"])


def test_a_booking_request_is_not_answered_first_by_an_unclaimed_lead(client):
    """An unclaimed card was compiled from public information and cannot be booked, so it is not the answer.

    It may still be found — a lead is real information — but a request to book ranks something bookable
    first, or the agent's next step is a hand-off the user never asked for.
    """
    top = _discover(client, f"{ASK} My name is Mara Keller.")["matches"]
    assert top, "the ask must match somebody"
    assert top[0]["claimed"], top[0]["id"]
    assert top[0]["bookable"], top[0]["id"]


def test_the_constraints_in_the_sentence_are_actually_scored(client):
    """ "Quiet, dog-friendly, near Basel SBB, under CHF 200" is four checkable claims, and they must pay.

    This is the other half of #95: the hotel that fitted scored 0 for `constraints` and 0 for `proximity`,
    which means the sentence had been read as prose and never turned into an ask. A constraint score is
    earned, so the test asserts it was earned and not merely that the right hotel won.
    """
    top = _discover(client, ASK)["matches"][0]
    assert top["score_breakdown"]["constraints"] > 0, top
    assert top["score_breakdown"]["proximity"] > 0, top
    assert top["distance_m"] is not None
    # And the reasons say so in words, because an unexplained score is not an open ranking.
    assert any("dog-friendly" in why for why in top["why"]), top["why"]
    assert any("basel sbb" in why.lower() for why in top["why"]), top["why"]


def test_a_hotel_that_misses_a_stated_constraint_is_excluded_and_says_why(client):
    """Whoever does not meet the ask is a near-miss with a reason, not a low-scoring match."""
    found = _discover(client, ASK)
    excluded = {e["id"]: e["why_not"] for e in found["excluded"]}
    assert excluded, "something in this corpus must fail this ask"
    assert all(why for why in excluded.values())
    assert set(excluded) & {m["id"] for m in found["matches"]} == set()


@pytest.mark.parametrize(
    "ask",
    [
        "Ein ruhiges, hundefreundliches Hotel beim Bahnhof Basel SBB unter CHF 200. Mein Name ist Mara Keller.",
        "Un hôtel calme près de Basel SBB, moins de CHF 200. Je m'appelle Mara Keller.",
        "Un hotel tranquillo vicino a Basel SBB, sotto CHF 200. Mi chiamo Mara Keller.",
    ],
)
def test_a_request_in_another_language_is_answered_and_not_ranked_on_the_name(client, ask):
    """The corpus is four languages, so the identity rule cannot be an English-only rule.

    Weaker than the English assertions on purpose: what is pinned is that the request is understood well
    enough to return somebody, and that the guest's name earns nobody anything.
    """
    found = _discover(client, ask)
    assert _scoring(found), ask
    for match in found["matches"] + found["excluded"]:
        if "kenya" in match["id"].lower():
            assert match["score_breakdown"]["offers_needs"] == 0, match["why"]
