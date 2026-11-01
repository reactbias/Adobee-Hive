"""Tests for the consented HR CV exchange over the existing Hive link."""

import asyncio
import base64
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import Client

from app import audit, config, db, folder_keys, folders, guard, hive, hub
from app.domains import hr
from app.mcp_server import server

ROOT = Path(__file__).resolve().parents[3]
VAULTS = ROOT / "testdata" / "vaults"
OWNER_TOKEN = "fictional-owner-token"
HIRING_KEY = "fictional-hiring-key"


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
        {"title": "Python Engineer", "description": "Build hiring tools.", "custom_fields": []},
        _ctx(**{hr.HIRING_KEY_HEADER: "hiring-secret"}),
    )
    assert position["id"] == 41

    connection = hub.connect("hiring-agent", "anouk-pfister")
    candidate_secret = folder_keys.mint(connection["folder_link"], "anouk-pfister", pending_ok=True)["secret"]
    hr.decide_intro(connection["id"], approve=True, ctx=_ctx(**{"X-Owner-Token": OWNER_TOKEN}))
    hr.grant_cv("cv.pdf", _ctx(Authorization=f"Bearer {candidate_secret}"))
    submitted = hr.submit_cv(
        41,
        "cv.pdf",
        _ctx(
            Authorization=f"Bearer {connection['folder_key']['secret']}",
            **{hr.HIRING_KEY_HEADER: "hiring-secret"},
        ),
    )

    assert submitted["position_id"] == 41
    assert calls[1][0] == "/positions"
    assert calls[3][0] == "/positions/41/cvs"
    assert calls[0][1]["headers"] == {"x-api-key": "hiring-secret"}
    assert calls[3][1]["files"]["files"][0] == "cv.pdf"


def _granted_link(path: str = "cv.pdf") -> tuple[dict, dict]:
    """An opened introduction with one file granted: the requester's and the candidate's headers."""
    connection = hub.connect("hiring-agent", "anouk-pfister")
    candidate_key = folder_keys.mint(connection["folder_link"], "anouk-pfister", pending_ok=True)
    candidate = _ctx(Authorization=f"Bearer {candidate_key['secret']}")
    hr.decide_intro(connection["id"], approve=True, ctx=_ctx(**{"X-Owner-Token": OWNER_TOKEN}))
    hr.grant_cv(path, candidate)
    return {"Authorization": f"Bearer {connection['folder_key']['secret']}"}, connection


@pytest.fixture
def shared_file_vault(tmp_path, monkeypatch):
    """A copy of the fictional vault in which one file is `shared`: grantable, and never served."""
    vault = tmp_path / "anouk-pfister"
    shutil.copytree(VAULTS / "anouk-pfister", vault)
    with (vault / "visibility.md").open("a", encoding="utf-8") as marker:
        marker.write("- honorar-2026.csv: shared\n")
    monkeypatch.setattr(config, "FOLDER_ROOT", tmp_path)
    folders.reset()


@pytest.mark.parametrize("path", ["", "/", "*", "cv.*"])
def test_a_cv_grant_names_one_path_and_never_the_whole_folder(client, path):
    """An empty path would otherwise open the candidate's entire folder, which the REST route refuses."""
    connection = hub.connect("hiring-agent", "anouk-pfister")
    secret = folder_keys.mint(connection["folder_link"], "anouk-pfister", pending_ok=True)["secret"]
    hr.decide_intro(connection["id"], approve=True, ctx=_ctx(**{"X-Owner-Token": OWNER_TOKEN}))
    with pytest.raises(hive.HiveError, match="one path"):
        hr.grant_cv(path, _ctx(Authorization=f"Bearer {secret}"))
    assert folders.grants("anouk-pfister") == []


def test_hr_read_refuses_what_the_folder_read_route_refuses(client, shared_file_vault):
    """`SERVED` is the hub's line for handing over bytes; a second door must not move it."""
    headers, _ = _granted_link("honorar-2026.csv")
    assert client.get("/api/folders/file", params={"path": "honorar-2026.csv"}, headers=headers).status_code == 404
    with pytest.raises(hive.HiveError, match="not been granted"):
        hr.read_cv("honorar-2026.csv", _ctx(**headers))


