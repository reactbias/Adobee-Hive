"""Discovery with the semantic component wired in: the card a substring search could not find, and why.

The failure in the open: a hairdresser whose card says *"Cut, wash and finish"* was invisible to a search for
"haircut", and a front-end person who "builds user interfaces in React" was invisible to "web developer". The
index is `offers` and `needs` across every kind, so this was every domain's bug, not hospitality's.

What these tests hold on to while fixing it: semantic similarity is one component *beside* `offers_needs` and
`text_relevance`, a literal hit still wins, every semantic hit gives a reason a person can read, and
`constraints` is still earned rather than granted.
"""

from __future__ import annotations

import time

import pytest

from app import hive, semantic

SALON = {
    "id": "service-schnittwerk",
    "slug": "schnittwerk",
    "kind": "service",
    "name": "Schnittwerk (fictional)",
    "description": "Two chairs in the Laenggasse. Walk-ins before eleven.",
    "offers": [
        {"title": "Cut, wash and finish", "summary": "About an hour.", "unit": "CHF 65"},
        {"title": "Beard trim", "summary": "CHF 25."},
    ],
    "needs": [
        {"title": "Someone to build us a booking page an agent can read."},
        {"title": "A hairdresser for Saturdays", "summary": "Two chairs, one of them free."},
    ],
}

FRONTEND = {
    "id": "person-ravi",
    "slug": "ravi",
    "kind": "person",
    "name": "Ravi O. (fictional)",
    "description": "Nine years on interfaces.",
    "offers": [{"title": "Product work", "summary": "Builds user interfaces in React."}],
}

LITERAL = {
    "id": "person-quinn",
    "slug": "quinn",
    "kind": "person",
    "name": "Quinn A. (fictional)",
    "description": "Barber, mobile.",
    "offers": [{"title": "Haircut", "summary": "At your door."}],
}

PAYMENTS = {
    "id": "person-tove",
    "slug": "tove",
    "kind": "person",
    "name": "Tove S. (fictional)",
    "description": "Backend engineer.",
    "offers": [{"title": "Payments integration review", "summary": "Three days, remote."}],
}


@pytest.fixture(scope="module", autouse=True)
def cards(client):
    for card in (SALON, FRONTEND, LITERAL, PAYMENTS):
        hive.publish(dict(card))


def _match(found, card_id):
    return next((m for m in found["matches"] if m["id"] == card_id), None)


def test_a_haircut_finds_the_card_that_says_cut_wash_and_finish(client):
    """The bug, named: no card on the hub contains the word "haircut" except the one that already matched."""
    found = hive.discover(query="haircut")
    salon = _match(found, "service-schnittwerk")
    assert salon is not None
    assert salon["score_breakdown"]["semantic"] > 0
    assert "haircut" not in repr(SALON).lower(), "sanity: a substring search genuinely cannot find this card"


def test_a_web_developer_finds_someone_who_builds_user_interfaces_in_react(client):
    """The same failure in another domain, which is the point: one index, so one fix."""
    found = hive.discover(query="web developer")
    ravi = _match(found, "person-ravi")
    assert ravi is not None and ravi["score_breakdown"]["semantic"] > 0


def test_the_semantic_component_is_beside_the_others_and_not_instead_of_them(client):
    """`offers_needs` and `text_relevance` keep doing their jobs; the new one is additive."""
    found = hive.discover(query="haircut")
    salon = _match(found, "service-schnittwerk")
    assert set(salon["score_breakdown"]) >= {"constraints", "text_relevance", "offers_needs", "semantic"}
    assert salon["score_breakdown"]["offers_needs"] == 0, "nothing in the card literally says haircut"
    assert salon["score"] == pytest.approx(round(sum(salon["score_breakdown"].values()), 1))


def test_a_literal_hit_still_beats_a_merely_similar_one(client):
    """Close is worth something. The same thing is worth more, and the ordering says so."""
    found = hive.discover(query="haircut", kind=None)
    ranked = [m["id"] for m in found["matches"]]
    assert ranked.index("person-quinn") < ranked.index("service-schnittwerk")

    quinn, salon = _match(found, "person-quinn"), _match(found, "service-schnittwerk")
    assert quinn["score_breakdown"]["offers_needs"] > 0
    assert hive.SEMANTIC_POINTS < 10, "one literal offers/needs hit is worth 10; the whole component is worth less"
    assert salon["score_breakdown"]["semantic"] <= hive.SEMANTIC_POINTS


