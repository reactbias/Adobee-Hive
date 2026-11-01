"""Whose rules? A ruleset is signed by whoever wrote it, chosen per request, and named in every answer it shapes."""

import asyncio

import pytest
from mcp import Client

from app import hive, rulesets
from app.mcp_server import server
from tests.mcp_result import tool_result

STAY = {"check_in": "2027-02-10", "check_out": "2027-02-12"}


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return tool_result(await c.call_tool(tool, args))

    return asyncio.run(go())


def test_rulesets_are_signed_by_their_authors(client):
    listed = _mcp("hive_rulesets", {})["rulesets"]
    pins = client.get("/.well-known/hive.json").json()["ruleset_keys"]
    assert {"hive-floor", "dogs-verified", "access-verified", "quiet-nights", "calm"} <= {r["id"] for r in listed}
    for r in listed:
        assert hive.verify_statement(r["statement"], pins[r["id"]])
        assert hive.read_statement(r["statement"])["author"] == r["author"]
    assert not set(pins) & set(client.get("/.well-known/hive.json").json()["owner_keys"])


def test_same_request_different_rules_different_answer(client):
    ask = {"features": ["dog-friendly"], "kind": "hotel", **STAY}
    plain = {m["id"] for m in _mcp("hive_discover", ask)["matches"]}
    assert {"hotel-rheinblick", "hotel-dreirosen", "hotel-messe"} <= plain

    out = _mcp("hive_discover", {**ask, "ruleset": "dogs-verified"})
    assert [m["id"] for m in out["matches"]] == ["hotel-rheinblick"]  # the only dog-friendly claim someone vouched for
    why_not = {e["id"]: e["why_not"] for e in out["excluded"]}
    assert "dog-friendly is not attested by a third party" in why_not["hotel-dreirosen"][-1]
    used = out["ruleset"]
    assert used["id"] == "dogs-verified" and used["author"] == "Basel Dog Owners Club (fictional)"
    assert any("left out" in c for c in used["changed"])


def test_calm_ruleset_shows_two_options_and_says_so(client):
    out = _mcp("hive_discover", {"kind": "hotel", "ruleset": "calm", **STAY})
    assert len(out["matches"]) == 2
    assert any("set aside" in e["why_not"][-1] for e in out["excluded"])


def test_unknown_ruleset_is_refused(client):
    assert "error" in _mcp("hive_discover", {"kind": "hotel", "ruleset": "pay-to-rank"})


def test_a_ruleset_can_only_add_rules_never_loosen_the_floor():
    with pytest.raises(ValueError):
        rulesets.validate({"boost": {"hotel-muenster": 100}})
    with pytest.raises(ValueError):
        rulesets.validate({"ignore_signatures": True})
    rulesets.validate({"require_features": ["quiet"], "max_results": 2})
