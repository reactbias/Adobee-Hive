"""Demand that waits: an agent leaves a standing request, the owner changes the card, the agent gets a signed offer."""

import asyncio
from datetime import date, timedelta

from mcp import Client

from app import db, hive, simulate, waiting
from app.mcp_server import server
from tests.mcp_result import tool_result

ARRIVE = (date.today() + timedelta(days=20)).isoformat()
LEAVE = (date.today() + timedelta(days=22)).isoformat()
ASK = {"features": ["rooftop pool"], "near": "basel sbb", "max_price_chf": 300, "check_in": ARRIVE, "check_out": LEAVE}


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return tool_result(await c.call_tool(tool, args))

    return asyncio.run(go())


def _add_feature(client, card_id: str, feature: str) -> None:
    card = client.get(f"/api/hive/cards/{card_id}").json()
    proposed = {**card, "features": [*card["features"], feature]}
    assert client.post(f"/api/owner/{card_id}/publish", json={"proposed": proposed}).status_code == 200


def test_waiting_agent_gets_a_signed_offer_when_the_card_changes(client):
    ticket = _mcp("hive_wait", {**ASK, "guests": 2})
    assert ticket["request_id"].startswith("wr_") and ticket["token"]
    assert _mcp("hive_check_waiting", ticket | {"token": ticket["token"]})["status"] == "waiting"

    waits = client.get("/api/owner/hotel-gare").json()["waiting"]
    assert {"missing": ["rooftop pool"], "cheaper": False, "agents": 1, "budget_chf": 600} in waits["asks"]

    _add_feature(client, "hotel-gare", "rooftop pool")
    out = _mcp("hive_check_waiting", {"request_id": ticket["request_id"], "token": ticket["token"]})
    assert out["status"] == "offered"
    [offer] = out["offers"]
    assert offer["business"] == "Gare Central Basel" and offer["unit_id"] == "std" and offer["total_chf"] == 378
    pins = client.get("/.well-known/hive.json").json()["owner_keys"]
    assert hive.verify_statement(offer["offer"], pins["hotel-gare"])  # signed by the owner's pinned key
    assert not hive.verify_statement(offer["offer"], pins["hotel-rheinblick"])

    after = client.get("/api/owner/hotel-gare").json()["waiting"]
    assert after["offers_sent"] >= 1 and all(a["missing"] != ["rooftop pool"] for a in after["asks"])
    _add_feature(client, "hotel-gare", "rooftop bar")  # another edit: still one offer per business
    assert len(waiting.check(ticket["request_id"], ticket["token"])["offers"]) == 1


def test_only_the_token_holder_can_read_a_request(client):
    ticket = waiting.leave(**{**ASK, "features": ["helipad"]})
    assert "error" in _mcp("hive_check_waiting", {"request_id": ticket["request_id"], "token": "guess"})
    with db.cursor() as cur:
        stored = cur.execute("SELECT * FROM hive_waiting WHERE id = ?", [ticket["request_id"]]).fetchone()
    assert ticket["token"] not in " ".join(map(str, stored))  # only its hash is kept


def test_waiting_is_refused_when_a_business_already_fits(client):
    out = _mcp("hive_wait", {"features": ["dog-friendly"], "check_in": ARRIVE, "check_out": LEAVE})
    assert "Book instead" in out["error"]
    assert "error" in _mcp("hive_wait", {"check_in": ARRIVE, "check_out": LEAVE})  # nothing to wait for
    assert "error" in _mcp("hive_wait", {"features": ["helipad"], "check_in": "2020-01-01", "check_out": "2020-01-02"})


def test_simulated_travellers_leave_standing_requests(client):
    simulate.run(40, seed=7)
    assert client.get("/api/owner/hotel-gare").json()["waiting"]["agents"] > 0
