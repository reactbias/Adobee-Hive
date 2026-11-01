"""One budget per costly operation, whichever transport asks for it.

This hub is reachable over REST and over MCP at `/mcp`, with the same costly work behind both: a
search that fans out to peer hubs, and a scout that pays for a web search and fetches other sites'
pages. A budget only one transport spends is not a budget, and that is what these tests pin — a
caller refused at the REST door used to walk in through the MCP one and run the same work.

The MCP calls go through the real Streamable HTTP endpoint over an in-process ASGI transport, so
there is no socket and no port to collide with a running demo, and `client=` gives the call a peer
address the ASGI server observes exactly as it would a real one. That matters here: the principal a
budget is charged to is read off the transport, so a test that could not set an address could not
check that two callers have two budgets.

Every test installs its own small `RateLimiter` rather than draining the hub's. Draining the real
one would leak into whatever ran next in the session, and a budget test that depends on test order
is not a budget test.
"""

import asyncio

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app import config, guard, limits
from app.domains import scout
from app.main import app
from app.mcp_server import server
from tests.mcp_result import tool_result

SOMEONE = "203.0.113.9"
SOMEBODY_ELSE = "198.51.100.4"


def _mcp(tool: str, args: dict, host: str = SOMEONE) -> dict:
    """Call one MCP tool over Streamable HTTP as a caller at `host`, and return its JSON answer."""

    async def go():
        async with (
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app, client=(host, 55555)), base_url="http://hive.test"
            ) as http,
            Client(streamable_http_client("http://hive.test/mcp/", http_client=http)) as mcp,
        ):
            return await mcp.call_tool(tool, args)

    return tool_result(asyncio.run(go()))


def _mcp_in_process(tool: str, args: dict) -> dict:
    """Call one MCP tool the way this repo's own agent does: in process, with no transport at all."""

    async def go():
        async with Client(server) as mcp:
            return await mcp.call_tool(tool, args)

    return tool_result(asyncio.run(go()))


@pytest.fixture
def one_federated_call(monkeypatch):
    """A `federated` budget with room for exactly one call on this hub, per client and in total."""
    limiter = guard.RateLimiter(per_client=1, total=1)
    monkeypatch.setattr(guard, "federated", limiter)
    return limiter


@pytest.fixture
def two_federated_calls(monkeypatch):
    """A `federated` budget with room for one call per client and two for the hub.

    Enough to tell a per-client refusal from a hub-global one: one caller spends its own share and
    is refused, while a second caller still has the hub's remaining call to spend.
    """
    limiter = guard.RateLimiter(per_client=1, total=2)
    monkeypatch.setattr(guard, "federated", limiter)
    return limiter


@pytest.fixture
def one_model_call(monkeypatch):
    """An `llm_calls` budget with room for exactly one paid call on this hub."""
    limiter = guard.RateLimiter(per_client=1, total=1)
    monkeypatch.setattr(guard, "llm_calls", limiter)
    return limiter


@pytest.fixture
def recorded_search(monkeypatch):
    """The scout's external search, replaced by a recording function that reaches no network.

    The safe dependency boundary the regression needs: a refusal has to happen *before* the search,
    and the only way to show that is a boundary that counts how many times it was reached. It
    returns no candidates, so nothing is compiled and nothing is written either.
    """
    reached: list[str] = []

    def recording(question: str) -> list[dict]:
        reached.append(question)
        return []

    monkeypatch.setattr(scout, "_search", recording)
    return reached


# ---------------------------------------------------------------- across the two transports


def test_a_federated_budget_spent_over_rest_refuses_the_same_search_over_mcp(client, one_federated_call):
    """The bug: REST refused a far search for an exhausted budget and MCP ran it anyway."""
    assert client.get("/api/hive/discover?query=quiet&radius=1").status_code == 200
    assert client.get("/api/hive/discover?query=quiet&radius=1").status_code == 429

    refused = _mcp("hive_discover", {"query": "quiet", "radius": 1})

    assert "error" in refused, "MCP ran a far search on a budget REST had already refused"
    assert "matches" not in refused
    assert "Try again in" in refused["error"]


