"""The Hive as an MCP server: the "homepage" an AI agent visits instead of a website.

Mounted at /mcp (Streamable HTTP). Any MCP client can connect, e.g. Claude Desktop,
Claude's MCP connector, or our own agent in app/agent.py.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import admin, connections, domains, hive, hub, registration, rulesets, waiting

server = MCPServer(
    name="Adobee Hive",
    instructions=(
        "Adobee Hive is a directory of signed, agent-facing business cards for Basel. "
        "Use hive_discover to find businesses for the user's constraints, hive_get_card to read one card and "
        "verify its Ed25519 signature, hive_check_availability before booking, and hive_book to complete a booking. "
        "Only state facts that come from cards. Tell the user why you picked a business (score_breakdown, why) "
        "and keep the booking receipt: it is needed to cancel or to leave a verified review. "
        "If nothing fits and the user wants to be told, hive_wait leaves an anonymous standing request. "
        "To reach a person rather than book a room, use hub_connect: some entries open at once and some wait "
        "for their owner's yes. After the real meeting has happened, hub_score records how it actually went, "
        "which is the only thing that teaches this Hive which other Hives to believe."
    ),
)


_safe = domains.safe


def _counted(out: dict[str, Any], kind: str) -> dict[str, Any]:
    """Count an agent's call against the card it touched, so its owner sees it; errors count for nothing."""
    card_id = out.get("card_id") or out.get("id")
    if "error" not in out and card_id:
        hive.record_event(card_id, kind, "agent")
    return out


@server.tool()
def hive_discover(
    query: str = "",
    kind: str | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    features: list[str] | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = 1,
    ruleset: str | None = None,
    radius: int = 0,
) -> dict[str, Any]:
    """Find local businesses in the Hive.

    kind: hotel | cafe. near: a landmark such as 'basel sbb', 'messe basel', 'marktplatz', 'badischer bahnhof'.
    features: exact tags such as 'dog-friendly', 'late check-in', 'quiet', 'breakfast', 'parking'.
    Dates are ISO (YYYY-MM-DD). Returns ranked matches with score_breakdown and why, plus excluded
    businesses with why_not, so you can explain the choice to the user.
    ruleset: only one your user chose (see hive_rulesets). The answer names it and what it changed; tell the user.
    radius: how far to look. 0 (the default) is this Hive only. 1 also asks its peer Hives, 2 their peers, up to 3.
    Above 0 each match says in provenance which hubs it travelled and how many hops, and its score_breakdown adds
    local_relevance, hub_path_trust and hop_decay; tell the user when a business came from another Hive.
    """
    found = _safe(hive.discover, query, kind, near, max_price_chf, features, check_in, check_out, guests, radius)
    return found if "error" in found or not ruleset else _safe(rulesets.apply, found, ruleset)


@server.tool()
def hive_what_was_promised(receipt: str) -> dict[str, Any]:
    """Show the signed card version a booking was made against (prices, policies), and which fields changed since.
    Use it when the stay differs from what was booked. Verify the old card against the owner's pinned key."""
    return _safe(hive.what_was_promised, receipt)


@server.tool()
def hive_rulesets() -> dict[str, Any]:
    """List the rulesets a user can choose for hive_discover, each signed by its author (keys in
    /.well-known/hive.json under ruleset_keys). A ruleset only narrows results; it never boosts a business."""
    return rulesets.catalogue()


@server.tool()
def hive_get_card(card_id: str) -> dict[str, Any]:
    """Read one business's full Hive card: offering, units and prices, policies, contact, and trust
    (signature, public key, third-party attestations, proof-of-stay reviews)."""
    return _counted(_safe(hive.get_card, card_id), "read")


@server.tool()
def hive_check_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    """List the units (rooms) free for these ISO dates and guest count, cheapest first, with totals in CHF."""
    return _counted(_safe(hive.check_availability, card_id, check_in, check_out, guests), "checked")


@server.tool()
def hive_book(
    card_id: str,
    unit_id: str,
    check_in: str,
    check_out: str,
    guest_name: str,
    guests: int = 1,
    notes: str = "",
    agent: str = "MCP agent",
) -> dict[str, Any]:
    """Book a unit. Only call this after the user has agreed to the business, room, dates and price.
    Returns a confirmation with a signed receipt (keep it for cancel and review)."""
    return _safe(hive.book, card_id, unit_id, check_in, check_out, guest_name, guests, notes, agent)


@server.tool()
def hive_cancel(booking_id: str, receipt: str) -> dict[str, Any]:
    """Cancel a booking. Requires the signed receipt returned by hive_book."""
    return _safe(hive.cancel, booking_id, receipt)