def test_a_semantic_hit_says_why_in_words_a_person_can_read(client):
    """The open ranking promise: a number nobody can read is not a reason."""
    salon = _match(hive.discover(query="haircut"), "service-schnittwerk")
    reason = next(why for why in salon["why"] if "close to" in why)
    assert reason.startswith("offers something close to")
    assert "haircut" in reason
    assert "Cut, wash and finish" in reason


def test_the_other_side_of_the_market_explains_itself_the_same_way(client):
    """A needs search says "needs something close to", because the sides are not interchangeable."""
    found = hive.discover(query="hairdressing work", looking_for="needs")
    salon = _match(found, "service-schnittwerk")
    assert salon["score_breakdown"]["offers_needs"] == 0, "no need of theirs contains the word"
    assert salon["score_breakdown"]["semantic"] > 0
    assert any(why.startswith("needs something close to") for why in salon["why"])

    # And an offers search is not answered by what someone needs, semantically either: what they are short of
    # is a hairdresser, which is not the same as having one to give.
    offers = _match(hive.discover(query="hairdressing work"), "service-schnittwerk")
    assert offers["score_breakdown"]["semantic"] > 0, "they do cut hair, so the offers side is close too"
    assert all(not why.startswith("needs") for why in offers["why"])


def test_the_floor_keeps_the_hub_from_answering_everything_with_everything(client):
    """Without a floor every card scores a little on every query and the component stops ranking anything."""
    found = hive.discover(query="haircut")
    unrelated = _match(found, "person-tove")
    assert unrelated["score_breakdown"]["semantic"] == 0
    assert not any("close to" in why for why in unrelated["why"])
    assert semantic.SIMILARITY_FLOOR > 0


def test_a_query_nobody_is_close_to_still_matches_nobody_semantically(client):
    """The honest empty answer is a promise the hub already keeps. Similarity must not quietly break it."""
    for query in ("asdkjh qwrtz plmok", "???", "a" * 400):
        found = hive.discover(query=query)
        assert all(m["score_breakdown"]["semantic"] == 0 for m in found["matches"]), query


def test_the_constraint_weight_is_still_earned_and_not_granted(client):
    """A recent fix, and a semantic score must not become a back door to the old free baseline."""
    found = hive.discover(query="haircut")
    assert all(m["score_breakdown"]["constraints"] == 0 for m in found["matches"])


def test_similarity_does_not_make_the_search_noticeably_slower(client):
    """It replaces a substring scan, so it has to cost about what a substring scan cost.

    Measured warm, which is the state a running hub is in: the corpus is encoded once per distinct line and
    cached, so the per-query work is the query's own vector and one dot product per offer.
    """
    hive.discover(query="haircut")  # warm the vector cache, as any second search finds it

    def elapsed(**kwargs) -> float:
        start = time.perf_counter()
        for _ in range(5):
            hive.discover(**kwargs)
        return time.perf_counter() - start

    with_semantics = elapsed(query="a haircut and a web developer")
    literal_only = elapsed(query="a haircut and a web developer", semantic_search=False)
    assert with_semantics < max(literal_only * 2.0, 0.5), (with_semantics, literal_only)


def test_the_semantic_component_can_be_turned_off_at_the_call(client):
    """Federation and the eval harness both need the literal baseline, and so does anyone comparing the two."""
    off = _match(hive.discover(query="haircut", semantic_search=False), "service-schnittwerk")
    assert off is None or off["score_breakdown"]["semantic"] == 0


def test_health_says_which_provider_discovery_is_ranking_with(client):
    """The page shows "AI live" or "Offline mode" from /api/health, so the field has to be the truth.

    And it is the one field about a provider that a public endpoint may carry: which one is in use, never
    anything about the credential behind it.
    """
    body = client.get("/api/health").json()
    assert body["semantic"] == semantic.OFFLINE, "the demo runs with no key, and says so"
    assert not any("key" in str(key).lower() for key in body), body
