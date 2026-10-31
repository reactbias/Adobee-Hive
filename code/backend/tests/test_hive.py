"""The challenge's core mechanism: an agent discovers and books a Basel hotel over MCP."""

import asyncio

import pytest
from mcp import Client

from app import agent, config, guard, hive, simulate
from app.mcp_server import server

REQUEST = (
    "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, "
    "2026-11-13 to 2026-11-15, my name is Tobi Muster"
)


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
    booking = client.post(
        "/api/hive/cards/hotel-dreirosen/book",
        json={"unit_id": "dorm", "check_in": "2026-11-20", "check_out": "2026-11-21", "guest_name": "Test Guest"},
    ).json()
    receipt = booking["receipt"]
    assert client.post("/api/hive/reviews", json={"receipt": receipt, "rating": 4, "text": "ok"}).status_code == 200
    assert client.post("/api/hive/reviews", json={"receipt": receipt, "rating": 5, "text": "again"}).status_code == 400
    forged = receipt[:-6] + "AAAAAA"
    assert client.post("/api/hive/reviews", json={"receipt": forged, "rating": 5, "text": "fake"}).status_code == 400


def test_sold_out_rooms_are_not_bookable(client):
    for _ in range(2):  # Muensterhof has 2 suites
        r = client.post(
            "/api/hive/cards/hotel-muenster/book",
            json={"unit_id": "suite", "check_in": "2027-01-10", "check_out": "2027-01-12", "guest_name": "A"},
        )
        assert r.status_code == 200
    r = client.post(
        "/api/hive/cards/hotel-muenster/book",
        json={"unit_id": "suite", "check_in": "2027-01-11", "check_out": "2027-01-13", "guest_name": "B"},
    )
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


def test_demo_reset_restores_the_seed(client):
    client.post(
        "/api/owner/hotel-gare/publish",
        json={"proposed": {**client.get("/api/hive/cards/hotel-gare").json(), "features": ["dog-friendly"]}},
    )
    assert client.post("/api/demo/reset").json()["cards"] == 6
    card = client.get("/api/hive/cards/hotel-gare").json()
    assert "dog-friendly" not in card["features"] and card["version"] == 1
    assert card["trust"]["signature_valid"]


def test_agent_falls_back_offline_when_claude_fails(client, monkeypatch):
    import anthropic
    import httpx

    async def broken(*_args, **_kwargs):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    monkeypatch.setattr(agent.config, "LLM_ENABLED", True)
    monkeypatch.setattr(agent, "_run_claude", broken)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert out["mode"] == "scripted" and out["fallback"] == "Claude unavailable"  # the UI must not claim Claude ran
    assert out["pending"]["tool"] == "hive_book"


def test_owner_edits_need_the_owner_token_when_set(client, monkeypatch):
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "s3cret")
    url = "/api/owner/hotel-gare/propose"
    assert client.post(url, json={"instruction": "add sauna"}).status_code == 403
    ok = client.post(url, json={"instruction": "add sauna"}, headers={"X-Owner-Token": "s3cret"})
    assert ok.status_code == 200


def test_claude_calls_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(guard, "llm_calls", guard.RateLimiter(per_client=1, total=10))
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(agent, "run", lambda _messages: asyncio.sleep(0, {"reply": "ok"}))
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/api/agent", json=body).status_code == 200
    assert client.post("/api/agent", json=body).status_code == 429


def test_bad_input_is_a_clear_400_not_a_crash(client):
    book = "/api/hive/cards/hotel-rheinblick/book"
    bad_date = {"unit_id": "single", "check_in": "13.11.2026", "check_out": "2026-11-15", "guest_name": "A"}
    assert client.post(book, json=bad_date).status_code == 400
    too_long = {**bad_date, "check_in": "2026-11-01", "check_out": "2027-01-01"}
    assert client.post(book, json=too_long).status_code == 400
    oversized = {"messages": [{"role": "user", "content": "x" * 5000}]}
    assert client.post("/api/agent", json=oversized).status_code == 422


@pytest.mark.parametrize(
    "text",
    [
        "Buche mir ein ruhiges, hundefreundliches Hotel nahe Basel SBB unter CHF 200 mit später Anreise, "
        "13.11.2026 bis 15.11.2026. Mein Name ist Tobi Muster.",
        "Réserve-moi un hôtel calme, accueillant les chiens, près de Basel SBB, à moins de CHF 200, arrivée tardive, "
        "du 13.11.2026 au 15.11.2026. Je m'appelle Tobi Muster.",
        "Prenotami un hotel tranquillo, che accetti cani, vicino a Basel SBB, sotto CHF 200, con arrivo tardivo, "
        "dal 13.11.2026 al 15.11.2026. Mi chiamo Tobi Muster.",
    ],
)
def test_offline_planner_reads_localized_requests(text):
    req = agent.parse_request(text)
    assert req["features"] == ["dog-friendly", "late check-in", "quiet"]
    assert (req["check_in"], req["check_out"]) == ("2026-11-13", "2026-11-15")
    assert req["max_price_chf"] == 200 and req["near"] == "basel sbb"
    assert req["guest_name"] == "Tobi Muster" and req["wants_booking"]


@pytest.mark.parametrize(
    "text",
    [
        "Zu zweit zur Art Basel, nahe Messe Basel, mit Parkplatz, 3 Nächte ab 14.06.2027. "
        "Nur vergleichen, nicht buchen.",
        "À deux pour Art Basel, près de Messe Basel, avec parking, 3 nuits dès le 14.06.2027. Compare seulement, "
        "ne réserve pas.",
        "In due per Art Basel, vicino a Messe Basel, con parcheggio, 3 notti dal 14.06.2027. Solo confrontare, "
        "non prenotare.",
    ],
)
def test_offline_planner_respects_localized_dont_book(text):
    req = agent.parse_request(text)
    assert not req["wants_booking"] and req["guests"] == 2
    assert (req["check_in"], req["check_out"]) == ("2027-06-14", "2027-06-17")
