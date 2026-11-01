"""A refused MCP call says so, and a successful one says what happens next (#155).

From a user test against two running hubs:

- `hub_connect` with an unknown id answered `{"error": "no entity 'zzz' on this hub"}` with
  **`isError: false`**. An agent that checks the flag — which is every well-behaved client — reads
  that as a success whose body happens to contain the word error, and tells its person it worked.
  A failure reported as a success is worse than a bad message.
- a missing `requester` came back as a page of pydantic: which field, and nothing about what
  belongs in it.
- and the success was a bare record: `state: "open"`, `target_hub: ""`, a `stale_at` three weeks
  out. Open meaning what? Is the person notified? Why is `target_hub` blank when I just connected
  to somebody? Nothing in the answer said.

So: refusals are raised as `ToolError`, which is what sets `isError`; the arguments a caller is
most likely to get wrong are refused in words rather than in a schema dump; and the record carries
`says` — including, because nothing here sends a notification, that nobody has been told.
"""

from __future__ import annotations

import asyncio
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from app import config, connections, federation, hive, hub
from app.domains import base
from app.mcp_server import server
from tests.mcp_result import tool_result


def _call(tool: str, args: dict):
    """One MCP tool call, returned as the protocol's own result so `isError` can be read."""

    async def go():
        async with Client(server) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(go())


def _text(result) -> str:
    return result.content[0].text if result.content else ""


BERN, THEM = "bern", "elektro-mattenhof"


def _remote_card() -> tuple[dict, dict[str, str]]:
    """A card signed by a fresh key, plus the registry entry that pins that key for it.

    The same construction `tests/test_cross_hub_connect.py` uses: never published into this hub's
    index, because the point is an entity this hub does not carry.
    """
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    body = {
        "id": THEM,
        "slug": THEM,
        "kind": "service",
        "name": "Elektro Mattenhof (fictional)",
        "description": "Invented for the demo: electrical work in Bern.",
        "offers": [{"title": "electrician"}],
        "version": 1,
    }
    signature = base64.b64encode(key.sign(hive.canonical(body))).decode()
    return {**body, "trust": {"signature": signature, "public_key": public}}, {THEM: public}


def _peer_knows(pins: dict[str, str]) -> None:
    """Teach this hub bern's key registry the way the background asking would have."""
    federation.forget()
    federation._by_hub[BERN] = {"hub_id": BERN, "owner_keys": pins}


# ---------------------------------------------------------------- a failure is declared to be one


def test_an_unknown_entity_is_an_error_and_not_a_success_carrying_the_word_error(client):
    """The reproduction. `isError` is the flag a client acts on, so it is the one that has to be true."""
    refused = _call("hub_connect", {"requester": "ole-agent", "entity_id": "zzz"})

    assert refused.is_error is True
    assert "zzz" in _text(refused)


def test_the_refusal_names_which_hub_it_looked_on(client):
    """ "on this hub" is unreadable when an agent is talking to three of them."""
    refused = _call("hub_connect", {"requester": "ole-agent", "entity_id": "zzz"})

    assert config.HIVE_HUB_ID in _text(refused)
    assert "radius" in _text(refused), "and it says how to reach an entity that is on a peer"


def test_a_missing_requester_is_refused_in_words_rather_than_in_pydantic(client):
    """A validation dump tells an agent which field is wrong and nothing about what belongs in it."""
    refused = _call("hub_connect", {"entity_id": "hotel-rheinblick"})

    assert refused.is_error is True
    message = _text(refused)
    assert "validation error" not in message and "pydantic" not in message
    assert "requester" in message
    assert "does not verify" in message, "and it says what the field is worth, which is what the tester asked"


def test_a_missing_entity_id_says_where_an_id_comes_from(client):
    refused = _call("hub_connect", {"requester": "ole-agent"})

    assert refused.is_error is True
    assert "hive_discover" in _text(refused) and "not its name" in _text(refused)