def test_a_federated_budget_spent_over_mcp_refuses_the_same_search_over_rest(client, one_federated_call):
    """And the other way round, which is the half a per-transport limiter would still get wrong."""
    assert "error" not in _mcp("hive_discover", {"query": "quiet", "radius": 1})

    over = client.get("/api/hive/discover?query=quiet&radius=1")

    assert over.status_code == 429, "REST ran a far search on a budget MCP had already spent"
    assert "Retry-After" in over.headers


def test_a_local_search_over_mcp_is_never_charged_to_the_federated_budget(client, one_federated_call):
    """radius=0 asks no peer, so it costs this hub nothing outbound and must stay free."""
    for _ in range(3):
        assert "error" not in _mcp("hive_discover", {"query": "quiet", "radius": 0})
    assert client.get("/api/hive/discover?query=quiet&radius=1").status_code == 200


def test_the_scout_is_refused_over_mcp_before_the_search(client, one_model_call, recorded_search, monkeypatch):
    """A paid search must be refused *before* the network call, not after it has already been made."""
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    assert client.post("/api/ask/scout", json={"question": "a locksmith in basel"}).status_code == 200
    spent_by_rest = len(recorded_search)
    assert spent_by_rest == 1, "the REST call should have reached the boundary exactly once"

    refused = _mcp("hive_scout", {"question": "a locksmith in basel"})

    assert "error" in refused and "Try again in" in refused["error"]
    assert len(recorded_search) == spent_by_rest, "MCP reached the paid search after being refused"


def test_hub_connect_over_mcp_spends_the_budget_its_rest_twin_spends(client, one_federated_call):
    """Verifying a peer's card means fetching that peer's key registry, which REST already pays for."""
    assert client.get("/api/hive/discover?query=quiet&radius=1").status_code == 200

    refused = _mcp("hub_connect", {"requester": "Fictional Asker", "entity_id": "hotel-rheinblick"})

    assert "error" in refused and "Try again in" in refused["error"]


def test_hub_register_over_mcp_spends_the_budget_its_rest_twin_spends(client, one_federated_call):
    """An application is signature-checked and stored; the MCP door must not be the cheap way in."""
    assert client.get("/api/hive/discover?query=quiet&radius=1").status_code == 200

    refused = _mcp("hub_register", {"entity": {"id": "fictional-co", "kind": "person", "name": "Fictional Co"}})

    assert "error" in refused and "Try again in" in refused["error"]


# ---------------------------------------------------------------- who the call is charged to


def test_an_mcp_caller_is_charged_by_its_transport_address(client, two_federated_calls):
    """Two callers have two budgets, told apart by the address the ASGI server saw."""
    assert "error" not in _mcp("hive_discover", {"query": "quiet", "radius": 1}, host=SOMEONE)
    assert "error" in _mcp("hive_discover", {"query": "quiet", "radius": 1}, host=SOMEONE)

    assert "error" not in _mcp(
        "hive_discover", {"query": "quiet", "radius": 1}, host=SOMEBODY_ELSE
    ), "one caller spending its own share must not spend another's"


def test_a_tool_argument_cannot_choose_which_budget_it_spends(client, two_federated_calls):
    """The principal comes off the transport. A caller that could name its own would have no budget.

    `hive_discover` takes a `query`, so this spends the first caller's share with one query and then
    asks again with another: a different argument, the same address, and so the same budget.
    """
    assert "error" not in _mcp("hive_discover", {"query": "quiet", "radius": 1}, host=SOMEONE)

    assert "error" in _mcp("hive_discover", {"query": "something else entirely", "radius": 1}, host=SOMEONE)


