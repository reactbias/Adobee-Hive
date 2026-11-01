"""Who asked for an introduction, and what the hub's answer to that is worth (#158).

`requester` is an unauthenticated free string and this hub has no way to make it anything else: it
has no accounts, and per-owner authorization is roadmap (#135). So the question this file pins is
not "is the requester authenticated" — the answer is no — but the one that is actually answerable:
**does the ledger say what it knows, or does it say something it made up?**

It used to make something up. `requester_hub` defaulted to `config.HIVE_HUB_ID`, the hub *receiving*
the request, so an agent from Zurich asking Basel was written into Basel's ledger as a Basel member.
These rows are the input to `calibration.py`, which is what ranks a hub in federated search, so the
default was putting words in a stranger's mouth inside the trust model's own evidence.

The fix is a column, not a gate. `requester_proof` is `member`, `claimed` or `none`, and a gate
built on any of the three would be a gate that is not there — which is why these tests check what is
*recorded* and check, separately, that nothing is being claimed for it.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from app import config, connections, db, folders, hive, hub
from app.mcp_server import server

ELSEWHERE = "zurich"


@pytest.fixture(autouse=True)
def clean_slate(client):
    """No rows and no links, so each test reads its own ledger."""
    connections.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_connections")
        cur.execute("DELETE FROM folder_links")
        cur.execute("DELETE FROM folder_grants")
    folders.reset()
    yield


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return (await c.call_tool(tool, args)).structured_content

    return asyncio.run(go())


def _an_entity() -> str:
    return hive.list_cards()[0]["id"]


# ---------------------------------------------------------------- what the hub establishes


def test_a_visitor_who_says_nothing_is_not_recorded_as_a_member_of_this_hub(client):
    """The bug. `requester_hub` was this hub's own id for anybody who could reach the port."""
    row = hub.connect("mara@example.com", _an_entity())

    assert row["requester_hub"] != config.HIVE_HUB_ID
    assert row["requester_hub"] == ""
    assert row["requester_proof"] == connections.BY_NOBODY
    assert connections.get(row["id"])["requester_proof"] == connections.BY_NOBODY, "and it is on the row"


def test_a_requester_who_names_their_hub_is_recorded_as_claiming_it_and_no_more(client):
    row = hub.connect("mara@example.com", _an_entity(), requester_hub=ELSEWHERE)

    assert row["requester_hub"] == ELSEWHERE
    assert row["requester_proof"] == connections.BY_CLAIM, "the hub cannot check this and does not pretend to"


def test_a_requester_this_hub_actually_carries_is_recorded_as_its_member(client):
    """The one of the three that is a check: this hub holds a card for that id, so it can answer."""
    member = _an_entity()
    row = hub.connect(member, hive.list_cards()[1]["id"])

    assert row["requester_hub"] == config.HIVE_HUB_ID
    assert row["requester_proof"] == connections.BY_MEMBER


def test_a_claim_never_outranks_what_the_hub_can_see_for_itself(client):
    """A member cannot talk itself into being somebody else's member by saying so."""
    member = _an_entity()
    row = hub.connect(member, hive.list_cards()[1]["id"], requester_hub=ELSEWHERE)

    assert row["requester_hub"] == config.HIVE_HUB_ID
    assert row["requester_proof"] == connections.BY_MEMBER


def test_the_hub_never_answers_member_because_of_something_in_the_request(client):
    """`member` is the only proof a reader may lean on, so nothing in the request may produce it."""
    for claim in (config.HIVE_HUB_ID, connections.BY_MEMBER, "", "   ", ELSEWHERE):
        _, proof = hub.requester_origin("nobody-on-this-hub@example.com", claim)
        assert proof != connections.BY_MEMBER, f"claiming {claim!r} bought membership"


def test_an_unknown_proof_value_is_stored_as_none_rather_than_as_itself(client):
    """`connections.request` is reachable from Python; it must not take an invented proof at its word."""
    folders.open_link("mara@example.com", "someone", auto_accept=True)
    row = connections.request(
        "mara@example.com",
        "someone",
        requester_hub=ELSEWHERE,
        requester_proof="attested-by-god",
        needs_confirmation=False,
    )
    assert row["requester_proof"] == connections.BY_NOBODY


# ---------------------------------------------------------------- at both doors


def test_the_rest_door_takes_a_requester_hub_and_says_what_it_did_with_it(client):
    res = client.post(
        "/api/hub/connect",
        json={"requester": "mara@example.com", "entity_id": _an_entity(), "requester_hub": ELSEWHERE},
    )
    assert res.status_code == 200
    out = res.json()
    assert out["requester_hub"] == ELSEWHERE and out["requester_proof"] == connections.BY_CLAIM


def test_the_mcp_door_takes_a_requester_hub_and_says_what_it_did_with_it(client):
    out = _mcp(
        "hub_connect",
        {"requester": "mara@example.com", "entity_id": _an_entity(), "requester_hub": ELSEWHERE},
    )
    assert out["requester_hub"] == ELSEWHERE and out["requester_proof"] == connections.BY_CLAIM


def test_both_doors_agree_about_a_requester_who_said_nothing(client):
    rest = client.post("/api/hub/connect", json={"requester": "a@example.com", "entity_id": _an_entity()}).json()
    mcp = _mcp("hub_connect", {"requester": "b@example.com", "entity_id": _an_entity()})

    assert rest["requester_proof"] == mcp["requester_proof"] == connections.BY_NOBODY
    assert rest["requester_hub"] == mcp["requester_hub"] == ""


# ---------------------------------------------------------------- and what it is not used for


def test_the_proof_gates_nothing_which_is_why_it_is_recorded(client):
    """An unproven requester is still served. The honesty is in the ledger, not in a refusal.

    Said out loud because the opposite would be worse than the bug: a gate keyed on an
    unauthenticated string would refuse honest callers and admit anyone who guessed the shape of it.
    """
    row = hub.connect("total-stranger@example.com", _an_entity())
    assert row["state"] == connections.OPEN
    assert row["requester_proof"] == connections.BY_NOBODY


def test_a_row_written_before_this_column_existed_still_reads(client):
    """The demo hub has a Postgres snapshot of older rows; a missing proof is a fact about the row."""
    folders.open_link("old@example.com", "someone", auto_accept=True)
    row = connections.request("old@example.com", "someone", needs_confirmation=False)
    with db.write() as cur:
        cur.execute("UPDATE hub_connections SET requester_proof = NULL WHERE id = ?", [row["id"]])

    assert connections.get(row["id"])["requester_proof"] is None
    assert connections.awaiting_rating("old@example.com"), "and it is still evidence"
