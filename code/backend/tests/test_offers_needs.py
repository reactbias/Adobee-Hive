"""The index is what an entity offers and what it needs; `kind` only narrows it.

A hub carries hotels, developers, hairdressers and cafés side by side. These tests describe the
two sides of that market: `looking_for="offers"` finds whoever provides the thing, `"needs"`
whoever wants what you provide. Every card here is fictional.
"""

import pytest

from app import hive

DEV = {
    "id": "person-nadia",
    "slug": "nadia",
    "kind": "person",
    "name": "Nadia B. (fictional)",
    "description": "Builds things for people who measure things.",
    # Two shapes on purpose: an offer may be a plain line or an object, and the shape an owner
    # happened to write must not decide whether they are findable.
    "offers": [
        "Two-week dataviz sprint, remote",
        {"title": "Firmware review", "skills": ["rust", "embedded"], "summary": "A week on your bootloader."},
    ],
    "needs": [{"title": "A technical writer for the handbook"}],
}

NETZ = {
    "id": "company-netz",
    "slug": "netz",
    "kind": "company",
    "name": "Netzwerk Nord (fictional)",
    "description": "Small workshop, two machines, no website.",
    "needs": [{"title": "A CNC lathe operator for night shifts", "tags": ["shift work"]}],
}

OFFERS_SVELTE = {
    "id": "person-pia",
    "slug": "pia",
    "kind": "person",
    "name": "Pia L. (fictional)",
    "description": "Interface work, nine years.",
    "offers": [{"title": "Svelte contracting", "summary": "Day rate, remote, from January."}],
}

MENTIONS_SVELTE = {
    "id": "person-tom",
    "slug": "tom",
    "kind": "person",
    "name": "Tom R. (fictional)",
    "description": "Backend engineer. I have read about Svelte and left it at that.",
    "offers": [{"title": "Postgres tuning"}],
}


@pytest.fixture(scope="module", autouse=True)
def cards(client):
    for card in (DEV, NETZ, OFFERS_SVELTE, MENTIONS_SVELTE):
        hive.publish(dict(card))


def _match(found, card_id):
    return next((m for m in found["matches"] if m["id"] == card_id), None)


def test_a_developer_is_found_by_a_skill_in_her_offers(client):
    """The failure that started this: a developer on the hub nobody could find."""
    for query in ("dataviz sprint", "firmware review", "someone who knows rust"):
        found = _match(hive.discover(query=query), "person-nadia")
        assert found is not None, query
        assert found["score_breakdown"]["offers_needs"] > 0, query
        assert any(why.startswith("offers ") for why in found["why"]), query


def test_an_entity_is_found_by_what_it_needs(client):
    """The other side of the market: a workshop that needs an operator is findable by the operator."""
    found = _match(hive.discover(query="lathe operator", looking_for="needs"), "company-netz")
    assert found is not None
    assert found["score_breakdown"]["offers_needs"] > 0
    assert any(why.startswith("needs ") for why in found["why"])


def test_an_offers_search_does_not_match_on_what_someone_needs(client):
    """Otherwise every search finds its own mirror image: people who want the thing, not have it."""
    offers = _match(hive.discover(query="lathe operator"), "company-netz")
    assert offers["score_breakdown"]["offers_needs"] == 0, "'lathe' is only in its needs"
    assert not any(why.startswith("needs ") for why in offers["why"])

    needs = _match(hive.discover(query="lathe operator", looking_for="needs"), "company-netz")
    assert needs["score"] > offers["score"]
    both = _match(hive.discover(query="lathe operator", looking_for="any"), "company-netz")
    assert both["score_breakdown"]["offers_needs"] > 0

    # And a side nobody asked for is not scored either: Nadia needs a writer, she does not offer one.
    assert _match(hive.discover(query="technical writer"), "person-nadia")["score_breakdown"]["offers_needs"] == 0


