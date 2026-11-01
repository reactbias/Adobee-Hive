"""The hub as an agent and an operator reach it: search, connect, score, and administer."""

from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from app import blocklist, config, connections, db, folders, hive, registration, sharing
from app.mcp_server import server
from tests.mcp_result import tool_result


@pytest.fixture(autouse=True)
def clean_slate(client):
    """Empty log, empty blocklist, no admin token unless a test sets one."""
    blocklist.init()
    connections.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_connections")
        cur.execute("DELETE FROM hub_blocklist")
        cur.execute("DELETE FROM folder_links")
        cur.execute("DELETE FROM folder_grants")
    folders.reset()
    yield


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return tool_result(await c.call_tool(tool, args))

    return asyncio.run(go())


def _an_entity() -> str:
    return hive.list_cards()[0]["id"]


def _introduced(requester: str, target: str, **kw) -> dict:
    """A booking, with the folder link it now stands on made first (folders.py, connections.link_for).

    The tests below are about scoring, standing and the admin counts. That they all have to link
    two folders first is the precondition working.
    """
    folders.open_link(requester, target, auto_accept=True)
    return connections.request(requester, target, **kw)


# ---------------------------------------------------------------- connect


def test_an_agent_connects_and_gets_a_connection_id_back(client):
    out = _mcp("hub_connect", {"requester": "mara@example.com", "entity_id": _an_entity()})

    assert out["id"].startswith("cx-")
    assert out["state"] in (connections.OPEN, connections.REQUESTED)
    assert out["target"] == _an_entity()


def test_connecting_to_a_blocked_entity_is_refused(client):
    entity = _an_entity()
    blocklist.block(blocklist.ENTITY, entity, "fabricated reviews")

    out = _mcp("hub_connect", {"requester": "mara@example.com", "entity_id": entity})
    assert "blocked" in out["error"]

    res = client.post("/api/hub/connect", json={"requester": "mara@example.com", "entity_id": entity})
    assert res.status_code == 400 and "blocked" in res.json()["detail"]


def test_connecting_through_a_blocked_hub_is_refused(client):
    blocklist.block(blocklist.HUB, "spam.example", "forgery")
    out = _mcp("hub_connect", {"requester": "m@example.com", "entity_id": _an_entity(), "target_hub": "spam.example"})
    assert "blocked" in out["error"]


def test_an_unknown_entity_is_refused_rather_than_logged(client):
    out = _mcp("hub_connect", {"requester": "m@example.com", "entity_id": ""})
    assert "error" in out
    assert connections.awaiting_rating() == [], "a refused request leaves no row behind"


def test_connecting_links_the_two_folders_first_and_says_what_that_opened(client):
    """The middle of the story, now real: the folders link, and the answer carries the manifest.

    A `public` Card is a standing yes to being contacted — publishing it is the yes — so the link is
    established in the same step and the connection opens. The manifest is what the link bought:
    what this requester may see of that folder, and a count of what was withheld without naming it.
    """
    entity = _an_entity()
    out = _mcp("hub_connect", {"requester": "mara@example.com", "entity_id": entity})

    assert out["folder_link"].startswith("fl-")
    assert folders.linked("mara@example.com", entity)
    assert out["folder"]["owner"] == entity and out["folder"]["linked"] is True
    assert "withheld" in out["folder"], "what is not shown is counted, never named"


def test_a_booking_at_the_rest_door_without_a_folder_link_is_refused_readably(client):
    """connections.request is the door this invariant sits on, so the refusal has to read as English."""
    res = client.post("/api/hub/connections/cx-nope/confirm")
    assert res.status_code == 400

    with pytest.raises(connections.ConnectionError_) as refused:
        connections.request("mara@example.com", _an_entity(), needs_confirmation=False)
    assert "connect their folders before a booking is made" in str(refused.value)


# ---------------------------------------------------------------- score


def test_scoring_an_introduction_reports_the_gap_against_what_was_promised(client):
    """The moment the trust layer learns something: promised against found."""
    row = _introduced(
        "mara@example.com",
        "hotel-far",
        target_hub="zurich",
        via_hub="zurich",
        published_rating=50,
        needs_confirmation=False,
    )

    out = _mcp("hub_score", {"connection_id": row["id"], "rating": 25, "note": "noisy"})

    assert out["connection"]["state"] == connections.RATED
    assert out["gap"] == 25 and out["gap_stars"] == 2.5, "promised 5.0, found 2.5"
    assert out["hub"] == "zurich"
    assert "promised 5.0" in out["says"] and "2.5" in out["says"]
    assert out["hub_standing"]["hub"] == "zurich"


def test_a_score_outside_the_scale_is_refused_at_the_rest_door(client):
    row = _introduced("m@example.com", "x", published_rating=40, needs_confirmation=False)
    assert client.post(f"/api/hub/connections/{row['id']}/score", json={"rating": 51}).status_code == 422
    assert client.post(f"/api/hub/connections/{row['id']}/score", json={"rating": -1}).status_code == 422


def test_scoring_twice_is_refused(client):
    row = _introduced("m@example.com", "x", published_rating=40, needs_confirmation=False)
    assert client.post(f"/api/hub/connections/{row['id']}/score", json={"rating": 40}).status_code == 200
    assert client.post(f"/api/hub/connections/{row['id']}/score", json={"rating": 10}).status_code == 400


def test_the_owner_can_decline_and_it_never_becomes_a_rating(client):
    row = _introduced("m@example.com", "lena", needs_confirmation=True)
    assert client.post(f"/api/hub/connections/{row['id']}/decline").status_code == 200
    assert client.post(f"/api/hub/connections/{row['id']}/score", json={"rating": 50}).status_code == 400


