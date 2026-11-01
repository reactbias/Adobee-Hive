"""An owner's agent can read, propose and publish over MCP, and the token rides the transport.

The three tools mirror `GET /api/owner/{card_id}`, `/propose` and `/publish`. What is checked here is
what the REST tests cannot check: that the credential arrives in a header rather than an argument,
that an edit fails closed without it, that what gets published is signed again and still verifies
against the key pinned in `/.well-known/hive.json`, and that `limits.py` refuses an oversized change
by naming the ceiling and the size rather than saying "invalid".

The MCP calls go through the real Streamable HTTP endpoint — `app` is mounted, headers and all — over
an in-process ASGI transport, so there is no socket and no port to collide with a running demo.
"""

import asyncio
import json

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app import config, guard, hive, limits, owner
from app.main import app
from app.mcp_server import server
from tests.mcp_result import tool_result

TOKEN = "owner-token-for-tests"
CARD = "hotel-gare"
GUEST = "Mara Keller"


def _call(tool: str, args: dict, token: str | None = None) -> dict:
    """Call one MCP tool over Streamable HTTP against the mounted app, with the owner token as a header."""

    async def go():
        headers = {owner.TOKEN_HEADER: token} if token is not None else {}
        async with (
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url="http://hive.test", headers=headers
            ) as http,
            Client(streamable_http_client("http://hive.test/mcp/", http_client=http)) as mcp,
        ):
            return await mcp.call_tool(tool, args)

    return tool_result(asyncio.run(go()))


@pytest.fixture
def hub_with_token(client, monkeypatch):
    """A hub that has an owner token set, which is the only state in which it takes an edit at all."""
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", TOKEN)
    return client


@pytest.fixture
def booked(hub_with_token):
    """A hub with one booking on it, so there is a guest name to show in full or reduce to initials.

    Made through the hub rather than assumed: another file in this session may or may not have left
    a booking on this card, and a test that only passes after one of its neighbours is not a test.
    """
    view = _call("hive_owner_card", {"card_id": "hotel-rheinblick"}, token=TOKEN)
    if GUEST not in [b["guest_name"] for b in view["bookings"]]:
        made = _call(
            "hive_book",
            {
                "card_id": "hotel-rheinblick",
                "unit_id": "single",
                "check_in": "2027-06-01",
                "check_out": "2027-06-02",
                "guest_name": GUEST,
            },
        )
        assert "error" not in made, made
    return hub_with_token


@pytest.fixture
def editable(hub_with_token):
    """The card as it is now, published back as it was once the test is done.

    The suite shares one database, so a card this file changes is a card every later file searches.
    Yields the version the test starts from, which is also what its assertions compare against.
    """
    before = hive.get_card(CARD)
    yield before
    hive.publish({k: v for k, v in before.items() if k != "trust"})


# ---------------------------------------------------------------- the three tools are there


def test_the_three_owner_tools_are_served_and_take_no_token_argument(client):
    async def tools():
        async with Client(server) as mcp:
            return {t.name: t for t in (await mcp.list_tools()).tools}

    served = asyncio.run(tools())
    for name in ("hive_owner_card", "hive_owner_propose", "hive_owner_publish"):
        assert name in served, "the owner tools are the point of this module"
        schema = json.dumps(served[name].input_schema).lower()
        # A credential in the schema is a credential in the transcript. It belongs in a header, nowhere else.
        assert "token" not in schema, f"{name} must not take a credential as an argument"
        assert "ctx" not in schema and "context" not in schema, "the request context is not the agent's business"


# ---------------------------------------------------------------- reading


def test_the_owner_view_reads_without_a_token_and_shows_guest_names_as_initials(booked):
    out = _call("hive_owner_card", {"card_id": "hotel-rheinblick"})
    assert out["card"]["id"] == "hotel-rheinblick"
    assert {"card", "bookings", "handoffs", "missed_demand", "last_7_days", "waiting"} == set(out)
    assert GUEST not in [b["guest_name"] for b in out["bookings"]]
    assert "M. K." in [b["guest_name"] for b in out["bookings"]], "initials, exactly as on the REST route"


def test_the_owner_view_with_the_token_is_the_rest_route_with_the_token(booked):
    named = _call("hive_owner_card", {"card_id": "hotel-rheinblick"}, token=TOKEN)
    rest = booked.get("/api/owner/hotel-rheinblick", headers={owner.TOKEN_HEADER: TOKEN}).json()
    assert GUEST in [b["guest_name"] for b in named["bookings"]], "the whole name, for the owner"
    assert [b["guest_name"] for b in named["bookings"]] == [b["guest_name"] for b in rest["bookings"]]


