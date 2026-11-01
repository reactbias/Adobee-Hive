"""Helpers shared by every domain's MCP tools."""

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from .. import blocklist, connections, hive


def safe(fn, *args, **kwargs) -> dict[str, Any]:
    """Run a Hive call for an MCP tool; a refusal becomes a tool error the protocol marks as one.

    `ToolError` is what sets `isError` on the result. Returning `{"error": ...}` instead — which is
    what this did — hands the caller a **successful** result whose body happens to contain the word
    error, so a client that checks `isError`, which is every well-behaved one, reads a refusal as a
    success. A user test found `hub_connect` answering "no entity 'zzz' on this hub" with
    `isError: false`, and an agent that trusted the flag would have told its person it had worked.

    The message is unchanged and still arrives as text, so a caller that only reads the body reads
    exactly what it read before. What changes is that the failure is now declared to be one.
    """
    try:
        return fn(*args, **kwargs)
    except (hive.HiveError, connections.ConnectionError_, blocklist.BlockError) as err:
        raise ToolError(str(err)) from err
    except ValueError as err:  # hub.HubError and anything else a caller got wrong
        raise ToolError(str(err)) from err