def test_an_agent_can_list_what_is_still_waiting_on_a_human(client):
    row = _introduced("mara@example.com", "x", published_rating=40, needs_confirmation=False)
    out = _mcp("hub_connections", {"requester": "mara@example.com"})
    assert [c["id"] for c in out["awaiting_rating"]] == [row["id"]]


# ---------------------------------------------------------------- standing


def test_hub_standing_reports_lower_is_better_and_says_so(client):
    for _ in range(3):
        row = _introduced("m@example.com", "x", via_hub="boastful", published_rating=50, needs_confirmation=False)
        connections.rate(row["id"], 25)
    for _ in range(3):
        row = _introduced("m@example.com", "y", via_hub="modest", published_rating=25, needs_confirmation=False)
        connections.rate(row["id"], 50)

    peers = {p["hub"]: p for p in _mcp("hub_standing", {})["peers"]}
    assert peers["boastful"]["error"] == 25.0 and peers["modest"]["error"] == -25.0
    assert peers["modest"]["error"] < peers["boastful"]["error"]
    assert "over-promised" in peers["boastful"]["why"]


# ---------------------------------------------------------------- administration


def test_the_admin_overview_counts_the_three_stores(client):
    blocklist.block(blocklist.HUB, "spam.example", "forgery")
    blocklist.block(blocklist.ENTITY, "hotel-dodgy", "fake")
    _introduced("m@example.com", "x", published_rating=40, needs_confirmation=False)

    out = client.get("/api/admin/overview").json()
    assert out["index"]["entities"] > 0
    assert out["blocklist"] == {"hubs": 1, "entities": 1}
    assert out["connections"]["awaiting_rating"] == 1


def test_the_settings_come_back_as_fields_a_form_can_render(client):
    out = client.get("/api/admin/settings").json()
    fields = {f["key"]: f for f in out["fields"]}

    assert fields["name"]["editable"] and fields["hub_id"]["editable"] is False
    assert "options" in fields["verification"], "a closed choice ships its options"
    assert all(f["help"] for f in out["fields"]), "every field explains itself to an operator"
    assert len(out["sharing_flags"]) == len(sharing.ORDER)
    assert out["calibration"]["lower_is_better"] is True


def test_the_blocklist_is_readable_without_a_token_but_not_writable(client, monkeypatch):
    """What a hub shuts out is something it should be willing to say out loud."""
    blocklist.block(blocklist.HUB, "spam.example", "forgery")
    assert client.get("/api/admin/blocklist").status_code == 200

    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    body = {"kind": "hub", "subject": "other.example", "reason": "spam"}
    assert client.post("/api/admin/blocklist", json=body).status_code == 403
    assert client.post("/api/admin/blocklist", json=body, headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert client.post("/api/admin/blocklist", json=body, headers={"X-Admin-Token": "s3cret"}).status_code == 200
    assert blocklist.is_blocked(blocklist.HUB, "other.example")


def test_administration_fails_closed_when_no_token_is_configured(client, monkeypatch):
    """A hub whose blocklist anyone can edit has no blocklist. Unset means shut, not open."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    res = client.post("/api/admin/blocklist", json={"kind": "hub", "subject": "x.example", "reason": "spam"})

    assert res.status_code == 503, "no token configured must refuse, never run open"
    assert not blocklist.is_blocked(blocklist.HUB, "x.example")


def test_a_block_without_a_reason_is_refused(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    res = client.post(
        "/api/admin/blocklist",
        json={"kind": "hub", "subject": "x.example", "reason": ""},
        headers={"X-Admin-Token": "s3cret"},
    )
    assert res.status_code == 422


def test_lifting_a_block_needs_the_token_too(client, monkeypatch):
    blocklist.block(blocklist.HUB, "spam.example", "forgery")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")

    assert client.delete("/api/admin/blocklist/hub/spam.example").status_code == 403
    assert client.delete("/api/admin/blocklist/hub/spam.example", headers={"X-Admin-Token": "s3cret"}).json() == {
        "lifted": True
    }
    assert not blocklist.is_blocked(blocklist.HUB, "spam.example")


def test_the_neighbours_table_shows_calibration_next_to_each_peer(client):
    out = client.get("/api/admin/neighbours").json()
    assert "peers" in out and "blocked_hubs" in out
    for row in out["peers"]:
        assert {"hub", "blocked", "verdict", "why"} <= set(row)


# ---------------------------------------------------------------- found by using it as an admin


def test_a_blocked_entity_disappears_from_an_ordinary_search(client):
    """The block was enforced in the hub façade only, so every normal search still listed it.

    An admin blocks a business, it stays visible, and nobody notices until someone checks. A block
    that does not block is worse than no block, because it is believed.
    """
    visible = hive.discover(query="")["matches"]
    assert visible, "the seed must answer an empty query"
    target_id = visible[0]["id"]

    blocklist.block(blocklist.ENTITY, target_id, "fabricated reviews")

    after = hive.discover(query="")
    assert all(m["id"] != target_id for m in after["matches"])
    assert all(
        m["id"] != target_id for m in after["excluded"]
    ), "a blocked entity is gone, not listed as excluded — being excluded still names it"


def test_refusing_an_application_without_a_reason_is_a_bad_request_not_a_crash(client, monkeypatch):
    """It returned 500. A refusal with no reason is the operator's mistake, and they should be told."""
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    app_id = registration.apply({"entity": {"id": "cafe-test-x", "kind": "cafe", "name": "Test"}})["id"]

    res = client.post(f"/api/admin/applications/{app_id}", json={"admit": False}, headers={"X-Admin-Token": "s3cret"})
    assert res.status_code == 400, "an operator mistake is a 400 with a message, never a 500"
    assert "reason" in res.json()["detail"]