def test_a_transport_with_no_address_is_counted_as_one_in_process_caller(client, two_federated_calls):
    """This repo's own agent reaches the same tools in process, where there is no address to charge.

    It is charged as one named principal rather than exempted: `POST /api/agent` spends `llm_calls`
    for the run and never spends `federated`, so the agent's peer fan-out is counted here or nowhere
    — and on a hub with no model key that door spends nothing at all.
    """
    assert guard.mcp_client(None) == guard.IN_PROCESS

    assert "error" not in _mcp_in_process("hive_discover", {"query": "quiet", "radius": 1})
    assert "error" in _mcp_in_process("hive_discover", {"query": "quiet", "radius": 1})


def test_the_in_process_agent_is_not_charged_twice_for_one_model_run(client, one_model_call, recorded_search):
    """`POST /api/agent` spends the model budget for the whole run; the agent's own tools must not again.

    The deliberate half of the attribution policy. A hub that charged both would refuse the agent
    its second tool call inside a run the caller had already paid for.
    """
    assert guard.admit_mcp(guard.llm_calls, None, charge_in_process=False) == ""
    assert guard.admit_mcp(guard.llm_calls, None, charge_in_process=False) == ""

    assert one_model_call.hits == {}, "an in-process call charged a budget its REST door had already spent"


def test_an_unreachable_transport_is_counted_rather_than_waved_through(client):
    """A context that carries no request, or a request with no peer, is one caller and not no caller."""

    class NoRequest:
        request_context = None

    class NoPeer:
        request_context = type("ctx", (), {"request": type("req", (), {"client": None})()})()

    assert guard.mcp_client(NoRequest()) == guard.IN_PROCESS
    assert guard.mcp_client(NoPeer()) == guard.IN_PROCESS


# ---------------------------------------------------------------- the size of the answer


def test_a_discovery_answer_over_mcp_is_bounded_and_says_so(client):
    """An unbounded answer is a resource hole even when no counter was breached.

    At radius 2 this tool answered with every card inline — about 690 KB for 73 of them, because a
    federated match carries the whole signed card. It took no limit, so a caller could not ask for
    less, and a client reading only `matches` could not tell a full answer from a cut one.
    """
    whole = _mcp("hive_discover", {"query": "", "radius": 0, "limit": limits.MAX_ANSWER_MATCHES})
    assert len(whole["matches"]) >= 2, "this hub needs at least two matches for the rest of this test"
    assert "truncated" not in whole

    cut = _mcp("hive_discover", {"query": "", "radius": 0, "limit": 1})

    assert len(cut["matches"]) == 1
    assert cut["truncated"] is True
    assert cut["total_matches"] == len(whole["matches"])
    assert str(len(whole["matches"])) in cut["note"]


def test_a_caller_cannot_ask_for_an_unbounded_answer(client):
    """`limit` is clamped, so neither a caller asking for everything nor one asking for nothing gets it.

    The ceilings are written out as literals rather than read back off the module. Comparing
    `bound_answer(found, 10_000)` against `limits.MAX_ANSWER_MATCHES` moves both sides of the
    assertion together, so raising the ceiling to 10_000 passed it — which is exactly the mutant
    this is meant to catch. A published number is pinned here, and changing it is a deliberate edit
    in two places.
    """
    found = {"matches": [{"id": str(n)} for n in range(200)]}

    assert (limits.MAX_ANSWER_MATCHES, limits.DEFAULT_ANSWER_MATCHES) == (50, 20)
    assert len(limits.bound_answer(found, 10_000)["matches"]) == 50
    assert len(limits.bound_answer(found, 0)["matches"]) == 1
    assert len(limits.bound_answer(found, -5)["matches"]) == 1
    assert len(limits.bound_answer(found, None)["matches"]) == 20


def test_bounding_an_answer_leaves_a_refusal_alone():
    """A refusal has no matches to cut, and must come back as the refusal it is."""
    refusal = {"error": "No such ruleset."}

    assert limits.bound_answer(refusal, 5) == refusal
