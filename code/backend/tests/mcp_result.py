"""Read one MCP tool result the way a client does, whichever way the call ended."""

from __future__ import annotations

import json
from typing import Any


def tool_result(result: Any) -> dict[str, Any]:
    """A tool result as a dict: its structured content, or `{"error": <message>}` for a refusal.

    A refused call arrives with `isError` set and the message as text, because `domains.base.safe`
    raises `ToolError` and that is what sets the flag (#155: it used to return `{"error": ...}`,
    which is a *successful* result whose body happens to contain the word error, so a client that
    checks the flag read a refusal as a success).

    So the suite reads a result the way `agent.HiveConnections._call` already does, and a test that
    asserts on `["error"]` is asserting about something the protocol has actually marked as an
    error rather than about a string in a success.
    """
    if getattr(result, "is_error", False):
        return {"error": result.content[0].text if result.content else ""}
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    return json.loads(result.content[0].text)
