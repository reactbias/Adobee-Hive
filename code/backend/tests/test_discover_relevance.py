"""A hub that cannot say "nothing matched" is not answering, it is guessing (#152, #154).

Every query returned the whole hub. A nonsense query, an empty query and a real one all came back with
`matches: 73, excluded: 0`, the first four rows four Basel hotels on `score: 1-2` with an empty `why`, and
no field anywhere saying that nothing had matched. The advice in the docs — *threshold on `score > 0`
yourself* — does not work, and those four hotels are exactly why: `reputation.business_points` pays an
entity for verified reviews and attestations whatever the question was, so its total is never zero.

So the test of whether a query was answered is `hive.relevance`, the five components the *ask* earned, and
the doors apply it: `GET /api/hive/discover` and `hive_discover` over MCP. `hive.discover` itself still
returns the whole ranked list — the answer key reads it, and a core that quietly returned less than it
found would make every measurement over it a different measurement.

The response-size half of #154 is `limits.bound_answer`, which was already there. What these tests pin is
that the two compose in the right order: threshold first, so the ceiling spends its slots on matches.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp import Client

from app import hive
from app.mcp_server import server

#: Queries no card on this hub answers. The first is the user test's own nonsense string.
NOTHING = ["asdfghjkl qwertz", "zzzz qqqq wwww", "scientific computing numerical simulation freelancer"]


def _mcp(tool: str, args: dict) -> dict:
    """Call an MCP tool the way a client does, and read the structured answer."""

    async def go():
        async with Client(server) as c:
            return (await c.call_tool(tool, args)).structured_content

    return asyncio.run(go())


def _discover(client, **params):
    """What the REST door returns, which is where the threshold lives."""
    found = client.get("/api/hive/discover", params=params)
    assert found.status_code == 200, found.text
    return found.json()


def test_a_nonsense_query_says_nothing_matched(client):
    """`matched: 0` and an empty `matches`, rather than the whole hub ranked by reputation.

    The complaint this closes: "a nonsense query looks like it has results". It did — 73 of them.
    """
    for query in NOTHING:
        found = _discover(client, query=query)
        assert found["matches"] == [], (query, [m["id"] for m in found["matches"][:5]])
        assert found["matched"] == 0, query
        # And the hub still says how many it looked at, so the zero has a denominator.
        assert found["considered"] > 0, query


def test_no_result_is_ever_returned_without_a_reason_for_being_there(client):
    """An empty `why` beside a nonzero score is unexplainable, so it is not a result.

    Open ranking is the claim; a row a caller cannot account for is the one place it leaked. Every match
    the door returns now carries at least one reason.
    """
    for query in ("quiet dog-friendly hotel", "haircut", "web developer", *NOTHING):
        for match in _discover(client, query=query)["matches"]:
            assert match["why"], (query, match["id"], match["score_breakdown"])
            assert hive.relevance(match) > 0, (query, match["id"])


def test_the_reputation_only_hotels_are_the_reason_score_is_not_the_test(client):
    """The rows that made "threshold on score > 0" useless, pinned so the regression is visible.

    Not a hypothetical: these four come back for every query there is, nonsense included, because
    attestations and verified reviews are paid whatever was asked. The core still ranks them — that is
    not a bug, reputation is real — and the door still leaves them out of an answer they did not earn.
    """
    raw = hive.discover(query="asdfghjkl qwertz")
    assert len(raw["matches"]) > 10, "the core still answers with the whole ranked hub"
    paid = [m for m in raw["matches"] if m["score"] > 0]
    assert paid, "if no entity scores on nonsense any more, this test has stopped testing anything"
    for match in paid:
        assert hive.relevance(match) == 0, match["id"]
        assert match["why"] == [] or not any(
            why.startswith(("offers", "needs", "mentions", "has")) for why in match["why"]
        ), match["why"]


def test_an_empty_ask_is_a_browse_and_still_returns_everyone(client):
    """A question with nothing in it is answered by everything, because that is the honest answer.

    The threshold would otherwise turn "show me what is on this hub" into "nobody is", which is worse
    than the bug it fixes. `hive.asks_anything` is the distinction.
    """
    browse = _discover(client)
    assert browse["matched"] == browse["considered"] > 0
    assert len(browse["matches"]) == browse["considered"]
    assert not hive.asks_anything("")
    assert not hive.asks_anything("   ")
    assert hive.asks_anything("hotel")
    assert hive.asks_anything("", features=["quiet"])
    assert hive.asks_anything("", near="basel sbb")
    assert hive.asks_anything("", max_price_chf=200)


def test_a_caller_that_wants_the_unfiltered_ranking_can_still_have_it(client):
    """`include_irrelevant` gives back exactly what the door used to return.

    The filter is a parameter, not a policy. An open ranking does not get to decide on a caller's behalf
    what they may see, and something downstream may well be counting on the old shape.
    """
    filtered = _discover(client, query="asdfghjkl qwertz")
    unfiltered = _discover(client, query="asdfghjkl qwertz", include_irrelevant=True)
    assert filtered["matches"] == []
    assert len(unfiltered["matches"]) == unfiltered["considered"] > 0
    assert unfiltered["matched"] == unfiltered["considered"]
    # And the two agree about the entities that really did answer a real query.
    real = _discover(client, query="quiet hotel")
    real_unfiltered = _discover(client, query="quiet hotel", include_irrelevant=True)
    answered = [m["id"] for m in real_unfiltered["matches"] if hive.relevance(m) > 0]
    assert [m["id"] for m in real["matches"]] == answered


def test_a_real_query_keeps_the_entities_that_answered_it(client):
    """The filter removes noise, not answers: whoever earned something is still there, in order."""
    found = _discover(client, query="breakfast")
    assert found["matched"] > 0
    assert found["matched"] < found["considered"], "something on this hub does not serve breakfast"
    scores = [m["score"] for m in found["matches"]]
    assert scores == sorted(scores, reverse=True)

    # Whoever answered is still there, and in the order the core ranked them.
    unfiltered = _discover(client, query="breakfast", include_irrelevant=True)
    assert [m["id"] for m in found["matches"]] == [m["id"] for m in unfiltered["matches"] if hive.relevance(m) > 0]


def test_the_core_still_answers_with_the_whole_ranked_hub(client):
    """`hive.discover` is deliberately unchanged, and the eval tools depend on that.

    The threshold is a door's decision. Putting it in the core would have changed what every measurement
    in `tools/` was measuring, and `federation.py` ranks the merged answer with its own scorer and needs
    the rows to do it.
    """
    found = hive.discover(query="asdfghjkl qwertz")
    assert set(found) == {"matches", "excluded", "ranking_policy"}, "the core's answer shape is a contract"
    assert len(found["matches"]) > 10


def test_a_forwarded_query_is_not_filtered_before_the_hub_that_asked_can_rank_it(client):
    """A hop returns rows, not conclusions: the asking hub re-scores them with its own scorer.

    Filtering at this door would hide rows from the only scorer entitled to judge them, which is the
    receiving hub's. `seen` is how a forwarded query identifies itself.
    """
    forwarded = _discover(client, query="asdfghjkl qwertz", seen="somewhere-else")
    assert len(forwarded["matches"]) > 10, "a peer gets the rows and decides for itself"


# --- the MCP door, and #154's response size -------------------------------------------------------


def test_the_agent_door_says_how_many_matched_and_leaves_the_rest_out(client):
    """Over MCP too, because the agent path is the one that cannot afford to read filler.

    An agent pays for every byte out of its context window. `hive_discover` at radius 2 came back at
    690 KB — 73 matches, about 65 of them scoring nothing, each with a full inline card.
    """
    answer = _mcp("hive_discover", {"query": "asdfghjkl qwertz"})
    assert answer["matches"] == []
    assert answer["matched"] == 0
    assert answer["considered"] > 0

    real = _mcp("hive_discover", {"query": "quiet hotel"})
    assert real["matched"] > 0
    assert all(hive.relevance(m) > 0 for m in real["matches"])


def test_the_threshold_runs_before_the_ceiling_so_the_slots_go_to_matches(client):
    """Order matters: cap first and the 20 slots fill with rows that answered nothing.

    Checked by asking for a single match of a query many entities answer — the one that comes back has
    to be a real match, and the count has to be the number that answered rather than the number ranked.
    """
    answer = _mcp("hive_discover", {"query": "quiet hotel", "limit": 1})
    assert len(answer["matches"]) == 1
    assert hive.relevance(answer["matches"][0]) > 0
    assert answer["matched"] >= 1

    # And a nonsense query with a generous limit still answers with nothing rather than filling the slots.
    assert _mcp("hive_discover", {"query": "asdfghjkl qwertz", "limit": 50})["matches"] == []


def test_an_agent_answer_is_small_enough_to_read(client):
    """The size claim, measured rather than asserted — #154 is a number, so this test is a number.

    Serialised the way an MCP client receives it. The threshold is what does the work here: the rows it
    removes are the ones carrying an inline card for an entity that answered nothing.
    """
    nonsense = len(json.dumps(_mcp("hive_discover", {"query": "asdfghjkl qwertz"})))
    assert nonsense < 2_000, nonsense
    real = len(json.dumps(_mcp("hive_discover", {"query": "quiet dog-friendly hotel"})))
    assert real < 60_000, real
    # Unfiltered is the old behaviour and is allowed to be big; the point is that it is now a choice.
    everything = len(json.dumps(_mcp("hive_discover", {"query": "asdfghjkl qwertz", "include_irrelevant": True})))
    assert everything > nonsense


@pytest.mark.parametrize("query", NOTHING)
def test_nothing_matched_is_reported_identically_at_both_doors(client, query):
    """REST and MCP answer the same question the same way, or an agent and an app disagree."""
    rest = _discover(client, query=query)
    over_mcp = _mcp("hive_discover", {"query": query})
    assert rest["matched"] == over_mcp["matched"] == 0
    assert rest["matches"] == over_mcp["matches"] == []
    assert rest["considered"] == over_mcp["considered"]
