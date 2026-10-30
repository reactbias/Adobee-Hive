"""The challenge's core mechanism: an agent discovers and books a Basel hotel over MCP."""

import asyncio

from mcp import Client

from app import agent, hive, simulate
from app.mcp_server import server

REQUEST = ("Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, "
           "2026-11-13 to 2026-11-15, my name is Tobi Muster")


def test_agent_books_end_to_end_over_mcp(client):
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert [s["tool"] for s in out["steps"]] == ["hive_discover", "hive_get_card", "hive_check_availability"]
    assert out["pending"]["tool"] == "hive_book"  # nothing is booked until the traveller approves

    done = client.post("/api/agent/approve", json={"pending": out["pending"]}).json()
    assert [s["tool"] for s in done["steps"]] == ["hive_book"]
    booking = done["booking"]
    assert booking["status"] == "confirmed"
    assert booking["business"] == "Hotel Rheinblick"
    assert booking["total_chf"] <= 2 * 200


def test_agent_only_approves_bookings(client):
    assert client.post("/api/agent/approve", json={"pending": {"tool": "hive_cancel", "input": {}}}).status_code == 400


def test_agent_compares_without_booking_when_told(client):
    ask = "Two of us near Messe Basel, parking, 3 nights from 2027-06-14. Just compare, don't book."
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": ask}]}).json()
    assert out["pending"] is None


def test_discover_explains_exclusions(client):
    found = hive.discover(features=["dog-friendly"], max_price_chf=200, check_in="2026-12-01", check_out="2026-12-03")
    excluded = {e["id"]: e["why_not"] for e in found["excluded"]}
    assert "missing dog-friendly" in excluded["hotel-muenster"][0]
    assert all(m["signature_valid"] for m in found["matches"])
    missed = client.get("/api/owner/hotel-muenster").json()["missed_demand"]
    assert any("dog-friendly" in m["detail"] for m in missed)


def test_tampered_card_fails_verification(client):
    card = client.get("/api/hive/cards/rheinblick").json()
    assert agent.verify_card(card)
    card["units"][0]["price_chf"] = 1
    assert not agent.verify_card(card)


def test_reviews_need_a_real_receipt(client):
    booking = client.post("/api/hive/cards/hotel-dreirosen/book", json={
        "unit_id": "dorm", "check_in": "2026-11-20", "check_out": "2026-11-21", "guest_name": "Test Guest"}).json()
    receipt = booking["receipt"]
    assert client.post("/api/hive/reviews", json={"receipt": receipt, "rating": 4, "text": "ok"}).status_code == 200
    assert client.post("/api/hive/reviews", json={"receipt": receipt, "rating": 5, "text": "again"}).status_code == 400
    forged = receipt[:-6] + "AAAAAA"
    assert client.post("/api/hive/reviews", json={"receipt": forged, "rating": 5, "text": "fake"}).status_code == 400


def test_sold_out_rooms_are_not_bookable(client):
    for _ in range(2):  # Muensterhof has 2 suites
        r = client.post("/api/hive/cards/hotel-muenster/book", json={
            "unit_id": "suite", "check_in": "2027-01-10", "check_out": "2027-01-12", "guest_name": "A"})
        assert r.status_code == 200
    r = client.post("/api/hive/cards/hotel-muenster/book", json={
        "unit_id": "suite", "check_in": "2027-01-11", "check_out": "2027-01-13", "guest_name": "B"})
    assert r.status_code == 400


def test_owner_edit_is_diffed_then_signed(client):
    proposal = client.post("/api/owner/hotel-gare/propose", json={"instruction": "add sauna"}).json()
    assert proposal["changes"][0]["field"] == "features"
    before = client.get("/api/hive/cards/hotel-gare").json()["version"]
    published = client.post("/api/owner/hotel-gare/publish", json={"proposed": proposal["proposed"]}).json()
    assert published["version"] == before + 1
    assert "sauna" in published["features"]
    assert published["trust"]["signature_valid"]


def test_mcp_lists_the_hive_tools(client):
    async def tools():
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert {"hive_discover", "hive_get_card", "hive_book", "hive_review"} <= asyncio.run(tools())


def test_verify_endpoint_catches_tampering(client):
    card = client.get("/api/hive/cards/rheinblick").json()
    assert client.post("/api/hive/verify", json={"card": card}).json()["signature_valid"]
    card["features"].append("pool")
    assert not client.post("/api/hive/verify", json={"card": card}).json()["signature_valid"]


def test_demand_map_counts_unserved_requests(client):
    assert client.post("/api/demo/simulate?n=5").status_code == 200
    out = simulate.run(60, seed=1)
    assert out["searches"] >= 65
    pool = next(f for f in out["features"] if f["feature"] == "pool")
    assert pool["unserved"] == pool["asked"]  # no seeded business has a pool
