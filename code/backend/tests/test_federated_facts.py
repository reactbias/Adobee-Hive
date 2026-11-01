"""A peer's summary is bound to the card it relayed, or it is labelled as the peer's word (#111).

The guarantee that already held: a relayed card is checked with `hive.verify_pinned` against the key
fetched from the card's *own* hub, never through the relay, so a carrier can withhold a card or
delay it but not forge one. What did not hold was the prose around it. `_verified` authenticated the
nested card and then let the carrier's own dictionary stand as the result, so a response could say
`signature_valid: true` beside a name, a description and a contact address the owner never signed.
Nothing had to be forged for that: the carrier simply wrote different words next to a genuine card.

Every test here keeps the origin, its key and its card **genuine** and varies only the untrusted
text beside them, which is the one case the issue is about. That also means no number of real hubs
can prove it: a real peer answers honestly, so a run of `lan.sh` shows nothing either way. What is
needed is a carrier that lies, which is what `FakeHive(match=...)` is.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from app import config, federation, hive, hub, reputation
from app.mcp_server import server
from tests.test_federation import FakeHive, FakeNet, _card

ASK = {"kind": "hotel", "features": ["dog-friendly"], "check_in": "2027-03-10", "check_out": "2027-03-12"}
THEIRS = "hotel-limmat"
HONEST = "Hotel Limmat (fictional)"


@pytest.fixture
def net(monkeypatch):
    """Wire a peer network into federation.py and leave no trust or cached profile behind."""

    def wire(*hubs: FakeHive, peers: list[FakeHive] | None = None) -> FakeNet:
        transport = FakeNet(*hubs)
        monkeypatch.setattr(federation, "DEFAULT_TRANSPORT", transport)
        monkeypatch.setattr(config, "HIVE_PEER_URLS", [h.url for h in (peers if peers is not None else hubs)])
        monkeypatch.setattr(config, "HIVE_HUB_ID", "basel")
        federation.forget()
        reputation.forget()
        return transport

    yield wire
    federation.forget()
    reputation.forget()


def _liar(**embellishment) -> FakeHive:
    """A peer carrying one genuine, correctly signed card and saying something else about it."""
    return FakeHive("zurich", cards=[_card(THEIRS, HONEST)], match=embellishment)


def _found(net, peer: FakeHive) -> dict:
    net(peer)
    out = hive.discover(**ASK, radius=1)
    return next(m for m in out["matches"] if m["id"] == THEIRS)


# ---------------------------------------------------------------- the facts come from the card


def test_a_carrier_cannot_rename_the_business_it_relays(client, net):
    """The reproduction. The card is genuine and verifies; the name beside it is the carrier's."""
    match = _found(net, _liar(name="LUXURY SPA RESORT", tagline="Sponsored", description="We wrote this"))

    assert match["name"] == HONEST, "the carrier's name was served as fact"
    assert match["name"] == match["card"]["name"]
    assert match["description"] == match["card"]["description"]
    assert match["tagline"] == match["card"]["tagline"]


def test_a_carrier_cannot_redirect_the_contact_details(client, net):
    """The one that costs a real person money: an address the owner never signed, next to a tick."""
    card = _card(THEIRS, HONEST)
    card = {**card, "contact": {"email": "hello@limmat.example", "phone": ""}}
    peer = FakeHive("zurich", cards=[card], match={"contact": {"email": "attacker@elsewhere.example"}})

    match = _found(net, peer)

    assert match["contact"] == {"email": "hello@limmat.example", "phone": ""}
    assert match["contact"] == match["card"]["contact"]


def test_the_signature_verdict_is_the_receivers_and_cannot_be_overwritten(client, net):
    """Both directions. A carrier may not claim a card checked out, nor claim that one did not."""
    denied = _found(net, _liar(signature_valid=False))
    assert denied["signature_valid"] is True, "we verified it ourselves; the carrier does not get a vote"
    assert denied["card"]["trust"]["signature_valid"] is True
    assert hive.verify_pinned(
        denied["card"], {THEIRS: denied["card"]["trust"]["public_key"]}
    ), "and restating the verdict must not have disturbed the signed bytes"


def test_a_field_the_carrier_invented_is_dropped_rather_than_passed_on(client, net):
    """Unknown fails closed: a key a consumer cannot place is the one it will read as fact."""
    match = _found(net, _liar(sponsored=True, verified_by_hub=True, rating_stars=5))

    assert "sponsored" not in match
    assert "verified_by_hub" not in match
    assert "rating_stars" not in match


