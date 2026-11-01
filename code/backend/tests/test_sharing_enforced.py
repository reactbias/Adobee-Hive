"""An item-level sharing flag is enforced on the paths that actually serve (#121).

The promise in the README is that `push` is "held, never searchable" and that the stricter of the
entity's flag and the item's always wins. `sharing.py` resolved that correctly and nothing called
it. `hive.discover` — the function REST and MCP discovery both run — never looked at a card's
`sharing` field at all, so an entity its owner had marked `push` came back from both. The façade in
`hub.py` did call `sharing.searchable(match.get("sharing"), ...)`, but `discover` put no `sharing`
key on a result, so `resolve(None, None)` answered `confirm` and the check passed everything. An
enforcement reading a field nobody sets is not an enforcement.

The other half is the contact block. `with_contact` skipped *filling in* a channel the owner had
closed but left a value that was already there, and `publish` runs it before signing — so a phone
number marked `never` went into the signed body, which `GET /api/hive/cards` serves to anyone with
no credential and every federated hop carries. A projection downstream cannot take that back
without breaking the signature the card is published under, so the only moment it can be kept out
is before the card is signed.

What this file does not claim: that cards are secret. The index is public by design. These are
rules about what the hub *serves about an entity that asked it not to*, not about the cards.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from app import config, federation, hive, hub, reputation, sharing
from app.mcp_server import server
from tests.test_federation import FakeHive, FakeNet, _card

HELD = "held-plumbing"
CLOSED = "closed-plumbing"
OPEN = "open-plumbing"


def _publish(entity_id: str, **extra) -> dict:
    """A fictional service card, published through the real signing path."""
    return hive.publish(
        {
            "id": entity_id,
            "slug": entity_id,
            "kind": "service",
            "name": f"{entity_id} (fictional)",
            "description": "Invented for the demo: emergency plumbing and drain work in Basel.",
            "offers": [{"title": "plumbing", "summary": "Invented for the demo."}],
            **extra,
        }
    )


@pytest.fixture(scope="module", autouse=True)
def cards(client):
    """One entity per flag, published once: `push`, `never` and `public`."""
    _publish(HELD, sharing=sharing.PUSH)
    _publish(CLOSED, sharing=sharing.NEVER)
    _publish(OPEN, sharing=sharing.PUBLIC)


def _ids(found: dict) -> set[str]:
    return {m["id"] for m in found["matches"]}


def _missed(found: dict) -> set[str]:
    return {e["id"] for e in found["excluded"]}


# ---------------------------------------------------------------- the entity's own flag


def test_a_held_entity_is_not_searchable_on_the_path_the_api_serves(client):
    """`hive.discover`, not the façade: this is the function REST and MCP discovery both run."""
    found = hive.discover(query="plumbing")

    assert OPEN in _ids(found), "the control: an open entity is still found"
    assert HELD not in _ids(found)
    assert CLOSED not in _ids(found)


def test_a_held_entity_is_in_neither_list_not_even_the_near_misses(client):
    """An exclusion names the business and says why it missed, which is most of what a match says."""
    found = hive.discover(query="helipad", features=["helipad"])

    assert HELD not in _missed(found) and CLOSED not in _missed(found)
    assert HELD not in _ids(found) and CLOSED not in _ids(found)


def test_every_result_now_carries_the_flag_the_facade_reads(client):
    """The field whose absence made the façade's check pass everything it was given."""
    found = hive.discover(query="plumbing")

    assert all("sharing" in match for match in found["matches"])
    assert next(m for m in found["matches"] if m["id"] == OPEN)["sharing"] == sharing.PUBLIC


def test_a_person_card_with_no_flag_of_its_own_is_confirm_and_still_findable(client):
    """The default must not have become `never`: people are discoverable, and asking is the point."""
    found = hive.discover(query="plumbing", kind="person")
    assert all(m["sharing"] in sharing.SEARCHABLE for m in found["matches"])
    assert hive.sharing_default({"kind": "person"}) == sharing.CONFIRM
    assert hive.sharing_default({"kind": "service"}) == sharing.PUBLIC


def test_rest_and_mcp_both_withhold_it(client):
    """The two served surfaces, which is where the issue says the enforcement was missing."""
    over_rest = client.get("/api/hive/discover", params={"query": "plumbing"}).json()

    async def go():
        async with Client(server) as c:
            return (await c.call_tool("hive_discover", {"query": "plumbing"})).structured_content

    over_mcp = asyncio.run(go())

    for answer in (over_rest, over_mcp):
        assert OPEN in _ids(answer)
        assert HELD not in _ids(answer) and CLOSED not in _ids(answer)
        assert HELD not in _missed(answer) and CLOSED not in _missed(answer)


def test_the_facade_and_the_core_now_agree(client):
    """`hub.search` filtered on a key that was never there. Both layers, same answer."""
    served = asyncio.run(hub.search({"query": "plumbing"}))

    assert HELD not in {m["id"] for m in served["matches"]}
    assert OPEN in {m["id"] for m in served["matches"]}


