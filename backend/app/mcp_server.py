"""The Hive as an MCP server: the "homepage" an AI agent visits instead of a website.

Mounted at /mcp (Streamable HTTP). Any MCP client can connect, e.g. Claude Desktop,
Claude's MCP connector, or our own agent in app/agent.py.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from . import hive

server = MCPServer(
    name="AdoBee Hive",
    instructions=(
        "AdoBee Hive is a directory of signed, agent-facing business cards for Basel. "
        "Use hive_discover to find businesses for the user's constraints, hive_get_card to read one card and "
        "verify its Ed25519 signature, hive_check_availability before booking, and hive_book to complete a booking. "
        "Only state facts that come from cards. Tell the user why you picked a business (score_breakdown, why) "
        "and keep the booking receipt: it is needed to cancel or to leave a verified review."
    ),
)


def _safe(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except hive.HiveError as err:
        return {"error": str(err)}


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
) -> dict[str, Any]:
    """Find local businesses in the Hive.

    kind: hotel | cafe. near: a landmark such as 'basel sbb', 'messe basel', 'marktplatz', 'badischer bahnhof'.
    features: exact tags such as 'dog-friendly', 'late check-in', 'quiet', 'breakfast', 'parking'.
    Dates are ISO (YYYY-MM-DD). Returns ranked matches with score_breakdown and why, plus excluded
    businesses with why_not, so you can explain the choice to the user.
    """
    return _safe(hive.discover, query, kind, near, max_price_chf, features, check_in, check_out, guests)


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
    card_id: str, unit_id: str, check_in: str, check_out: str, guest_name: str,
    guests: int = 1, notes: str = "", agent: str = "MCP agent",
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


def http_app():
    # Behind App Runner / Amplify the Host header is the public domain, so host checks are off;
    # the MCP surface only exposes the public card data and booking actions above.
    return server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
