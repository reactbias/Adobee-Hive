"""The challenge's core mechanism: an agent discovers and books a Basel hotel over MCP."""

import asyncio
import json

import httpx
import openai
import pytest
from mcp import Client

from app import agent, config, connections, db, guard, hive, hub, llm, owner, second_opinion, sharing, simulate
from app.domains import examples, hr
from app.mcp_server import server

REQUEST = (
    "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, "
    "2026-11-13 to 2026-11-15, my name is Mara Keller"
)


def test_agent_books_end_to_end_over_mcp(client):
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert [s["tool"] for s in out["steps"]] == ["hive_discover", "hive_get_card", "hive_check_availability"]
    assert out["pending"]["tool"] == "hive_book"  # nothing is booked until the traveller approves
    assert out["second_opinion"]["verdict"] == "agree" and out["second_opinion"]["by"] == "Rule check"
    # Three agents agree before the traveller is asked: the booking agent, the critic and the verifier.
    assert out["critic"]["verdict"] == "agree" and out["critic"]["challenge"]
    assert out["consensus"] is True

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
    pins = client.get("/.well-known/hive.json").json()["owner_keys"]
    assert agent.verify_card(card, pins)
    card["units"][0]["price_chf"] = 1
    assert not agent.verify_card(card, pins)


def test_card_re_signed_by_a_stranger_is_rejected(client):
    forged = client.post("/api/hive/demo/forge/hotel-rheinblick").json()
    assert forged["units"][0]["price_chf"] == 1
    # The signature is valid for the stranger's key, so only the pinned key catches it.
    data = {k: v for k, v in forged.items() if k != "trust"}
    assert hive.verify(data, forged["trust"]["signature"], forged["trust"]["public_key"])
    assert client.post("/api/hive/verify", json={"card": forged}).json() == {"signature_valid": False}
    original = client.get("/api/hive/cards/rheinblick").json()
    assert client.post("/api/hive/verify", json={"card": original}).json() == {"signature_valid": True}


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
    assert client.post("/api/demo/reset").json()["cards"] == 6 + len(examples.CARDS)
    card = client.get("/api/hive/cards/hotel-gare").json()
    assert "dog-friendly" not in card["features"] and card["version"] == 1
    assert card["trust"]["signature_valid"]


def test_agent_falls_back_offline_when_claude_fails(client, monkeypatch):
    import anthropic
    import httpx

    async def broken(*_args, **_kwargs):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    monkeypatch.setattr(agent.config, "LLM_PROVIDER", "claude")
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
    monkeypatch.setattr(agent, "run", lambda _messages, *_options: asyncio.sleep(0, {"reply": "ok"}))
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


def test_hr_domain_finds_people_by_skill_and_asks_for_consent(client):
    hive.publish(dict(hr.EXAMPLE_CARD))
    found = hr.find_people(["Figma", "user research", "rust"])
    mira = found["matches"][0]
    assert mira["matched"] == ["figma", "user research"] and mira["signature_valid"]
    assert "contact" not in mira and "email" not in json.dumps(found)
    intro = hr.request_intro("person-mira", "Fictional Hotel Group", "We'd like to talk about agent-facing design.")
    assert intro["status"] == "pending_consent"
    assert "intro_request" in client.get("/api/owner/person-mira").json()["last_7_days"]


def test_hr_tools_are_on_the_same_mcp_server(client):
    async def tools():
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert {"hr_find_people", "hr_request_intro", "hive_discover"} <= asyncio.run(tools())


def test_second_opinion_flags_a_missing_feature():
    card = {"name": "Gare Central", "trust": {"signature_valid": True}, "features": ["late check-in"], "units": []}
    request = {"features": ["dog-friendly", "late check-in"], "max_price_chf": None}
    assert second_opinion.rule_check(request, {"unit_id": "x"}, card)["verdict"] == "concern"
    assert second_opinion.rule_check(request, {}, None)["verdict"] == "concern"


def test_second_opinion_falls_back_when_openai_fails(client, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))

    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(second_opinion, "_ask_openai", broken)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert out["second_opinion"]["by"] == "Rule check" and out["second_opinion"]["fallback"] == "OpenAI unavailable"