def test_a_public_identifier_is_still_not_a_read_capability(client):
    """An authorised owner-initiated exchange stays distinct from public search.

    Knowing the id of a held entity does not make it askable: `hub.connect` refuses it, and that
    refusal is what "the owner has to move first" means in code rather than in the README.
    """
    with pytest.raises(hub.HubError, match="their own initiative"):
        hub.connect("Mara Keller", HELD)
    with pytest.raises(hub.HubError, match="not shared"):
        hub.connect("Mara Keller", CLOSED)


# ---------------------------------------------------------------- the contact block


def test_a_closed_channel_never_reaches_the_signed_body(client):
    """The signed body is public — every card, no credential, plus every federated hop.

    So a value in a channel the owner closed cannot be withheld downstream: it is published under a
    signature, and redacting it afterwards would break the signature it is published under. The only
    moment it can be kept out is before the card is signed.
    """
    published = _publish(
        "shy-plumbing",
        contact={"email": "open@x.example", "phone": "+41 79 000 00 00", "whatsapp": "+41 79 111 11 11"},
        contact_sharing={"phone": "never", "whatsapp": "push"},
    )

    assert "phone" not in published["contact"], "a `never` number went into the body the hub publishes"
    assert "whatsapp" not in published["contact"], "a `push` channel is the owner's to send"
    assert published["contact"]["email"] == "open@x.example"
    # And the card still verifies, because the redaction happened before the signature.
    assert hive.verify_pinned(published, {"shy-plumbing": published["trust"]["public_key"]})


def test_the_public_read_serves_no_closed_channel_either(client):
    """Belt as well as braces: the serving side applies the same rule to a card published earlier."""
    before = {"contact": {"email": "a@b.example", "phone": "+41 79 000 00 00"}, "contact_sharing": {"phone": "never"}}

    assert hive.public_contact(before) == {"email": "a@b.example"}


def test_the_flag_that_says_why_is_still_served(client):
    """The value is gone; the owner's own word for why is not withheld as well.

    `contact_sharing` is part of what the owner signed and the index is public, so a result that
    disagreed with the card it travels with would be the worse answer.
    """
    found = hive.discover(query="plumbing", seen=["basel"])
    match = next(m for m in found["matches"] if m["id"] == "shy-plumbing")

    assert match["contact"] == match["card"]["contact"]
    assert match["contact_sharing"] == match["card"]["contact_sharing"]
    assert match["contact_sharing"]["phone"] == "never"
    assert "phone" not in match["contact"]


def test_the_stricter_flag_still_wins_when_the_entity_is_the_strict_one(client):
    """A channel that says `public` on an entity held back as `confirm` resolves to `confirm`."""
    card = {"kind": "person", "contact": {"email": "a@b.example"}, "contact_sharing": {"email": "public"}}

    assert hive.public_contact(card) == {"email": "a@b.example"}
    assert sharing.resolve(hive.sharing_default(card), "public") == sharing.CONFIRM


# ---------------------------------------------------------------- and the same rule on an arrival


@pytest.fixture
def net(monkeypatch):
    """Wire a peer network into federation.py and leave no trust or cached profile behind."""

    def wire(*hubs: FakeHive) -> FakeNet:
        transport = FakeNet(*hubs)
        monkeypatch.setattr(federation, "DEFAULT_TRANSPORT", transport)
        monkeypatch.setattr(config, "HIVE_PEER_URLS", [h.url for h in hubs])
        monkeypatch.setattr(config, "HIVE_HUB_ID", "basel")
        federation.forget()
        reputation.forget()
        return transport

    yield wire
    federation.forget()
    reputation.forget()


ASK = {"kind": "hotel", "features": ["dog-friendly"], "check_in": "2027-03-10", "check_out": "2027-03-12"}


def test_a_held_entity_relayed_by_a_peer_is_withheld_here_too(client, net):
    """The owner's decision does not stop at a hub boundary.

    Read after `verify_pinned`, so the flag comes from a body the owner signed and not from whoever
    relayed it. Nobody's reputation is charged: the hub that should have enforced this is the
    origin, and from here the origin and the carrier are not reliably told apart.
    """
    held = {**_card("hotel-held", "Hotel Held (fictional)"), "sharing": sharing.PUSH}
    peer = FakeHive("zurich", cards=[held, _card("hotel-open", "Hotel Open (fictional)")])
    net(peer)

    found = hive.discover(**ASK, radius=1)

    assert "hotel-open" in _ids(found), "the control: the peer's open card still arrives"
    assert "hotel-held" not in _ids(found)
    rejected = {r["card_id"]: r["reason"] for r in found["federation"]["rejected"]}
    assert "own initiative" in rejected["hotel-held"], rejected
    assert reputation.observed("zurich").invalid == 0, "withholding is not a tamper and costs no trust"