def test_a_wrong_token_degrades_the_read_rather_than_refusing_it(booked):
    out = _call("hive_owner_card", {"card_id": "hotel-rheinblick"}, token="not the token")
    assert "error" not in out, "reading is not an edit: a bad token masks the names, it does not close the door"
    assert GUEST not in [b["guest_name"] for b in out["bookings"]]


def test_an_unknown_card_is_an_error_an_agent_can_read(client):
    assert "No Hive card" in _call("hive_owner_card", {"card_id": "nope"})["error"]


# ---------------------------------------------------------------- the access decisions


def test_propose_and_publish_fail_closed_without_the_token(editable):
    for tool, args in (
        ("hive_owner_propose", {"card_id": CARD, "instruction": "add ski storage"}),
        ("hive_owner_publish", {"card_id": CARD, "proposed": {**editable, "name": "Taken over"}}),
    ):
        refused = _call(tool, args)
        assert owner.TOKEN_HEADER in refused["error"] and "header" in refused["error"]
    live = hive.get_card(CARD)
    assert live["version"] == editable["version"] and live["name"] == editable["name"]


def test_a_wrong_token_publishes_nothing(editable):
    refused = _call("hive_owner_publish", {"card_id": CARD, "proposed": {**editable, "name": "Taken over"}}, "guess")
    assert owner.TOKEN_HEADER in refused["error"]
    assert hive.get_card(CARD)["version"] == editable["version"]


def test_a_hub_with_no_owner_token_set_refuses_every_edit_rather_than_accepting_any(client, monkeypatch):
    """Fail closed. This is where the MCP write path differs from the REST route, and it says so."""
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "")
    before = hive.get_card(CARD)
    for token in (None, "", "anything at all"):
        refused = _call("hive_owner_propose", {"card_id": CARD, "instruction": "add ski storage"}, token)
        assert "OWNER_EDIT_TOKEN" in refused["error"]
        assert _call("hive_owner_publish", {"card_id": CARD, "proposed": {**before, "name": "Mine"}}, token)["error"]
    live = hive.get_card(CARD)
    assert live["version"] == before["version"] and live["name"] == before["name"]
    # Reading still works with no token at all, so an agent is never locked out of looking.
    assert _call("hive_owner_card", {"card_id": CARD})["card"]["id"] == CARD


def test_an_unclaimed_card_cannot_be_edited_by_the_token_holder_either(hub_with_token):
    unclaimed = next(c["id"] for c in hive.list_cards() if not hive.get_card(c["id"])["trust"]["claimed"])
    refused = _call("hive_owner_propose", {"card_id": unclaimed, "instruction": "add ski storage"}, TOKEN)
    assert "unclaimed" in refused["error"].lower()


def test_no_answer_ever_carries_the_token_back(editable):
    proposed = _call("hive_owner_propose", {"card_id": CARD, "instruction": "add luggage room"}, TOKEN)
    published = _call("hive_owner_publish", {"card_id": CARD, "proposed": proposed["proposed"]}, TOKEN)
    read = _call("hive_owner_card", {"card_id": CARD}, TOKEN)
    for answer in (proposed, published, read):
        assert TOKEN not in json.dumps(answer), "a tool must never echo the credential it was given"


# ---------------------------------------------------------------- propose, then publish


def test_propose_returns_a_diff_and_publishes_nothing(editable):
    assert "ski storage" not in editable["features"]
    out = _call("hive_owner_propose", {"card_id": CARD, "instruction": "add ski storage"}, TOKEN)
    assert out["card_id"] == CARD
    assert {
        "field": "features",
        "before": editable["features"],
        "after": [*editable["features"], "ski storage"],
    } in out["changes"]
    assert out["summary"] and out["proposed"]["features"][-1] == "ski storage"
    live = hive.get_card(CARD)
    assert live["version"] == editable["version"] and "ski storage" not in live["features"]


def test_publish_makes_the_proposed_card_live_as_a_new_version(editable):
    out = _call("hive_owner_propose", {"card_id": CARD, "instruction": "add night porter"}, TOKEN)
    published = _call("hive_owner_publish", {"card_id": CARD, "proposed": out["proposed"]}, TOKEN)
    assert "night porter" in published["features"]
    assert published["version"] == editable["version"] + 1
    assert hive.get_card(CARD)["features"] == published["features"]


