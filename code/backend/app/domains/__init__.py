"""Use cases ("domains") built on the Hive core.

The core (`hive.py`) knows signed cards, trust, events and bookings; a domain adds its own card kind and MCP tools.
Stays (hotels, cafés) are the first domain; their tools live in `mcp_server.py` because they came first. Every
other domain is a module here with a `register(server)` function, listed in DOMAINS. See CONTRIBUTING.md,
"Add a use case".
"""

from mcp.server.mcpserver import MCPServer

from . import explore, hr, scout
from .base import safe

__all__ = ["DOMAINS", "register_all", "safe"]

DOMAINS = [hr, explore, scout]


def register_all(server: MCPServer) -> None:
    """Add every domain's MCP tools to the server."""
    for domain in DOMAINS:
        domain.register(server)
