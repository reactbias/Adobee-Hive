"""A failed or refused tool call is never shown as an empty directory."""

import asyncio

from app import agent

ASK = {
    "query": "quiet dog-friendly hotel",
    "near": "basel sbb",
    "max_price_chf": 200,
    "features": ["quiet", "dog-friendly", "late check-in"],
    "check_in": "2026-11-13",
    "check_out": "2026-11-15",
}


async def _discover(args):
    async with agent.HiveConnections() as hives:
        steps: list = []
        return await hives.step(steps, "hive_discover", args), steps


def test_seeded_directory_is_not_empty(client):
    out, _ = asyncio.run(_discover({}))
    assert len(out["matches"]) >= 5


def test_null_optional_arguments_are_dropped(client):
    # Models often send null for arguments they leave open; the MCP schema rejects null for guests.
    out, _ = asyncio.run(_discover(ASK | {"kind": None, "guests": None, "ruleset": None}))
    assert out["matches"][0]["id"] == "hotel-rheinblick"
    assert "errors" not in out


def test_a_refused_call_reaches_agent_and_trace_as_an_error(client):
    out, steps = asyncio.run(_discover(ASK | {"guests": "two"}))
    assert out["matches"] == []
    (err,) = out["errors"]
    assert "guests" in err["error"]
    assert steps[0]["output"]["errors"]  # the trace shows the error, not "0 of 0 fit"