def test_the_published_card_is_signed_again_and_verifies_against_the_pinned_key(editable):
    """The worst outcome this feature could have is a published card that no longer verifies."""
    out = _call("hive_owner_propose", {"card_id": CARD, "instruction": "add bike wash"}, TOKEN)
    published = _call("hive_owner_publish", {"card_id": CARD, "proposed": out["proposed"]}, TOKEN)
    pins = hive.owner_keys()
    assert published["trust"]["signature"] != editable["trust"]["signature"], "a new version is signed again"
    assert hive.verify_pinned(published, pins), "the published card must verify against the key this hub pinned"
    # And as the next agent handed it over MCP would check it, against the registry rather than our word.
    fetched = _call("hive_get_card", {"card_id": CARD})
    assert fetched["trust"]["signature"] == published["trust"]["signature"]
    assert hive.verify_pinned(fetched, pins)
    assert not hive.verify_pinned({**published, "features": [*published["features"], "pool"]}, pins)


def test_publish_keeps_the_identity_fields_whatever_the_proposal_says(editable):
    published = _call(
        "hive_owner_publish",
        {"card_id": CARD, "proposed": {**editable, "id": "somebody-else", "slug": "taken", "kind": "person"}},
        TOKEN,
    )
    assert (published["id"], published["slug"], published["kind"]) == (
        editable["id"],
        editable["slug"],
        editable["kind"],
    )
    assert hive.get_record("somebody-else") is None
    assert hive.verify_pinned(published, hive.owner_keys())


# ---------------------------------------------------------------- the published ceilings


def test_a_description_over_its_ceiling_is_refused_with_the_ceiling_and_the_size(editable):
    """The same 24 published ceilings, and a refusal naming a number somebody can act on."""
    over = limits.MAX_DESCRIPTION + 400
    proposed = {k: v for k, v in editable.items() if k != "trust"} | {"description": "a" * over}
    refused = _call("hive_owner_publish", {"card_id": CARD, "proposed": proposed}, TOKEN)
    assert "description" in refused["error"]
    assert str(limits.MAX_DESCRIPTION) in refused["error"] and str(over) in refused["error"]
    assert hive.get_card(CARD)["version"] == editable["version"], "nothing was published"


def test_a_proposal_over_a_ceiling_is_refused_at_propose_not_only_at_publish(editable, monkeypatch):
    """An agent should not show its person a diff that the hub will refuse after they have said yes."""
    over = limits.MAX_DESCRIPTION + 1

    def oversized(card_id, _instruction):
        card = hive.get_card(card_id)
        return {
            "card_id": card_id,
            "proposed": {k: v for k, v in card.items() if k != "trust"} | {"description": "b" * over},
            "changes": [],
            "summary": "",
            "summary_items": None,
            "mode": "mock",
        }

    monkeypatch.setattr(owner, "propose", oversized)
    refused = _call("hive_owner_propose", {"card_id": CARD, "instruction": "a very long description"}, TOKEN)
    assert str(limits.MAX_DESCRIPTION) in refused["error"] and str(over) in refused["error"]
    assert "propose again" in refused["error"], "a refusal says what to do next"


def test_a_long_description_inside_the_ceiling_is_published_and_never_judged(editable):
    """`description` is the card's pitch to an agent. Only its size may refuse it, never its content."""
    pitch = ("Rooms an agent can book, by the station, for people who arrive late. " * 29).strip()
    assert limits.MAX_DESCRIPTION - 100 < len(pitch) <= limits.MAX_DESCRIPTION
    proposed = {k: v for k, v in editable.items() if k != "trust"} | {"description": pitch}
    published = _call("hive_owner_publish", {"card_id": CARD, "proposed": proposed}, TOKEN)
    assert published["description"] == pitch
    assert hive.verify_pinned(published, hive.owner_keys())


# ---------------------------------------------------------------- the budget, and the transport


def test_a_proposal_counts_against_the_model_budget(editable, monkeypatch):
    monkeypatch.setattr(guard, "llm_calls", guard.RateLimiter(per_client=1, total=10))
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    assert "error" not in _call("hive_owner_propose", {"card_id": CARD, "instruction": "add ski storage"}, TOKEN)
    again = _call("hive_owner_propose", {"card_id": CARD, "instruction": "add night porter"}, TOKEN)
    assert "Try again in" in again["error"]


def test_a_transport_that_carries_no_headers_cannot_edit(hub_with_token):
    """An in-process or stdio client has no headers at all, so it falls on the closed side. By design."""

    async def go():
        async with Client(server) as mcp:
            return await mcp.call_tool("hive_owner_publish", {"card_id": CARD, "proposed": {"id": CARD}})

    out = tool_result(asyncio.run(go()))
    assert owner.TOKEN_HEADER in out["error"]
