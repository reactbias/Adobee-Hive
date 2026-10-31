"""The docs are a map of what runs: every endpoint, MCP tool and page in the app has a row in ARCHITECTURE.md."""

import asyncio
import re
from pathlib import Path

from fastapi.routing import APIRoute
from mcp import Client

from app.main import app
from app.mcp_server import server

ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = (ROOT / "documentation" / "ARCHITECTURE.md").read_text(encoding="utf-8")
FRONTEND_ROUTES = (ROOT / "code" / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")


def _section(title: str) -> str:
    """The text of one `## ` section of ARCHITECTURE.md."""
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", ARCHITECTURE, re.S | re.M)
    assert match, f"ARCHITECTURE.md has no section '## {title}'"
    return match.group(1)


def _first_cells(title: str) -> set[str]:
    """The first column of every table row in a section, without its backticks."""
    rows = re.findall(r"^\| `([^`]+)` \|", _section(title), re.M)
    return set(rows)


def test_every_endpoint_is_documented():
    served = {f"{m} {r.path}" for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    documented = _first_cells("REST API")
    assert served - documented == set(), "add these to the REST API table in ARCHITECTURE.md"
    assert documented - served == set(), "these are documented but not served"


def test_every_mcp_tool_is_documented(client):
    async def tools() -> set[str]:
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    served, documented = asyncio.run(tools()), _first_cells("MCP tools (`/mcp/`, Streamable HTTP)")
    assert served - documented == set(), "add these to the MCP tools table in ARCHITECTURE.md"
    assert documented - served == set(), "these are documented but not served"


def test_every_page_is_documented():
    served = set(re.findall(r'<Route path="([^"]+)"', FRONTEND_ROUTES))
    documented = _first_cells("Pages")
    assert served, "no routes found in main.tsx"
    assert served - documented == set(), "add these to the Pages table in ARCHITECTURE.md"
    assert documented - served == set(), "these are documented but not routed"


def test_the_interactive_api_docs_are_served(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/agent" in paths and "/api/health" in paths
