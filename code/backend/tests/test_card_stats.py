"""Each business sees what agents did with its card this week: shown, read, checked, booked or handed off."""

import asyncio
from datetime import date

from mcp import Client

from app import hive
from app.domains import explore
from app.mcp_server import server


def _week(card_id):
    return hive.owner_overview(card_id)["last_7_days"]


def _call(tool, args):
    async def run():
        async with Client(server) as c:
            await c.call_tool(tool, args)

    asyncio.run(run())


def test_an_agent_reading_the_card_counts_as_read(client):
    before = _week("hotel-rheinblick").get("read", 0)
    _call("hive_get_card", {"card_id": "hotel-rheinblick"})
    assert _week("hotel-rheinblick").get("read", 0) == before + 1


def test_an_agent_checking_rooms_counts_as_checked(client):
    before = _week("hotel-rheinblick").get("checked", 0)
    _call(
        "hive_check_availability", {"card_id": "hotel-rheinblick", "check_in": "2026-11-13", "check_out": "2026-11-15"}
    )
    assert _week("hotel-rheinblick").get("checked", 0) == before + 1


def test_any_business_that_answers_a_question_counts_as_shown(client):
    before = _week("x-endress").get("shown", 0)
    out = explore.ask("What's going on at Endress this month?", today=date(2026, 11, 2))
    assert {r["card_id"] for r in out["replies"]} == {"x-endress"}
    assert _week("x-endress").get("shown", 0) == before + 1


def test_the_owner_view_works_for_an_unclaimed_card(client):
    r = client.get("/api/owner/x-endress")
    assert r.status_code == 200
    assert r.json()["card"]["trust"]["claimed"] is False
