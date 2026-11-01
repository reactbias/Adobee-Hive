"""Four separate processes' worth of the design: an agent service, a hub that indexes, a hotel that books.

The hub and the agent are the same code as ever, started with different settings. What this proves over real
HTTP is the separation itself: the agent's own store stays empty, the hub holds the hotel's card but no booking
and no key, and the booking and its receipt are made by the hotel's node.
"""

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import agent, config, hive

BACKEND = Path(__file__).resolve().parents[1]
CARD = BACKEND.parents[1] / "testdata" / "hotel-node" / "hotel-lindenhof.json"
CARD_ID = "hotel-lindenhof"
TOKEN = "fictional-owner-token"
GUEST = "Fictional Node Guest"
ASK = f"Book a dog-friendly hotel in Basel from 2027-03-08 to 2027-03-10 for {GUEST}."


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _get(url: str, timeout: float = 10) -> dict | list:
    with urllib.request.urlopen(url, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
        return json.loads(answer.read())


def _post(url: str, body: dict, timeout: float = 60) -> dict:
    request = urllib.request.Request(  # noqa: S310 - our own subprocess
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
            return json.loads(answer.read())
    except urllib.error.HTTPError as err:
        raise AssertionError(f"{url} answered {err.code}: {err.read().decode()}") from err


def _bookings(base: str) -> list[dict]:
    """Bookings for the hotel on one server, asked of that server."""
    try:
        return _get(f"{base}/api/owner/{CARD_ID}").get("bookings", [])
    except urllib.error.HTTPError:  # this server has never heard of the card
        return []


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """A hub, a hotel node and an agent service, each its own process with its own store."""
    ports = {"hub": _free_port(), "node": _free_port(), "agent": _free_port()}
    urls = {name: f"http://127.0.0.1:{port}" for name, port in ports.items()}
    data = tmp_path_factory.mktemp("hotelnode")
    base_env = {
        **os.environ,
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "LLM_PROVIDER": "offline",
        "HIVE_PEER_URLS": "",
        "HIVE_MCP_URLS": "",
        "DATABASE_URL": "",
        "SEED_ON_EMPTY": "false",
    }
    settings = {
        "hub": {"HIVE_HUB_ID": "hub", "OWNER_EDIT_TOKEN": TOKEN},
        "node": {"HIVE_HUB_ID": CARD_ID},
        "agent": {"HIVE_HUB_ID": "agent", "HIVE_MCP_URLS": f"{urls['hub']}/mcp/", "NODE_ALLOW_PRIVATE": "true"},
    }
    procs, logs = {}, []
    try:
        for name, port in ports.items():
            log = (data / f"{name}.log").open("w")
            logs.append(log)
            if name == "node":  # the card and its key are made before the node serves anything
                subprocess.run(  # noqa: S603 - our own interpreter and tool
                    [
                        sys.executable,
                        "tools/hotel_node.py",
                        "--card",
                        str(CARD),
                        "--db",
                        str(data / "node.duckdb"),
                        "--mcp-url",
                        f"{urls['node']}/mcp/",
                    ],
                    env=base_env,
                    cwd=str(BACKEND),
                    check=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            procs[name] = subprocess.Popen(  # noqa: S603 - our own interpreter and module
                [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--port", str(port)],
                env={**base_env, **settings[name], "DUCKDB_PATH": str(data / f"{name}.duckdb")},
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(BACKEND),
            )
        for name, url in urls.items():
            for _ in range(150):
                try:
                    if _get(f"{url}/api/health", timeout=1):
                        break
                except Exception:  # noqa: BLE001 - still starting, or never will
                    time.sleep(0.2)
            else:
                log_text = (data / f"{name}.log").read_text()
                pytest.fail(f"the {name} service did not come up:\n{log_text}")
        subprocess.run(  # noqa: S603 - our own interpreter and tool
            [
                sys.executable,
                "tools/hotel_node.py",
                "--card",
                str(CARD),
                "--db",
                str(data / "push.duckdb"),
                "--from-node",
                urls["node"],
                "--hub",
                urls["hub"],
            ],
            env={**base_env, "OWNER_EDIT_TOKEN": TOKEN},
            cwd=str(BACKEND),
            check=True,
            capture_output=True,
        )
        yield urls
    finally:
        for proc in procs.values():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - a service that will not stop
                proc.kill()
        for log in logs:
            log.close()


def test_the_hub_carries_the_hotels_card_with_the_hotels_own_key(stack):
    at_hub = _get(f"{stack['hub']}/api/hive/cards/{CARD_ID}")
    at_node = _get(f"{stack['node']}/api/hive/cards/{CARD_ID}")

    assert at_hub["trust"]["public_key"] == at_node["trust"]["public_key"]
    assert at_hub["trust"]["signature"] == at_node["trust"]["signature"]
    registry = _get(f"{stack['hub']}/.well-known/hive.json")["owner_keys"]
    assert registry[CARD_ID] == at_node["trust"]["public_key"]


def test_a_booking_through_the_agent_service_is_made_by_the_hotel(stack):
    run = _post(f"{stack['agent']}/api/agent", {"messages": [{"role": "user", "content": ASK}]})
    pending = run["pending"]
    assert pending is not None, f"the agent held nothing to approve: {run.get('reply')}"
    assert _bookings(stack["node"]) == [], "nothing may be booked before the person's yes"

    done = _post(f"{stack['agent']}/api/agent/approve", {"pending": pending})

    assert done["booking"] is not None, f"the approval did not go through: {done['reply']}"
    assert len(_bookings(stack["node"])) == 1, "the hotel's node did not take the booking"
    assert _bookings(stack["hub"]) == [], "the hub took a booking that belongs to the hotel"
    assert _bookings(stack["agent"]) == [], "the agent service stored a booking of its own"

    pinned = _get(f"{stack['hub']}/.well-known/hive.json")["owner_keys"][CARD_ID]
    assert hive.verify_statement(done["booking"]["receipt"], pinned), "the receipt must verify against the pinned key"


def test_a_receipt_that_fails_the_pinned_key_is_not_reported_as_a_booking(client, stack, monkeypatch):
    monkeypatch.setattr(config, "NODE_ALLOW_PRIVATE", True)
    key = Ed25519PrivateKey.generate().public_key()
    stranger = base64.b64encode(key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    pending = agent._hold(
        {
            "card_id": CARD_ID,
            "unit_id": "double",
            "check_in": "2027-04-08",
            "check_out": "2027-04-10",
            "guest_name": "Fictional Second Guest",
            "guests": 2,
            "agent": "test",
        },
        f"{stack['node']}/mcp/",
        pin=stranger,
    )

    done = asyncio.run(agent.approve(pending))

    assert done["booking"] is None
    assert "receipt" in done["reply"], "it must fail on the receipt, not on reaching the node"


def _signed_statement(body: dict) -> tuple[str, str]:
    """A statement a business really signed, and its public key."""
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    encoded = hive.canonical(body)
    statement = base64.urlsafe_b64encode(encoded).decode() + "." + base64.urlsafe_b64encode(key.sign(encoded)).decode()
    return statement, base64.b64encode(raw).decode()


HELD_STAY = {"card_id": "c", "unit_id": "double", "check_in": "2027-04-08", "check_out": "2027-04-10", "guests": 2}


def test_a_signed_receipt_must_be_for_the_booking_that_was_approved():
    body = HELD_STAY | {"booking_id": "bk_1"}
    good, public = _signed_statement(body)
    assert agent._receipt_matches({"receipt": good, "booking_id": "bk_1"}, HELD_STAY, public)

    unrelated, public = _signed_statement({"unrelated": "statement"})
    assert not agent._receipt_matches({"receipt": unrelated, "booking_id": "bk_1"}, HELD_STAY, public)

    other_dates, public = _signed_statement(body | {"check_in": "2026-01-01"})
    assert not agent._receipt_matches({"receipt": other_dates, "booking_id": "bk_1"}, HELD_STAY, public)

    old, public = _signed_statement(body)
    assert not agent._receipt_matches({"receipt": old, "booking_id": "bk_2"}, HELD_STAY, public)

    assert not agent._receipt_matches({"receipt": "not.a-receipt", "booking_id": "bk_1"}, HELD_STAY, public)


def test_an_approval_reaches_the_hotel_even_when_the_hub_has_gone_away(client, stack, monkeypatch):
    monkeypatch.setattr(config, "NODE_ALLOW_PRIVATE", True)
    pinned = _get(f"{stack['hub']}/.well-known/hive.json")["owner_keys"][CARD_ID]
    pending = agent._hold(
        {
            "card_id": CARD_ID,
            "unit_id": "double",
            "check_in": "2027-09-08",
            "check_out": "2027-09-10",
            "guest_name": "Fictional Third Guest",
            "guests": 2,
            "agent": "test",
        },
        f"{stack['node']}/mcp/",
        pin=pinned,
    )
    monkeypatch.setattr(config, "HIVE_MCP_URLS", [f"http://127.0.0.1:{_free_port()}/mcp/"])

    done = asyncio.run(agent.approve(pending))

    assert done["booking"] is not None, f"the approval did not go through: {done['reply']}"


def test_a_node_address_is_checked_again_when_it_is_dialled(client, monkeypatch):
    monkeypatch.setattr(config, "NODE_ALLOW_PRIVATE", False)
    tried = []
    monkeypatch.setattr(agent, "Client", lambda target: tried.append(target) or agent.Client)

    async def ask() -> dict:
        hives = agent.HiveConnections()
        hives.direct["hotel-private"] = "http://127.0.0.1:9/mcp/"
        return await hives._call_node("http://127.0.0.1:9/mcp/", "hive_book", {"card_id": "hotel-private"})

    assert "error" in asyncio.run(ask())
    assert tried == [], "a private address must never be dialled"


def test_a_hotel_node_that_is_down_is_an_answer_not_a_crash(client, monkeypatch):
    monkeypatch.setattr(config, "NODE_ALLOW_PRIVATE", True)
    closed = f"http://127.0.0.1:{_free_port()}/mcp/"
    pending = agent._hold(
        {
            "card_id": "hotel-gone",
            "unit_id": "double",
            "check_in": "2027-05-08",
            "check_out": "2027-05-10",
            "guest_name": "Fictional Guest",
            "guests": 1,
            "agent": "test",
        },
        closed,
        pin="irrelevant",
    )

    done = asyncio.run(agent.approve(pending))
    assert done["booking"] is None

    async def ask() -> dict:
        async with agent.HiveConnections() as hives:
            hives.direct["hotel-gone"] = closed
            stay = {"card_id": "hotel-gone", "check_in": "2027-05-08", "check_out": "2027-05-10"}
            return await hives.call("hive_check_availability", stay)

    assert "error" in asyncio.run(ask())


@pytest.mark.parametrize(
    ("contact", "allow_private", "expected"),
    [
        ({}, False, ""),
        ({"mcp": ""}, False, ""),
        ({"mcp": "ftp://node.example/mcp/"}, True, ""),
        ({"mcp": "not a url"}, True, ""),
        ({"mcp": "http://[broken/mcp/"}, True, ""),
        ({"mcp": "http://[broken/mcp/"}, False, ""),
        ({"mcp": "https://example.com:bad/mcp/"}, True, ""),
        ({"mcp": "https://example.com:bad/mcp/"}, False, ""),
        ({"mcp": "http://127.0.0.1:9/mcp/"}, False, ""),
        ({"mcp": "http://169.254.169.254/mcp/"}, False, ""),
        ({"mcp": "http://127.0.0.1:9/mcp/"}, True, "http://127.0.0.1:9/mcp/"),
    ],
)
def test_only_a_safe_address_on_a_card_is_ever_dialled(monkeypatch, contact, allow_private, expected):
    monkeypatch.setattr(config, "NODE_ALLOW_PRIVATE", allow_private)

    assert agent.node_url({"contact": contact}) == expected


def test_a_card_whose_signature_fails_never_routes_the_agent_to_its_address(client, monkeypatch):
    monkeypatch.setattr(config, "NODE_ALLOW_PRIVATE", True)
    card = hive.publish(
        {
            "id": "hotel-forged-route",
            "slug": "hotel-forged-route",
            "kind": "hotel",
            "name": "Fictional Route",
            "contact": {"mcp": "http://127.0.0.1:9/mcp/"},
        }
    )
    hives = agent.HiveConnections()
    hives.last_source = "test"

    hives._guard("hive_get_card", json.loads(json.dumps(card)), {})
    assert "hotel-forged-route" not in hives.direct, "no pinned key: the address must not be trusted"

    hives.pins = hive.owner_keys()
    hives._guard("hive_get_card", json.loads(json.dumps(card)), {})
    assert hives.direct["hotel-forged-route"] == "http://127.0.0.1:9/mcp/"


def test_an_unreachable_hotel_is_not_reported_as_sold_out(client, stack, monkeypatch):
    monkeypatch.setattr(config, "HIVE_MCP_URLS", [f"{stack['hub']}/mcp/"])
    monkeypatch.setattr(agent, "node_url", lambda _card: f"http://127.0.0.1:{_free_port()}/mcp/")

    run = asyncio.run(agent.run([{"role": "user", "content": ASK}]))

    assert run["pending"] is None
    assert "could not be reached" in run["reply"]


def test_a_model_agents_hold_goes_to_the_node_with_the_pinned_key():
    hives = agent.HiveConnections()
    hives.routes["hive_book"] = ["hub"]
    hives.direct["hotel-on-node"] = "https://node.example/mcp/"
    hives.pins["hotel-on-node"] = "pinned-key"

    pending, args = agent._call_tool("hive_book", {"card_id": "hotel-on-node"}, hives)
    stored = agent._HELD[pending["id"]][1]
    assert (stored["_source"], stored["_pin"], args) == ("https://node.example/mcp/", "pinned-key", {})

    pending, _ = agent._call_tool("hive_book", {"card_id": "hotel-on-hub"}, hives)
    stored = agent._HELD[pending["id"]][1]
    assert stored["_source"] == "hub"
    assert "_pin" not in stored, "a card without its own node must still book on the hub"
