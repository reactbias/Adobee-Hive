"""The Hive as an MCP server: the "homepage" an AI agent visits instead of a website.

Mounted at /mcp (Streamable HTTP). Any MCP client can connect, e.g. Claude Desktop,
Claude's MCP connector, or our own agent in app/agent.py.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import domains, hive, rulesets, waiting

server = MCPServer(
    name="Adobee Hive",
    instructions=(
        "Adobee Hive is a directory of signed, agent-facing business cards for Basel. "
        "Use hive_discover to find businesses for the user's constraints, hive_get_card to read one card and "
        "verify its Ed25519 signature, hive_check_availability before booking, and hive_book to complete a booking. "
        "Only state facts that come from cards. Tell the user why you picked a business (score_breakdown, why) "
        "and keep the booking receipt: it is needed to cancel or to leave a verified review. "
        "If nothing fits and the user wants to be told, hive_wait leaves an anonymous standing request."
    ),
)


_safe = domains.safe


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
) -> dict[str, Any]:
    """Find local businesses in the Hive.

    kind: hotel | cafe. near: a landmark such as 'basel sbb', 'messe basel', 'marktplatz', 'badischer bahnhof'.
    features: exact tags such as 'dog-friendly', 'late check-in', 'quiet', 'breakfast', 'parking'.
    Dates are ISO (YYYY-MM-DD). Returns ranked matches with score_breakdown and why, plus excluded
    businesses with why_not, so you can explain the choice to the user.
    ruleset: only one your user chose (see hive_rulesets). The answer names it and what it changed; tell the user.
    """
    found = _safe(hive.discover, query, kind, near, max_price_chf, features, check_in, check_out, guests)
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
    return _safe(hive.get_card, card_id)


@server.tool()
def hive_check_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    """List the units (rooms) free for these ISO dates and guest count, cheapest first, with totals in CHF."""
    return _safe(hive.check_availability, card_id, check_in, check_out, guests)


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
