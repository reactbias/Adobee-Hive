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
    assert hive.SEMANTIC_POINTS < 10, "a literal hit is worth 10 a word; a close one has to be worth less"
    assert hive.SEMANTIC_CAP < 30, "and the ceiling stays under the one a literal match can reach"
    assert salon["score_breakdown"]["semantic"] <= hive.SEMANTIC_CAP


def test_a_side_that_already_matched_literally_is_not_scored_twice(client):
    """One side's evidence is counted once, at its strongest form, and there is a bug behind that rule.

    Two people who both literally offer a dataviz sprint should not be reordered because one of them wrote
    ", remote" after it and lost a little cosine similarity to the longer line. Paying the component on top of
    a literal hit let exactly that happen. So the semantic read of a side is skipped when the words already
    found something there, which also makes "a literal hit beats a merely similar one" true by construction.
    """
    found = hive.discover(query="haircut")
    quinn, salon = _match(found, "person-quinn"), _match(found, "service-schnittwerk")
    assert quinn["score_breakdown"]["offers_needs"] > 0
    assert quinn["score_breakdown"]["semantic"] == 0, "the word is really there; that is what it is paid for"
    assert not any("close to" in why for why in quinn["why"])
    assert quinn["score"] > salon["score"], "and really offering it still outranks being close to it"

    # His card also *says* "barber", which is close to the question, and that is not paid either: the prose is
    # read only when the market side had nothing to say, so one card never collects twice for one question.
    assert any("close to" in why for why in salon["why"]), "the salon, whose offers did not contain the word"


def test_nothing_is_ever_paid_for_a_closeness_it_does_not_explain(client):
    """The open ranking promise, as an invariant rather than a sentence: points imply a reason.

    This failed once, quietly. The reason used to be dropped when the literal reason already named the same
    words; once the prose side was read too, a card could be paid for being close and say nothing about it.
    """
    for query in ("haircut", "web developer", "hairdressing work", "a quiet room", "payments"):
        for side in ("offers", "needs", "any"):
            for match in hive.discover(query=query, looking_for=side)["matches"]:
                close = [why for why in match["why"] if "close to" in why]
                if match["score_breakdown"]["semantic"] > 0:
                    assert close, (query, side, match["id"], match["why"])
                else:
                    assert not close, (query, side, match["id"], match["why"])

    # And the side a search is on is read whole: they offer cutting, and they need a cutter.
    both = _match(hive.discover(query="hairdressing", looking_for="any"), "service-schnittwerk")
    assert both["score_breakdown"]["semantic"] > 0


def test_what_an_entity_says_about_itself_is_read_last_and_counts_least(client):
    """A description is a pitch to an agent, and worth reading — under what the entity will actually do.

    `offers` and `needs` are claims an entity can be held to and rated against, so they are read first and
    paid at twice the rate. The prose answers when they had nothing to say, which is how a hub reaches a
    Gästehaus whose rooms are listed as "Zimmer", and it is where most of the four-language corpus is found.
    """
    hive.publish(
        {
            "id": "stay-sonnenhof",
            "slug": "sonnenhof",
            "kind": "hotel",
            "name": "Gästehaus Sonnenhof (fictional)",
            "description": "Neun Zimmer in Riehen. Frühstück im Garten, solange es warm ist.",
            "offers": [{"title": "Gartenzimmer", "summary": "Zwei Personen."}],
        }
    )
    guesthouse = _match(hive.discover(query="bed and breakfast with a garden"), "stay-sonnenhof")
    assert guesthouse["score_breakdown"]["semantic"] > 0
    assert 0 < hive.SEMANTIC_TEXT_POINTS < hive.SEMANTIC_POINTS, "prose counts, and counts for less"
    assert hive.SEMANTIC_TEXT_CAP < hive.SEMANTIC_CAP
    assert any("close to" in why for why in guesthouse["why"])


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