@pytest.mark.parametrize(
    "text",
    [
        "Buche mir ein ruhiges, hundefreundliches Hotel nahe Basel SBB unter CHF 200 mit später Anreise, "
        "13.11.2026 bis 15.11.2026. Mein Name ist Mara Keller.",
        "Réserve-moi un hôtel calme, accueillant les chiens, près de Basel SBB, à moins de CHF 200, arrivée tardive, "
        "du 13.11.2026 au 15.11.2026. Je m'appelle Mara Keller.",
        "Prenotami un hotel tranquillo, che accetti cani, vicino a Basel SBB, sotto CHF 200, con arrivo tardivo, "
        "dal 13.11.2026 al 15.11.2026. Mi chiamo Mara Keller.",
    ],
)
def test_offline_planner_reads_localized_requests(text):
    req = agent.parse_request(text)
    assert req["features"] == ["dog-friendly", "late check-in", "quiet"]
    assert (req["check_in"], req["check_out"]) == ("2026-11-13", "2026-11-15")
    assert req["max_price_chf"] == 200 and req["near"] == "basel sbb"
    assert req["guest_name"] == "Mara Keller" and req["wants_booking"]


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


def test_agent_falls_back_offline_when_openai_fails(client, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))

    monkeypatch.setattr(agent.config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(agent, "_run_openai", broken)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert out["mode"] == "scripted" and out["fallback"] == "OpenAI unavailable"
    assert out["pending"]["tool"] == "hive_book"


def test_owner_edit_falls_back_to_rules_when_the_model_fails(monkeypatch):
    def broken(*_args, **_kwargs):
        raise llm.LLMError("no answer")

    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(llm, "structured", broken)
    out = owner.propose("hotel-gare", "add sauna")
    assert out["mode"] == "mock" and any(c["field"] == "features" for c in out["changes"])


def test_openai_agent_loop_holds_the_booking(client, monkeypatch):
    """A scripted stand-in for the OpenAI Responses API drives the real tool loop over MCP."""
    from types import SimpleNamespace as NS

    def call(name, args):
        return NS(type="function_call", name=name, call_id=name, arguments=json.dumps(args))

    dates = {"check_in": "2026-11-13", "check_out": "2026-11-15"}
    turns = iter(
        [
            [call("hive_discover", {"kind": "hotel", "features": ["dog-friendly"], "near": "basel sbb"} | dates)],
            [call("hive_get_card", {"card_id": "hotel-rheinblick"})],
            [call("hive_book", {"card_id": "hotel-rheinblick", "unit_id": "double", "guest_name": "Mara"} | dates)],
            [NS(type="message")],
        ]
    )
    seen = []

    class FakeResponses:
        async def create(self, **kwargs):
            seen.append(kwargs)
            output = next(turns)
            return NS(output=output, output_text="Ready to book Hotel Rheinblick.")

    monkeypatch.setattr(agent.config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(agent.openai, "AsyncOpenAI", lambda **_: NS(responses=FakeResponses()))
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert out["mode"] == "openai" and out["reply"] == "Ready to book Hotel Rheinblick."
    assert [s["tool"] for s in out["steps"]] == ["hive_discover", "hive_get_card"]  # hive_book was held, not sent
    assert out["pending"]["input"]["card_id"] == "hotel-rheinblick"
    assert all(k["store"] is False for k in seen)


def test_search_logs_never_store_the_travellers_words(client):
    ask = "Book a dog-friendly hotel near Basel SBB for Anna Secret, 2026-11-13 to 2026-11-15"
    client.post("/api/agent", json={"messages": [{"role": "user", "content": ask}]})
    with db.cursor() as cur:
        details = [r[0] for r in cur.execute("SELECT detail FROM hive_events").fetchall()]
    assert details and not any("Anna" in d or "Secret" in d for d in details)


def test_owner_overview_masks_guest_names_without_the_token(client, monkeypatch):
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "s3cret")
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    client.post("/api/agent/approve", json={"pending": out["pending"]})
    url = "/api/owner/hotel-rheinblick"
    assert client.get(url).json()["bookings"][0]["guest_name"] == "M. K."
    assert client.get(url, headers={"X-Owner-Token": "s3cret"}).json()["bookings"][0]["guest_name"] == "Mara Keller"


def test_a_held_booking_is_approved_once_and_as_held(client):
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    pending = out["pending"] | {"input": out["pending"]["input"] | {"unit_id": "river", "guest_name": "Mallory"}}
    done = client.post("/api/agent/approve", json={"pending": pending}).json()
    assert done["booking"]["unit_name"] != "River-view double"  # what the agent held, not what the client sent
    again = client.post("/api/agent/approve", json={"pending": out["pending"]})
    assert again.status_code == 400 and "already approved" in again.json()["detail"]


def test_approval_refuses_a_source_that_was_removed_instead_of_retargeting(client, monkeypatch):
    """A held action belongs to the Hive that proposed it, not whichever one is configured at approval."""
    ask = "Book a quiet dog-friendly hotel under CHF 200, 2027-02-10 to 2027-02-12. " "My name is Fictional Guest."
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": ask}]}).json()
    pending = out["pending"]
    assert pending is not None
    monkeypatch.setattr(config, "HIVE_MCP_URLS", ["http://127.0.0.1:1/mcp/"])

    changed = pending | {"source": "http://127.0.0.1:1/mcp/", "input": pending["input"] | {"_source": "other"}}
    response = client.post("/api/agent/approve", json={"pending": changed})

    assert response.status_code == 400
    assert "no longer configured" in response.json()["detail"]
    with db.cursor() as cur:
        assert (
            cur.execute("SELECT count(*) FROM hive_bookings WHERE guest_name = ?", ["Fictional Guest"]).fetchone()[0]
            == 0
        )


def test_rule_edit_keeps_the_pets_policy_in_line():
    card = {"features": ["wifi"], "policies": {"pets": "No pets"}}
    added, _ = owner.mock_edit(card, "add dog-friendly")
    assert "dog-friendly" in added["features"] and added["policies"]["pets"] == "Dogs welcome"
    removed, _ = owner.mock_edit(added, "remove dog-friendly")
    assert removed["policies"]["pets"] == "No pets"


def test_discovery_lists_a_person_and_still_guards_their_contact(client):
    """The reverse of the old rule, on purpose: a hub whose developers are invisible is not a hub.

    People used to be hidden from discovery (NOT_DISCOVERABLE), which also hid every developer,
    hairdresser and consultant on the hub. `offers` and `needs` are the index now and `kind` is
    only a filter, so a person is found like anyone else. What hiding them used to buy, and what
    this test keeps: their contact is not handed out, reaching them waits for their yes, and no
    `missed_demand` row is written against a person — demand is a market signal a business asked
    for; against a person it would be a record of the times they were passed over.
    """
    hive.publish(dict(hr.EXAMPLE_CARD))
    found = hive.discover(query="product design prototyping", kind="person")
    mira = next(m for m in found["matches"] if m["id"] == "person-mira")
    assert mira["signature_valid"] and mira["bookable"] is False

    # Consent, unchanged: a person card carries no contact details at all (domains/hr.py), the
    # result cannot invent any, and an introduction has to be asked for and waits for the person.
    # The contact block exists — every entity carries one so nothing downstream has to guard a
    # lookup — but it holds no values. An empty string reads as "not published", which is the
    # guarantee and the guard at once: the keys are predictable, the person's details are not here.
    assert all(not v for v in mira["contact"].values()), f"a person's details leaked: {mira['contact']}"
    assert all(not v for v in (hive.get_card("person-mira").get("contact") or {}).values())
    assert sharing.resolve(hive.get_card("person-mira").get("sharing"), None) == sharing.CONFIRM
    assert hub.connect("acme", "person-mira")["state"] == connections.REQUESTED  # not open, asked
    assert hr.request_intro("person-mira", "Acme", "Can we talk?")["status"] == "pending_consent"

    # And nothing is logged against them when they do not fit: no missed_demand for a person.
    turned_away = hive.discover(features=["dog-friendly"])
    assert any(e["id"] == "person-mira" for e in turned_away["excluded"]), "said so in the open"
    assert not any(m["detail"] for m in client.get("/api/owner/person-mira").json()["missed_demand"])


def test_agent_falls_back_offline_when_the_model_hangs(client, monkeypatch):
    async def slow(*_args, **_kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(agent.config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(agent.config, "AGENT_TIMEOUT_S", 0.2)
    monkeypatch.setattr(agent, "_run_openai", slow)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert out["mode"] == "scripted" and out["fallback"] == "OpenAI unavailable"


def test_agent_falls_back_offline_when_the_model_returns_garbage(client, monkeypatch):
    async def garbage(*_args, **_kwargs):
        raise json.JSONDecodeError("bad", "", 0)

    monkeypatch.setattr(agent.config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(agent, "_run_openai", garbage)
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    assert out["mode"] == "scripted" and out["fallback"] == "OpenAI unavailable"