def test_kind_still_narrows_a_search(client):
    """`kind` stopped being a gate the hub applies; it is still a filter the caller may apply."""
    wide = {m["id"] for m in hive.discover(query="lathe operator", looking_for="needs")["matches"]}
    assert {"company-netz", "person-nadia"} <= wide

    narrow = hive.discover(query="lathe operator", looking_for="needs", kind="person")
    assert "company-netz" not in {m["id"] for m in narrow["matches"] + narrow["excluded"]}
    assert {m["kind"] for m in narrow["matches"]} == {"person"}


def test_offering_the_thing_beats_mentioning_it(client):
    """An entity that literally offers it outranks one whose prose happens to contain the word."""
    found = hive.discover(query="svelte", kind="person")
    ranked = [m["id"] for m in found["matches"]]
    assert ranked.index("person-pia") < ranked.index("person-tom")

    pia, tom = _match(found, "person-pia"), _match(found, "person-tom")
    assert pia["score_breakdown"]["offers_needs"] > tom["score_breakdown"]["text_relevance"]
    assert tom["score_breakdown"]["offers_needs"] == 0 and tom["score_breakdown"]["text_relevance"] > 0


def test_an_unknown_side_of_the_market_is_refused_not_guessed(client):
    """A typo must not quietly become the default, or a needs search silently answers with offers."""
    with pytest.raises(hive.HiveError, match="looking_for"):
        hive.discover(query="lathe", looking_for="need")
    assert client.get("/api/hive/discover", params={"query": "lathe", "looking_for": "need"}).status_code == 400


def test_both_sides_are_reachable_over_the_rest_api(client):
    """The parameter is no use if only the Python caller has it."""
    needs = client.get("/api/hive/discover", params={"query": "lathe operator", "looking_for": "needs"}).json()
    found = next(m for m in needs["matches"] if m["id"] == "company-netz")
    assert found["score_breakdown"]["offers_needs"] > 0
    assert "offers" in needs["ranking_policy"] and "needs" in needs["ranking_policy"]


def test_the_constraint_score_is_earned_and_not_granted(client):
    """An ask with nothing to verify pays nobody: a free 50 for passing an empty check outranked
    every relevance signal there is, which is how a query for "dataviz" answered with hotels.
    """
    empty = hive.discover(query="dataviz sprint")
    assert all(m["score_breakdown"]["constraints"] == 0 for m in empty["matches"])
    assert empty["matches"][0]["id"] == "person-nadia", [(m["id"], m["score"]) for m in empty["matches"][:3]]

    # A real constraint, tested and met, is still worth the full weight.
    asked = hive.discover(features=["dog-friendly"], check_in="2026-12-01", check_out="2026-12-03")
    rheinblick = _match(asked, "hotel-rheinblick")
    assert rheinblick["score_breakdown"]["constraints"] == hive.CONSTRAINT_POINTS
    assert hive.fit(hive.get_card("hotel-rheinblick"), ["dog-friendly"], check_in="2026-12-01", check_out="2026-12-03")[
        "checked"
    ] == ["dog-friendly", "dates"]


def test_a_budget_nobody_published_a_price_for_is_not_a_constraint_met(client):
    """It is not cheap, it is unknown: an entity with no price neither fails a budget nor earns it."""
    card = hive.get_card("person-nadia")
    found = hive.fit(card, [], max_price_chf=50)
    assert found["checked"] == [] and found["misses"] == []

    priced = hive.fit(hive.get_card("hotel-rheinblick"), [], max_price_chf=1000)
    assert priced["checked"] == ["budget"] and priced["met"] == ["budget"]
    assert hive.fit(hive.get_card("hotel-rheinblick"), [], max_price_chf=10)["met"] == []

    # So a priced stay that meets the budget outranks a card the budget could not be checked against.
    ranked = [m["id"] for m in hive.discover(query="design", max_price_chf=1000)["matches"]]
    assert ranked.index("hotel-rheinblick") < ranked.index("person-nadia")
