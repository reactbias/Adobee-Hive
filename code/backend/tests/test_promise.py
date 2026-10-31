"""The receipt remembers the promise: a booking pins the card version it was made against."""

import asyncio

from mcp import Client

from app import hive
from app.mcp_server import server


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return (await c.call_tool(tool, args)).structured_content

    return asyncio.run(go())


def test_receipt_proves_what_the_card_said_at_booking(client):
    before = hive.get_card("hotel-muenster")
    unit = before["units"][0]
    booking = hive.book("hotel-muenster", unit["id"], "2027-04-05", "2027-04-07", "Test Guest", agent="test agent")
    assert booking["card_version"] == before["version"]
    assert booking["card_digest"] == hive.card_digest(before)

    changed = {k: v for k, v in before.items() if k != "trust"}
    changed["units"] = [{**u, "price_chf": u["price_chf"] + 50} for u in changed["units"]]
    changed["policies"] = {**changed["policies"], "cancellation": "No refunds"}
    assert client.post("/api/owner/hotel-muenster/publish", json={"proposed": changed}).status_code == 200

    out = _mcp("hive_what_was_promised", {"receipt": booking["receipt"]})
    promised = out["card"]
    assert promised["version"] == before["version"] and promised["units"][0]["price_chf"] == unit["price_chf"]
    assert out["digest_matches"] is True
    assert {"units", "policies"} <= set(out["changed_since"])
    pins = client.get("/.well-known/hive.json").json()["owner_keys"]
    assert hive.verify_pinned(promised, pins)  # the old version still carries the owner's signature


def test_a_forged_receipt_proves_nothing(client):
    card = hive.get_card("hotel-dreirosen")
    booking = hive.book("hotel-dreirosen", card["units"][0]["id"], "2027-04-05", "2027-04-06", "Test Guest")
    body, sig = booking["receipt"].split(".")
    assert "error" in _mcp("hive_what_was_promised", {"receipt": body + "." + sig[::-1]})