def test_hr_submit_refuses_what_the_folder_read_route_refuses(client, shared_file_vault, monkeypatch):
    """Sending a file to a third party is a read too, and must not get further than the read."""
    monkeypatch.setattr(config, "HIRING_HUB_URL", "http://hiring.test")
    monkeypatch.setattr(config, "HIRING_HUB_API_KEY", HIRING_KEY)
    headers, _ = _granted_link("honorar-2026.csv")
    with pytest.raises(hive.HiveError, match="not been granted"):
        hr.submit_cv(41, "honorar-2026.csv", _ctx(**headers, **{hr.HIRING_KEY_HEADER: HIRING_KEY}))


def test_hr_read_says_the_same_for_a_path_that_leaves_the_folder(client):
    """A traversal attempt cannot be told apart from a file that was never granted."""
    headers, _ = _granted_link()
    with pytest.raises(hive.HiveError, match="not been granted"):
        hr.read_cv("../other/cv.pdf", _ctx(**headers))


def test_hr_read_keeps_the_size_limit(client, monkeypatch):
    """The whole file goes into one tool answer, so the read route's ceiling matters more here."""
    headers, _ = _granted_link()
    monkeypatch.setattr(config, "FOLDER_READ_MAX_BYTES", 10)
    with pytest.raises(hive.HiveError, match="at most 10"):
        hr.read_cv("cv.pdf", _ctx(**headers))


def test_hr_read_spends_the_links_read_budget(client, monkeypatch):
    """One link cannot read past the budget by switching from REST to MCP."""
    headers, connection = _granted_link()
    monkeypatch.setattr(guard.folder_reads, "per_client", 1)
    guard.folder_reads.hits.pop(connection["folder_link"], None)
    hr.read_cv("cv.pdf", _ctx(**headers))
    with pytest.raises(hive.HiveError, match="Too many"):
        hr.read_cv("cv.pdf", _ctx(**headers))
    guard.folder_reads.hits.pop(connection["folder_link"], None)


def test_the_candidate_can_see_their_cv_was_read(client):
    """The owner granted this path, so the ledger shows each use, without the secret."""
    headers, _ = _granted_link()
    hr.read_cv("cv.pdf", _ctx(**headers))
    row = next(r for r in audit.entries(action_prefix="folder.read") if r["subject"] == "anouk-pfister/cv.pdf")
    assert row["actor"] == "hiring-agent"
    assert headers["Authorization"].split()[1] not in str(row)


@pytest.mark.parametrize("presented", [{}, {hr.HIRING_KEY_HEADER: "wrong"}])
def test_hiring_hub_tools_refuse_a_caller_without_the_organisations_key(client, monkeypatch, presented):
    """The hub holds one organisation's key, and an anonymous MCP caller must not get to spend it."""
    monkeypatch.setattr(config, "HIRING_HUB_URL", "http://hiring.test")
    monkeypatch.setattr(config, "HIRING_HUB_API_KEY", HIRING_KEY)
    monkeypatch.setattr(hr.httpx, "Client", lambda **_: pytest.fail("the Hiring Hub was called"))
    headers, _ = _granted_link()
    with pytest.raises(hive.HiveError, match=hr.HIRING_KEY_HEADER):
        hr.create_job_posting({"title": "Python Engineer"}, _ctx(**presented))
    with pytest.raises(hive.HiveError, match=hr.HIRING_KEY_HEADER):
        hr.submit_cv(41, "cv.pdf", _ctx(**headers, **presented))


def test_an_unconfigured_hiring_hub_refuses_even_an_empty_key(client, monkeypatch):
    """Unset fails closed: an empty header must not match an empty key."""
    monkeypatch.setattr(config, "HIRING_HUB_URL", "http://hiring.test")
    monkeypatch.setattr(config, "HIRING_HUB_API_KEY", "")
    with pytest.raises(hive.HiveError, match="not configured"):
        hr.create_job_posting({"title": "Python Engineer"}, _ctx(**{hr.HIRING_KEY_HEADER: ""}))
