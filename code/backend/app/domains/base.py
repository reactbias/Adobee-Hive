"""Helpers shared by every domain's MCP tools."""

from typing import Any

from .. import hive


def safe(fn, *args, **kwargs) -> dict[str, Any]:
    """Run a Hive call for an MCP tool; a refused request becomes {"error": ...} instead of a failed call."""
    try:
        return fn(*args, **kwargs)
    except hive.HiveError as err:
        return {"error": str(err)}
