"""Tests for the consented HR CV exchange over the existing Hive link."""

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import Client

from app import config, db, folder_keys, folders, hive, hub
from app.domains import hr
from app.mcp_server import server

ROOT = Path(__file__).resolve().parents[3]
VAULTS = ROOT / "testdata" / "vaults"
OWNER_TOKEN = "fictional-owner-token"


@pytest.fixture(autouse=True)
def clean_slate(client, monkeypatch):
    """Use the fictional Anouk vault and leave HR links and cards isolated per test."""
    monkeypatch.setattr(config, "FOLDER_LINK", "local")
    monkeypatch.setattr(config, "FOLDER_ROOT", VAULTS)
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", OWNER_TOKEN)
    folders.reset()
    with db.write() as cur:
        for table in ("folder_links", "folder_grants", "folder_handles", "folder_keys", "hub_connections"):
            cur.execute(f"DELETE FROM {table}")
    hive.publish(
        {
            "id": "anouk-pfister",
            "slug": "anouk-pfister",
            "kind": "person",
            "name": "Anouk Pfister (fictional)",
            "headline": "Product designer and Python developer",
            "description": "Product designer and Python developer in Basel.",
            "skills": ["python", "product design"],
            "languages": ["de", "en"],
            "availability": "from 2027-01",
            "location": "Basel",
            "sharing": "confirm",
        }
    )
    yield
    folders.reset()


def _ctx(**headers: str) -> SimpleNamespace:
    """Build the small MCP context shape used by the HR tools."""
    return SimpleNamespace(headers=headers)


def test_hr_agent_can_retrieve_a_cv_only_after_candidate_consent_and_grant(client):
    """A signed person card and a connection do not make the CV readable by themselves."""
    connection = hub.connect("hiring-agent", "anouk-pfister")
    requester_secret = connection["folder_key"]["secret"]
    assert connection["state"] == "requested"
    with pytest.raises(hive.HiveError, match="connected folder link"):
        hr.read_cv("cv.pdf", _ctx(Authorization=f"Bearer {requester_secret}"))

    candidate_secret = folder_keys.mint(connection["folder_link"], "anouk-pfister", pending_ok=True)["secret"]
    approved = hr.decide_intro(
        connection["id"],
        approve=True,
        ctx=_ctx(**{"X-Owner-Token": OWNER_TOKEN}),
    )
    assert approved["state"] == "open"

    grant = hr.grant_cv("cv.pdf", _ctx(Authorization=f"Bearer {candidate_secret}"))
    assert grant["path"] == "cv.pdf" and grant["to"] == "hiring-agent"

    result = hr.read_cv("cv.pdf", _ctx(Authorization=f"Bearer {requester_secret}"))
    assert result["media_type"] == "application/pdf"
    assert base64.b64decode(result["content_base64"]).startswith(b"%PDF")


def test_hr_cv_tools_are_exposed_over_mcp(client):
    """The HR workflow is available through the same MCP server as hotel booking."""

    async def tools():
        async with Client(server) as mcp:
            return {tool.name for tool in (await mcp.list_tools()).tools}

    assert {"hr_decide_intro", "hr_grant_cv", "hr_read_cv"} <= asyncio.run(tools())


def test_hr_job_is_created_and_granted_cv_is_submitted_to_hiring_hub(client, monkeypatch):
    """The adapter creates a position and uploads only a consented CV to it."""
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": 41, "title": "Python Engineer"}

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(config, "HIRING_HUB_URL", "http://hiring.test")
    monkeypatch.setattr(config, "HIRING_HUB_API_KEY", "hiring-secret")
    monkeypatch.setattr(hr.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))

    position = hr.create_job_posting(
        {"title": "Python Engineer", "description": "Build hiring tools.", "custom_fields": []}
    )
    assert position["id"] == 41

    connection = hub.connect("hiring-agent", "anouk-pfister")
    candidate_secret = folder_keys.mint(connection["folder_link"], "anouk-pfister", pending_ok=True)["secret"]
    hr.decide_intro(connection["id"], approve=True, ctx=_ctx(**{"X-Owner-Token": OWNER_TOKEN}))
    hr.grant_cv("cv.pdf", _ctx(Authorization=f"Bearer {candidate_secret}"))
    submitted = hr.submit_cv(
        41,
        "cv.pdf",
        _ctx(Authorization=f"Bearer {connection['folder_key']['secret']}"),
    )

    assert submitted["position_id"] == 41
    assert calls[1][0] == "/positions"
    assert calls[3][0] == "/positions/41/cvs"
    assert calls[0][1]["headers"] == {"x-api-key": "hiring-secret"}
    assert calls[3][1]["files"]["files"][0] == "cv.pdf"
