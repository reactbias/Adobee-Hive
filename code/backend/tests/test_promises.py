"""The promises the demo makes, each pinned by a test: receipts prove a stay, holds are one-time, guards hold."""

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from app import agent, guard, hive
from app.domains import base, hr
from app.mcp_server import server
from tests.mcp_result import tool_result


def _book(card: str, unit: str, check_in: str, check_out: str) -> dict:
    return hive.book(card, unit, check_in, check_out, guest_name="Test Guest")


# ---------------------------------------------------------------- receipts


def test_a_receipt_cancels_its_own_booking_only(client):
    first = _book("hotel-dreirosen", "dorm", "2027-02-01", "2027-02-02")
    second = _book("hotel-dreirosen", "dorm", "2027-02-03", "2027-02-04")
    with pytest.raises(hive.HiveError, match="does not belong"):
        hive.cancel(second["booking_id"], first["receipt"])
    assert hive.cancel(first["booking_id"], first["receipt"])["status"] == "cancelled"


def test_a_receipt_from_another_business_is_rejected(client):
    elsewhere = _book("hotel-dreirosen", "dorm", "2027-02-05", "2027-02-06")
    here = _book("hotel-rheinblick", "river", "2027-02-05", "2027-02-06")
    with pytest.raises(hive.HiveError, match="not valid for this business"):
        hive.cancel(here["booking_id"], elsewhere["receipt"])


def test_a_cancelled_stay_cannot_be_reviewed(client):
    booking = _book("hotel-dreirosen", "dorm", "2027-02-07", "2027-02-08")
    hive.cancel(booking["booking_id"], booking["receipt"])
    with pytest.raises(hive.HiveError, match="Only confirmed stays"):
        hive.review(booking["receipt"], 5, "never stayed")


@pytest.mark.parametrize("receipt", ["", "no-dot", "a.b.c", "!!!.???"])
def test_malformed_receipts_are_refused_not_crashing(client, receipt):
    with pytest.raises(hive.HiveError):
        hive.review(receipt, 5, "x")


def test_a_cancelled_room_is_free_again(client):
    booking = _book("hotel-muenster", "suite", "2027-03-01", "2027-03-02")
    _book("hotel-muenster", "suite", "2027-03-01", "2027-03-02")
    assert not any(
        u["id"] == "suite"
        for u in hive.check_availability("hotel-muenster", "2027-03-01", "2027-03-02")["available_units"]
    )
    hive.cancel(booking["booking_id"], booking["receipt"])
    assert any(
        u["id"] == "suite"
        for u in hive.check_availability("hotel-muenster", "2027-03-01", "2027-03-02")["available_units"]
    )


# ---------------------------------------------------------------- held bookings


@pytest.fixture
def holds(monkeypatch):
    monkeypatch.setattr(agent, "_HELD", {})
    return agent._HELD


def test_an_expired_hold_cannot_be_approved(holds):
    held = agent._hold({"card_id": "hotel-rheinblick"})
    holds[held["id"]] = (time.time() - agent.HOLD_TTL_S - 1, holds[held["id"]][1])
    with pytest.raises(ValueError, match="expired"):
        agent._take(held["id"])


def test_an_unknown_hold_cannot_be_approved(holds):
    with pytest.raises(ValueError):
        agent._take("made-up")


def test_holds_are_capped_dropping_expired_then_oldest(holds, monkeypatch):
    monkeypatch.setattr(agent, "MAX_HELD", 3)
    stale, oldest, middle = (agent._hold({"n": n})["id"] for n in range(3))
    holds[stale] = (time.time() - agent.HOLD_TTL_S - 1, holds[stale][1])
    newest = agent._hold({"n": 3})["id"]
    assert set(holds) == {oldest, middle, newest}  # the expired one went first
    agent._hold({"n": 4})
    assert oldest not in holds and len(holds) == 3


def test_a_hold_keeps_a_copy_of_what_the_agent_chose(holds):
    args = {"unit_id": "river"}
    held = agent._hold(args)
    args["unit_id"] = "suite"
    assert agent._take(held["id"]) == {"unit_id": "river"}


# ---------------------------------------------------------------- guards


def _request(host: str = "10.0.0.1", headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers or {})


def test_the_rate_limit_is_per_client_and_global():
    limit = guard.RateLimiter(per_client=2, total=3)
    limit.check(_request("a"))
    limit.check(_request("a"))
    with pytest.raises(HTTPException) as err:
        limit.check(_request("a"))
    assert err.value.status_code == 429
    limit.check(_request("b"))
    with pytest.raises(HTTPException):
        limit.check(_request("c"))  # the backend's total is spent


def test_the_rate_limit_window_slides(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(guard.time, "monotonic", lambda: now[0])
    limit = guard.RateLimiter(per_client=1, total=10, window_s=60)
    limit.check(_request())
    with pytest.raises(HTTPException):
        limit.check(_request())
    now[0] += 61
    limit.check(_request())


def test_a_secret_header_must_match_when_set():
    guard.require_secret(_request(), "X-Owner-Token", "")  # off when no secret is configured
    guard.require_secret(_request(headers={"X-Owner-Token": "s3cret"}), "X-Owner-Token", "s3cret")
    with pytest.raises(HTTPException) as err:
        guard.require_secret(_request(headers={"X-Owner-Token": "guess"}), "X-Owner-Token", "s3cret")
    assert err.value.status_code == 403


# ---------------------------------------------------------------- domains


def test_safe_turns_a_refusal_into_an_error_result():
    def refuse():
        raise hive.HiveError("No.")

    with pytest.raises(ToolError, match="No."):
        base.safe(refuse)
    with pytest.raises(KeyError):  # real bugs still surface
        base.safe(lambda: {}["missing"])


def test_a_person_card_shows_only_public_fields():
    card = {**hr.EXAMPLE_CARD, "email": "x@example.org", "age": 41, "trust": {"signature_valid": True}}
    view = hr.public_view(card)
    assert set(view) <= set(hr.PUBLIC_FIELDS) | {"signature_valid"}
    assert "email" not in view and "age" not in view


def test_people_search_needs_a_skill_and_respects_location(client):
    hive.publish(dict(hr.EXAMPLE_CARD))
    with pytest.raises(hive.HiveError):
        hr.find_people([" "])
    found = hr.find_people(["figma"], location="Zurich")
    assert found["matches"] == [] and found["excluded"][0]["why_not"] == ["not in Zurich"]


def test_an_intro_is_only_for_people_and_needs_a_message(client):
    hive.publish(dict(hr.EXAMPLE_CARD))
    with pytest.raises(hive.HiveError, match="not a person card"):
        hr.request_intro("hotel-rheinblick", "Org", "Hello")
    with pytest.raises(hive.HiveError):
        hr.request_intro("person-mira", "Org", " ")
    with pytest.raises(hive.HiveError):
        hr.request_intro("person-mira", "Org", "x" * (hr.MAX_MESSAGE + 1))


def test_an_hr_refusal_reaches_the_agent_as_an_error_over_mcp(client):
    async def ask():
        async with Client(server) as c:
            res = await c.call_tool(
                "hr_request_intro", {"card_id": "hotel-rheinblick", "from_org": "O", "message": "Hi"}
            )
            return tool_result(res)

    assert "not a person card" in asyncio.run(ask())["error"]


def test_a_booking_is_cancelled_once(client):
    booking = _book("hotel-dreirosen", "dorm", "2027-02-09", "2027-02-10")
    hive.cancel(booking["booking_id"], booking["receipt"])
    with pytest.raises(hive.HiveError, match="already cancelled"):
        hive.cancel(booking["booking_id"], booking["receipt"])