def test_whether_a_card_is_claimed_comes_from_the_card_too(client, net):
    """`claimed` decides whether an agent may treat an entry as a business that agreed, so it is
    read from the provenance block the owner signed and not from the carrier's summary."""
    compiled = {**_card(THEIRS, HONEST), "provenance": {"verified_by_owner": False, "source": "public web"}}
    peer = FakeHive("zurich", cards=[compiled], match={"claimed": True})

    match = _found(net, peer)

    assert match["claimed"] is False, "a compiled lead was relayed as a business that agreed"


# ---------------------------------------------------------------- and what only the peer can know stays


def test_the_peers_own_ranking_and_availability_survive_and_are_named_as_its_claims(client, net):
    """Binding the facts must not throw away the useful part: a hub is trusted for its own ranking."""
    match = _found(net, _liar(score=73.5, why=["has dog-friendly"], from_price_chf=210.0, rating=4.4))

    assert match["score"] == 73.5
    assert match["from_price_chf"] == 210.0
    assert match["rating"] == 4.4
    assert "has dog-friendly" in match["why"]
    assert set(match["verified"]["peer_claims"]) >= {"score", "from_price_chf", "rating", "why"}


def test_the_result_says_which_fields_were_signed_and_which_were_the_peers(client, net):
    """The second acceptance item, answered in the response rather than in this module's docstring."""
    match = _found(net, _liar())

    verified = match["verified"]
    assert verified["card"] is True
    assert verified["origin"] == "zurich"
    assert "the key this entity's own hub pinned" in verified["how"]
    assert {"name", "description", "kind"} <= set(verified["signed_facts"])
    assert not set(verified["signed_facts"]) & set(verified["peer_claims"]), "a field is one or the other"


def test_an_exclusion_carries_no_card_so_it_is_marked_the_peers_own_account(client, net):
    """Where a fact genuinely cannot be bound, it is made visibly the peer's claim, not the hub's."""
    peer = FakeHive("zurich")

    async def answer(ask, radius, budget_ms, seen):
        return {
            "matches": [],
            "excluded": [{"id": "hotel-aare", "name": "Hotel Aare", "why_not": ["no dogs"], "signature_valid": True}],
            "ranking_policy": "No paid placement.",
        }

    peer.search = answer  # type: ignore[method-assign]
    net(peer)

    out = hive.discover(**ASK, radius=1)
    left_out = next(e for e in out["excluded"] if e["id"] == "hotel-aare")

    assert left_out["asserted_by"] == "zurich"
    assert left_out["verified"]["card"] is False
    assert "peer's own account" in left_out["verified"]["how"]


# ---------------------------------------------------------------- on the paths that actually serve


def test_a_local_result_is_untouched_by_any_of_this(client, net):
    """Radius 0 is still byte-identical for a direct caller, and a local match has no carrier."""
    plain = hive.discover(**ASK)
    assert set(plain) == {"matches", "excluded", "ranking_policy"}
    assert all("verified" not in m for m in plain["matches"])

    net(_liar())
    local = next(m for m in hive.discover(**ASK, radius=1)["matches"] if m["id"] == "hotel-rheinblick")
    assert "verified" not in local, "nothing relayed it, so there is nothing to say about a carrier"


def test_rest_and_mcp_both_get_the_bound_facts(client, net):
    """The two surfaces a consumer actually uses, not the module under them."""
    net(_liar(name="LUXURY SPA RESORT"))

    over_rest = client.get("/api/hive/discover", params={**ASK, "radius": 1}).json()
    rest = next(m for m in over_rest["matches"] if m["id"] == THEIRS)

    async def go():
        async with Client(server) as c:
            return (await c.call_tool("hive_discover", {**ASK, "radius": 1})).structured_content

    over_mcp = asyncio.run(go())
    mcp = next(m for m in over_mcp["matches"] if m["id"] == THEIRS)

    assert rest["name"] == mcp["name"] == HONEST
    assert rest["verified"]["card"] is mcp["verified"]["card"] is True


def test_the_hub_facade_passes_the_bound_facts_through(client, net):
    """`hub.search` is where the app and `hub_connect` read a match from, so it has to carry them."""
    net(_liar(name="LUXURY SPA RESORT"))

    served = asyncio.run(hub.search(ASK, radius=1))
    match = next(m for m in served["matches"] if m["id"] == THEIRS)

    assert match["name"] == HONEST
    assert match["verified"]["origin"] == "zurich"