def test_every_refusal_across_the_tool_surface_sets_the_flag(client):
    """`domains.base.safe` is the one place this is decided, so it holds for every tool using it."""
    for tool, args in (
        ("hive_get_card", {"card_id": "no-such-card"}),
        ("hive_check_availability", {"card_id": "no-such-card", "check_in": "2027-01-01", "check_out": "2027-01-02"}),
        ("hive_cancel", {"booking_id": "nope", "receipt": "nope"}),
        ("hive_what_was_promised", {"receipt": "nope"}),
        ("hub_score", {"connection_id": "nope", "rating": 40}),
    ):
        result = _call(tool, args)
        assert result.is_error is True, f"{tool} reported a refusal as a success"
        assert _text(result), f"{tool} refused without saying anything"


def test_safe_raises_rather_than_returning_an_error_body(client):
    """The unit under all of the above. A real bug still surfaces as itself, not as a refusal."""

    def refuse():
        raise hive.HiveError("No.")

    with pytest.raises(ToolError, match="No."):
        base.safe(refuse)
    with pytest.raises(KeyError):
        base.safe(lambda: {}["missing"])


def test_an_owner_edit_without_the_token_is_an_error_not_a_quiet_no_op(client):
    """An edit that was declined must never read as an edit that was made."""
    refused = _call("hive_owner_propose", {"card_id": "hotel-rheinblick", "instruction": "dogs welcome"})

    assert refused.is_error is True
    assert "token" in _text(refused).lower(), "and it says what is missing, whichever way the hub is configured"


def test_a_caller_that_only_reads_the_body_still_reads_the_same_message(client):
    """Nothing is withheld by this change: the message is the text content, as it was before.

    `agent.HiveConnections._call` and `tests/mcp_result.py` both turn that back into
    `{"error": ...}`, which is the shape the rest of the suite and the in-process agent expect.
    """
    refused = _call("hub_connect", {"requester": "ole-agent", "entity_id": "zzz"})

    assert tool_result(refused)["error"] == _text(refused)


# ---------------------------------------------------------------- and a success says what happens next


def test_an_open_introduction_explains_itself(client):
    """What "open" means, why the hub fields are empty, and the one call that has to come later."""
    out = tool_result(_call("hub_connect", {"requester": "Mara Keller", "entity_id": "hotel-rheinblick"}))

    assert out["state"] == connections.OPEN
    says = out["says"]
    assert "this hub" in says
    assert "target_hub" in says, "the tester's question: why is it blank when I connected to somebody"
    assert "hub_score" in says, "and the step that actually teaches this Hive something"
    assert "notified" not in says, "nothing here sends a notification, so nothing may say it did"


def test_a_request_waiting_on_an_owner_says_nobody_has_been_told(client):
    """The honest half. There is no notification in this hub, only a list somebody has to look at."""
    hive.publish(
        {
            "id": "person-quiet",
            "slug": "person-quiet",
            "kind": "person",
            "name": "Quiet Person (fictional)",
            "description": "Invented for the demo: writes documentation.",
            "offers": [{"title": "documentation"}],
        }
    )
    out = tool_result(_call("hub_connect", {"requester": "Mara Keller", "entity_id": "person-quiet"}))

    assert out["state"] == connections.REQUESTED
    says = out["says"]
    assert "Nobody is sent a message" in says
    assert "hub_connections" in says, "so an agent knows where to look instead"


def test_the_sentence_is_on_the_rest_answer_too_because_it_is_one_hub_call(client):
    """`hub.connect` is the single place this is said, so REST cannot drift from MCP."""
    out = hub.connect("Mara Keller", "hotel-rheinblick")

    assert "says" in out and "hub_score" in out["says"]


def test_a_remote_introduction_keeps_its_own_sentence_and_the_next_step_too(client):
    """Found by running two real hubs and reading the answer, which no fake would have shown.

    The remote branch replaced the whole of `says` with its own explanation, so an introduction to
    somebody on a peer came back without the one thing every introduction needs: that it expires,
    and that `hub_score` afterwards is what any of this is for.
    """
    card, pins = _remote_card()
    _peer_knows(pins)
    out = hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)

    assert "carried by bern" in out["says"], "the remote explanation is still there"
    assert "hub_score" in out["says"], "and so is the step that comes after"
    assert "runs out" in out["says"]


def test_a_remote_entity_with_no_target_hub_is_still_refused_in_words(client):
    with pytest.raises(hub.HubError, match="target_hub"):
        hub.connect("Mara Keller", "elektro-somewhere", card={"id": "elektro-somewhere"})