@server.tool()
def hive_review(receipt: str, rating: int, text: str) -> dict[str, Any]:
    """Leave a verified review (1-5) for a stay. Requires the booking's signed receipt."""
    return _safe(hive.review, receipt, rating, text)


@server.tool()
def hive_wait(
    check_in: str,
    check_out: str,
    features: list[str] | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    guests: int = 1,
) -> dict[str, Any]:
    """When hive_discover found nothing that fits, and only if your user wants to be told: leave an anonymous
    standing request. If a business later changes its signed card to fit, it sends a signed offer. Returns a
    request_id and a secret token; keep both. Never include the user's name or words."""
    return _safe(waiting.leave, features, near, max_price_chf, check_in, check_out, guests)


@server.tool()
def hive_check_waiting(request_id: str, token: str) -> dict[str, Any]:
    """Check a standing request. Offers are signed by the business; verify them against its pinned key and ask
    your user before booking with hive_book."""
    return _safe(waiting.check, request_id, token)


# The stays tools above came first; every other use case registers its tools from app/domains.
domains.register_all(server)


def http_app():
    """Return the MCP server as an ASGI app for Streamable HTTP, mounted at /mcp."""
    # Behind the hosting proxy the Host header is the public domain, so host checks are off;
    # the MCP surface only exposes public card data and actions that don't reveal private data.
    return server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


@server.tool()
def hub_connect(requester: str, entity_id: str, target_hub: str = "", via_hub: str = "") -> dict[str, Any]:
    """Ask to be introduced to a business or person found in a search, and log the introduction.

    An entry marked public opens at once; one marked `needs_confirmation` waits for its owner's yes; one its
    owner shares only on their own initiative cannot be asked for at all. Returns the connection and its state.
    Keep the connection id: it is what hub_score needs later."""
    return _safe(hub.connect, requester, entity_id, target_hub=target_hub, via_hub=via_hub)


@server.tool()
def hub_score(connection_id: str, rating: int, note: str = "") -> dict[str, Any]:
    """Record how an introduction actually went, after the real meeting, from the person who asked for it.

    `rating` is tenths of a star out of five: 43 means 4.3 stars. Scoring is once and final, and only while the
    connection is still open — an introduction nobody scored within a month closes unscored. This is the only
    input to how much this Hive trusts the Hive the entry came from, so ask the person, never guess."""
    return _safe(hub.score, connection_id, rating, note)


@server.tool()
def hub_connections(requester: str = "") -> dict[str, Any]:
    """List introductions still waiting on somebody: on an owner's yes, or on the person's score.

    Use it to ask "how did it go with X?" before the connection goes stale and can no longer be scored."""
    return {
        "awaiting_rating": connections.awaiting_rating(requester),
        "awaiting_confirmation": connections.pending_confirmation(),
    }


@server.tool()
def hub_standing() -> dict[str, Any]:
    """What this Hive makes of its neighbours, from how their ratings held up against real meetings.

    `error` is published minus realised, in tenths of a star: lower is better, negative means the Hive
    undersold what it offered. A Hive with too little evidence is reported as unproven rather than guessed at."""
    return hub.standing()


@server.tool()
def hub_registration() -> dict[str, Any]:
    """Read what this Hive asks of someone who wants to join, before writing an application.

    Returns the admission policy, the checks an application goes through, the proof types accepted, and an
    example document. Read this first: a hub may be invite-only or closed, and the answer says so."""
    return registration.policy()


@server.tool()
def hub_register(
    entity: dict[str, Any],
    public_key: str = "",
    proofs: list[dict[str, Any]] | None = None,
    invite: str = "",
    signature: str = "",
) -> dict[str, Any]:
    """Apply to join this Hive on behalf of your user, with one signed JSON document.

    `entity` is the card: id, kind, name, description, sharing. Bring a `public_key` and your user keeps the
    private half — sign the canonical JSON of the whole application except `signature` to prove they hold it.
    Omit the key and this Hive generates and holds one, which is weaker and is recorded as such.

    A refusal is an answer, not a failure: the reply always carries the checks, the reason and what to do next.
    Never invent proofs — they are claims about the world and a hub that catches a false one will block you."""
    return _safe(
        registration.apply,
        {"entity": entity, "public_key": public_key, "proofs": proofs or [], "invite": invite, "signature": signature},
    )


@server.tool()
def hub_directory() -> dict[str, Any]:
    """List the Hives this one knows of, so a user can choose which to join before applying.

    Each row says whether it is taking members, what it asks of them, and how closely its published ratings
    have matched what real people found: `error` is published minus realised, and lower is better."""
    return admin.directory()
