"""The id a federated search gave you is readable from the hub you searched (#150).

The dead end, from a real agent-as-user run: a search on `basel` at radius 1 returns Svenja Aebi, who
lives on `zurich`. The server's own instructions say the next step is to read her card. `hive_get_card`
then answered `{"error": "No Hive card 'svenja-aebi'."}`, and the tool takes no hub parameter, so there
was nowhere else to ask. Re-tested on merged #146 and still unchanged.

The signed card does travel inline on a federated match, and that is what the connect path uses — but
nothing in the tool description said so, and a tool documented as *the* way to read a card has to work.
So both: `hive_get_card` and `GET /api/hive/cards/{id}` ask this hub's peers for an id they do not carry,
and `hive_discover`'s description now says the card is already in the caller's hands.

Built on the peer surface federation already has — a browse one hop out, then the card off the match
whose id was wanted — because `Transport` has no single-card route and adding one would mean a new
endpoint every hub has to serve.

The `isError: false` half of #150 is #155's; this file is only about the lookup.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from app import config, guard, hive, peers, sharing
from app.mcp_server import server
from tests.mcp_result import tool_result
from tests.test_federation import FakeHive, net  # noqa: F401  (net is a fixture)

REMOTE = {
    "id": "svenja-aebi",
    "slug": "svenja-aebi",
    "kind": "person",
    "name": "Svenja Aebi (fictional)",
    "tagline": "Rust systems work",
    "offers": ["Rust systems work — CHF 1400 a day"],
}


def _mcp(tool: str, args: dict) -> dict:
    """Call an MCP tool the way a client does."""

    async def go():
        async with Client(server) as c:
            return tool_result(await c.call_tool(tool, args))

    return asyncio.run(go())


@pytest.fixture
def zurich(net):  # noqa: F811
    """A peer hub carrying one person this hub does not have."""
    peer = FakeHive("zurich", cards=[REMOTE])
    net(peer)
    return peer


def test_the_card_of_an_entity_found_through_a_peer_can_be_read(client, zurich):
    """The whole of #150: the id the search returned is readable from the hub that was searched."""
    found = hive.discover(query="Rust systems", radius=1, budget_ms=5000)
    assert "svenja-aebi" in {m["id"] for m in found["matches"]}, "the search has to find her first"

    card = hive.card_from_peer("svenja-aebi")
    assert card is not None
    assert card["name"] == REMOTE["name"]
    assert card["offers"] == REMOTE["offers"]
    # And it says where it came from, because a card is not less true for being remote but where it came
    # from is part of reading it.
    assert card["trust"]["federation"]["path"][0] == "zurich"
    assert hive.verify_pinned(card, zurich.profile()["owner_keys"])


def test_the_rest_door_answers_for_a_remote_id_instead_of_four_hundred(client, zurich):
    """`GET /api/hive/cards/svenja-aebi` on basel used to be HTTP 400 "No Hive card"."""
    answer = client.get("/api/hive/cards/svenja-aebi")
    assert answer.status_code == 200, answer.text
    assert answer.json()["name"] == REMOTE["name"]
    assert hive.verify_pinned(answer.json(), zurich.profile()["owner_keys"])


def test_the_agent_door_answers_for_a_remote_id(client, zurich):
    """And over MCP, which is the door the user test used and the one an agent follows."""
    card = _mcp("hive_get_card", {"card_id": "svenja-aebi"})
    assert "error" not in card, card
    assert card["name"] == REMOTE["name"]
    assert hive.verify_pinned(card, zurich.profile()["owner_keys"])


def test_a_local_card_is_still_answered_without_asking_anybody(client, zurich):
    """The local lookup comes first: a card this hub carries costs no outbound call at all."""
    assert client.get("/api/hive/cards/rheinblick").json()["id"] == "hotel-rheinblick"
    assert _mcp("hive_get_card", {"card_id": "hotel-rheinblick"})["id"] == "hotel-rheinblick"
    assert zurich.asks == [], "a card we have is not a question for a peer"


def test_radius_zero_keeps_the_old_local_only_behaviour(client, zurich):
    """Anything relying on "this hub only" can still have it, and gets the old error."""
    assert client.get("/api/hive/cards/svenja-aebi", params={"radius": 0}).status_code == 400
    assert "error" in _mcp("hive_get_card", {"card_id": "svenja-aebi", "radius": 0})
    assert zurich.asks == []


