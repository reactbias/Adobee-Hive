"""The hub you are standing on knows something about itself (#156).

From a user test: `GET /api/hub/directory` listed three hubs usefully — name, description, admission,
accepting, entity counts — except the home row, which had `url: ""`, `apply_at: "/api/hub/register"`
(relative), and `last_asked`/`last_asked_ok` null with nothing to say why. An agent copying the rows
to a person could give a working address and an apply link for zurich and bern and not for the hub it
was actually talking to. The MCP `initialize` instructions said the Hive was a directory of cards
"for Basel" whatever hub was answering, while that hub described itself as stays and places to eat
and the federation carried developers and Bern trades. And `verdict: "unproven", evidence: 0,
min_evidence: 3` was shown with nothing saying what a reader should do with it.

None of it is a security hole. It is the first thing anyone sees, and a hub that knows nothing about
itself reads as broken.

No new route: `/api/hub/directory` already serves the standing figures (`error`, `evidence`,
`verdict`, `why` per row), so this adds the address the row was missing rather than an endpoint.
`/api/hub/standing` stays as it is — it has no caller in the frontend and is not this issue's.
"""

from __future__ import annotations

import asyncio

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app import admin, calibration, config
from app.main import app
from app.mcp_server import server


def _over_mcp(host: str, headers: dict[str, str] | None = None) -> dict:
    """Call hub_directory over Streamable HTTP, so the tool really reads the request's own headers."""

    async def go():
        async with (
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url=f"http://{host}", headers=headers or {}
            ) as http,
            Client(streamable_http_client(f"http://{host}/mcp/", http_client=http)) as mcp,
        ):
            return (await mcp.call_tool("hub_directory", {})).structured_content

    return asyncio.run(go())


def _rows(payload: dict) -> dict[str, dict]:
    return {row["hub"]: row for row in payload["hubs"]}


def _home(payload: dict) -> dict:
    return next(row for row in payload["hubs"] if row["home"])


# ---------------------------------------------------------------- an address a person can use


def test_the_home_row_carries_the_address_the_request_arrived_on(client):
    """A process does not know what name a client used to reach it, so the request is the source."""
    payload = client.get("/api/hub/directory").json()
    home = _home(payload)

    assert home["url"], "the home row had no address at all"
    assert home["url"].startswith("http://"), home["url"]
    assert not home["url"].endswith("/"), "no trailing slash, so joining a path cannot double it"


def test_the_apply_link_is_absolute_so_it_can_be_passed_on(client):
    home = _home(client.get("/api/hub/directory").json())

    assert home["apply_at"] == f"{home['url']}/api/hub/register"
    assert home["apply_at"].startswith("http"), "a relative link is useless to an agent quoting it"


def test_a_configured_public_url_wins_over_the_request(client, monkeypatch):
    """Behind a proxy the address a client used is not the one this process sees."""
    monkeypatch.setattr(config, "HIVE_PUBLIC_URL", "https://hive.example")

    home = _home(client.get("/api/hub/directory").json())

    assert home["url"] == "https://hive.example"
    assert home["apply_at"] == "https://hive.example/api/hub/register"


def test_with_no_address_at_all_it_stays_empty_rather_than_guessing(client, monkeypatch):
    """A hub called with no base URL and nothing configured says nothing instead of inventing a host."""
    monkeypatch.setattr(config, "HIVE_PUBLIC_URL", "")

    home = _home(admin.directory())

    assert home["url"] == ""
    assert home["apply_at"] == "/api/hub/register", "the old relative value, as the honest fallback"


def test_every_row_has_an_absolute_url_or_an_honest_empty_one(client):
    """The acceptance criterion as the tester wrote it: an absolute URL for every hub."""
    for hub, row in _rows(client.get("/api/hub/directory").json()).items():
        assert row["url"] == "" or row["url"].startswith("http"), f"{hub} has a URL nobody can use"
        assert row["apply_at"] == "" or row["apply_at"].startswith(("http", "/")), hub


# ---------------------------------------------------------------- and says why its own nulls are null


def test_the_home_row_explains_its_nulls_instead_of_looking_broken(client):
    """`last_asked: null` is correct and unreadable. Claiming a time would be a lie, so it says why."""
    home = _home(client.get("/api/hub/directory").json())

    assert home["last_asked"] is None and home["last_asked_ok"] is None
    assert "answers for itself" in home["why_not_asked"]
    assert home["stale"] is False
    assert home["known"] is True, "a peer row carries `known`; the home row was missing it entirely"


def test_a_verdict_comes_with_what_it_means(client):
    """`unproven` with a count and nothing else reads as a warning. It is not one."""
    payload = client.get("/api/hub/directory").json()

    assert payload["min_evidence"] == calibration.MIN_EVIDENCE
    meanings = payload["verdict_meanings"]
    assert "no evidence either way" in meanings["unproven"]
    for row in payload["hubs"]:
        assert row["verdict"] in meanings, f"{row['hub']} has a verdict nothing explains"
        assert row["why"], "and every row says it for that hub's own count"


def test_the_meanings_cover_every_verdict_calibration_can_produce(client):
    """A new verdict in calibration.py must show up as a missing key, not as a wrong sentence."""
    produced = set()
    for rows in ([], [{"published_rating": 40, "rating": 40, "rated_at": None}] * calibration.MIN_EVIDENCE):
        produced.add(calibration.score("probe", list(rows))["verdict"])
    produced |= {"over-promises", "under-promises"}

    assert produced <= set(admin.VERDICT_MEANINGS)


# ---------------------------------------------------------------- the MCP intro describes this hub


def test_the_mcp_instructions_name_this_hub_rather_than_basel(client):
    """Three hubs ran the same binary and all three introduced themselves as the Basel directory."""
    assert server.instructions is not None
    intro = server.instructions

    assert "for Basel. " not in intro, "the hard-coded city is what the tester hit"
    assert config.HIVE_HUB_ID in intro
    assert config.HIVE_DESCRIPTION in intro, "a hub describes itself in its own words"


def test_the_mcp_instructions_say_the_federation_exists_and_how_to_reach_it(client):
    """ "Expected: instructions that mention the federation." An agent that does not know a peer
    exists reports "nothing in Basel" for something one hop away."""
    intro = server.instructions or ""

    assert "federation" in intro
    assert "radius" in intro and "hub_directory" in intro
    assert "not the whole Hive" in intro


def test_hub_directory_over_mcp_gives_an_absolute_home_url_too(client):
    """The MCP surface has no Request, so the address comes from the headers the call arrived on."""

    home = _home(_over_mcp("hive.test:8470"))

    assert home["url"] == "http://hive.test:8470"
    assert home["apply_at"] == "http://hive.test:8470/api/hub/register"


def test_a_forwarded_scheme_is_honoured_rather_than_assumed(client):
    """`http` is the fallback, not a claim: a proxy that says https is believed about its own leg."""

    home = _home(_over_mcp("hive.example", {"x-forwarded-proto": "https"}))

    assert home["url"] == "https://hive.example"


def test_no_address_anywhere_leaves_the_row_honestly_empty(client, monkeypatch):
    """Nothing to go on is nothing to go on: no hostname is ever invented."""
    monkeypatch.setattr(config, "HIVE_PUBLIC_URL", "")

    home = _home(admin.directory(""))

    assert home["url"] == "" and home["apply_at"] == "/api/hub/register"
