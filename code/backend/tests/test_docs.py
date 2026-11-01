"""The docs are a map of what runs: every endpoint, MCP tool and panel of the app has a row in ARCHITECTURE.md."""

import asyncio
import re
from pathlib import Path

from fastapi.routing import APIRoute
from mcp import Client

from app.main import app
from app.mcp_server import server

ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = (ROOT / "documentation" / "ARCHITECTURE.md").read_text(encoding="utf-8")
FRONTEND = ROOT / "code" / "frontend" / "src"


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


def test_the_app_is_one_page_and_every_panel_is_documented():
    pages = {p.name for p in (FRONTEND / "pages").glob("*.tsx") if not p.name.endswith(".test.tsx")}
    panels = {p.name for p in (FRONTEND / "panels").glob("*.tsx") if not p.name.endswith(".test.tsx")}
    assert pages == {"TravellerAgent.tsx"}, "the app is one page; fold new views into it as a panel"
    assert "<Route" not in (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    documented = _first_cells("The page")
    assert panels, "no panels found"
    assert panels - documented == set(), "add these to the table under 'The page' in ARCHITECTURE.md"
    assert documented - panels == set(), "these are documented but not in src/panels"


def test_the_interactive_api_docs_are_served(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/agent" in paths and "/api/health" in paths


def _anchor(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_every_link_between_the_docs_resolves():
    broken = []
    for doc in [ROOT / "readme.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "documentation").glob("*.md"))]:
        for target in re.findall(r"\]\(([^)\s]+)\)", doc.read_text(encoding="utf-8")):
            if re.match(r"[a-z]+:", target):
                continue  # web links are checked by people, not by CI
            path, _, anchor = target.partition("#")
            file = (doc.parent / path).resolve() if path else doc
            if not file.exists():
                broken.append(f"{doc.name}: {target}")
            elif anchor and file.suffix == ".md":
                headings = re.findall(r"^#+ (.+)$", file.read_text(encoding="utf-8"), re.M)
                if anchor not in {_anchor(h) for h in headings}:
                    broken.append(f"{doc.name}: {target}")
    assert broken == []


def test_the_developer_guide_names_only_what_runs(client):
    guide = (ROOT / "documentation" / "DEVELOPER.md").read_text(encoding="utf-8")

    async def tools() -> set[str]:
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    served_tools = asyncio.run(tools())
    named_tools = set(re.findall(r"\b((?:hive|hr|explore)_[a-z_]+)\b(?!\.)", guide))  # not file names
    assert named_tools - served_tools == set(), "the guide names MCP tools the server does not have"

    served_paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    named_paths = {re.sub(r"/(hotel|cafe)-[a-z]+", "/{card_id}", p) for p in re.findall(r"(/api/[a-z/{}_-]+)", guide)}
    assert named_paths - served_paths == set(), "the guide names endpoints the backend does not serve"


def test_the_diagrams_name_only_what_exists(client):
    diagrams = (ROOT / "documentation" / "DIAGRAMS.md").read_text(encoding="utf-8")

    files = set(re.findall(r"(?<![\w.-])([\w-]+(?:\.test)?\.(?:py|tsx|ts|yml|yaml))\b", diagrams))
    repo = {p.name for p in ROOT.rglob("*") if "node_modules" not in p.parts and ".git" not in p.parts}
    assert files - repo == set(), "the diagrams name files that do not exist"

    async def tools() -> set[str]:
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    named_tools = set(re.findall(r"\b((?:hive|hr|explore)_[a-z_]+)\b(?!\.)", diagrams))
    assert named_tools - asyncio.run(tools()) == set(), "the diagrams name MCP tools the server does not have"
    served_paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert set(re.findall(r"(/api/[a-z/{}_-]*[a-z}])", diagrams)) - served_paths == set()


def test_every_module_tool_and_endpoint_is_in_the_diagrams(client):
    """Agents keep the pictures true: a new module, MCP tool or endpoint fails CI until DIAGRAMS.md shows it."""
    diagrams = (ROOT / "documentation" / "DIAGRAMS.md").read_text(encoding="utf-8")
    app_dir = ROOT / "code" / "backend" / "app"
    modules = {p.name for p in app_dir.rglob("*.py") if p.name != "__init__.py"}
    drawn = set(re.findall(r"(?<![\w.-])(\w+\.py)\b", diagrams))
    assert modules - drawn == set(), "draw these modules in documentation/DIAGRAMS.md"

    async def tools() -> set[str]:
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert {
        t for t in asyncio.run(tools()) if not re.search(rf"\b{t}\b", diagrams)
    } == set(), "draw these MCP tools in documentation/DIAGRAMS.md"
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert {
        p for p in paths if not re.search(re.escape(p) + r"(?![\w/{}-])", diagrams)
    } == set(), "draw these endpoints in documentation/DIAGRAMS.md"