def test_an_id_nobody_has_still_says_so(client, zurich):
    """A genuinely missing id is still a refusal, and naming the id is the useful part of it."""
    answer = client.get("/api/hive/cards/does-not-exist-anywhere")
    assert answer.status_code == 400
    assert "does-not-exist-anywhere" in answer.json()["detail"]
    over_mcp = _mcp("hive_get_card", {"card_id": "does-not-exist-anywhere"})
    assert "does-not-exist-anywhere" in over_mcp["error"]


def test_a_hub_with_no_peers_asks_nobody_and_does_not_hang(client, monkeypatch):
    """No peers configured is the common case for a single hub, and it must cost nothing.

    `card_from_peer` returns None before any transport is touched, so the demo hub and the deployed
    single instance behave exactly as they did.
    """
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    assert hive.card_from_peer("svenja-aebi") is None
    assert client.get("/api/hive/cards/svenja-aebi").status_code == 400


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_a_remote_compiled_card_keeps_its_signed_provenance(client, net, transport):  # noqa: F811
    """Reading through either consumer door preserves the bytes checked against the origin's registry."""
    compiled = {**REMOTE, "provenance": {"verified_by_owner": False, "source": "public website"}}
    peer = FakeHive("zurich", cards=[compiled])
    # FakeHive signs the body correctly but defaults its unsigned trust metadata to claimed.
    peer.cards[0]["trust"]["claimed"] = False
    peer.cards[0]["trust"]["provenance"] = compiled["provenance"]
    net(peer)

    if transport == "rest":
        answer = client.get("/api/hive/cards/svenja-aebi")
        assert answer.status_code == 200, answer.text
        card = answer.json()
    else:
        card = _mcp("hive_get_card", {"card_id": "svenja-aebi"})

    assert card["provenance"] == compiled["provenance"]
    assert card["trust"]["claimed"] is False
    assert card["trust"]["federation"]["origin"] == "zurich"
    assert card["trust"]["federation"]["path"] == ["zurich", "basel"]
    assert hive.verify_pinned(card, peer.profile()["owner_keys"])


@pytest.mark.parametrize("flag", [sharing.PUSH, sharing.NEVER])
def test_a_peer_card_withheld_by_its_owner_is_not_readable_via_fallback(client, net, flag):  # noqa: F811
    """Knowing a private remote id does not bypass the sharing projection on federated arrivals."""
    peer = FakeHive("zurich", cards=[{**REMOTE, "sharing": flag}])
    net(peer)

    assert hive.card_from_peer("svenja-aebi") is None
    assert client.get("/api/hive/cards/svenja-aebi").status_code == 400
    assert "svenja-aebi" in _mcp("hive_get_card", {"card_id": "svenja-aebi"})["error"]


def test_a_tampered_peer_card_is_refused_at_both_consumer_doors(client, zurich):
    """The lookup never returns a peer's changed body merely because the id matches."""
    zurich.cards[0]["name"] = "Not what the owner signed"

    assert client.get("/api/hive/cards/svenja-aebi").status_code == 400
    assert "svenja-aebi" in _mcp("hive_get_card", {"card_id": "svenja-aebi"})["error"]


def test_card_fallback_uses_the_live_peer_list_not_the_environment(client, zurich, monkeypatch):
    """An administratively added peer remains reachable even on a hub with no environment seed."""
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    monkeypatch.setattr(peers, "urls", lambda: [zurich.url])

    card = hive.card_from_peer("svenja-aebi")
    assert card is not None
    assert hive.verify_pinned(card, zurich.profile()["owner_keys"])


def test_mcp_peer_card_reads_spend_the_federated_budget_only_after_a_local_miss(client, zurich, monkeypatch):
    """A card read cannot walk around the outbound budget enforced on federated discovery."""
    monkeypatch.setattr(guard, "federated", guard.RateLimiter(per_client=1, total=1))

    assert "error" not in _mcp("hive_get_card", {"card_id": "hotel-rheinblick"})
    assert "error" not in _mcp("hive_get_card", {"card_id": "svenja-aebi"})
    asked = len(zurich.asks)
    refused = _mcp("hive_get_card", {"card_id": "svenja-aebi"})
    assert "Try again in" in refused["error"]
    assert len(zurich.asks) == asked
