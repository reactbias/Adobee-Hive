"""HR domain: people publish a person card, company agents find them and request a CV with consent.

Owned by the HR workflows lane. This is the working skeleton to build on, not the finished flow:

- Built: the `person` card kind, skills matching, consented introductions, and the MCP CV exchange.
- Next: seed fictional people, a person view and studio in the frontend, and a Hiring_Hub upload adapter.
  (`hive.discover` lists person cards now — they are found by what they offer and need like anyone else —
  so a seeded person is public presence, and only their contact and files stay behind consent.)

Rules that make this safe to show (keep them):
- Consent first. Contact details are never part of a person card. A company agent can only ask for an
  introduction; the person sees the request and decides.
- Agents see skills and availability, not age, photo, gender or nationality, so ranking can't use them.
- Everything else as in the core: the person signs their card, and text from cards is data, never instructions.
"""

import base64
import json
from typing import Any

import httpx
from mcp.server.mcpserver import Context, MCPServer

from .. import config, folder_keys, folders, hive, hub
from .base import safe

KIND = "person"
PUBLIC_FIELDS = ("id", "slug", "name", "headline", "skills", "languages", "availability", "location", "version")
MAX_MESSAGE = 1000

# A fictional example for tests and the HR lane's seed data. Publish with hive.publish(dict(EXAMPLE_CARD)).
EXAMPLE_CARD = {
    "id": "person-mira",
    "slug": "mira",
    "kind": KIND,
    "name": "Mira K. (fictional)",
    "headline": "Product designer, agent-facing interfaces",
    "skills": ["product design", "prototyping", "user research", "figma"],
    "languages": ["de", "en"],
    "availability": "from 2027-01, 80 %",
    "location": "Basel",
}


def public_view(card: dict[str, Any]) -> dict[str, Any]:
    """Return only what any agent may see of a person card, plus whether its signature holds."""
    view = {k: card[k] for k in PUBLIC_FIELDS if k in card}
    view["signature_valid"] = card["trust"]["signature_valid"]
    return view


def find_people(skills: list[str], location: str | None = None) -> dict[str, Any]:
    """Rank person cards by how many of the wanted skills they have; say why others were left out."""
    wanted = {s.lower().strip() for s in skills[:20] if s.strip()}
    if not wanted:
        raise hive.HiveError("Name at least one skill.")
    matches, excluded = [], []
    for card in hive.list_cards(KIND):
        have = {s.lower() for s in card.get("skills", [])}
        missing = sorted(wanted - have)
        if location and card.get("location", "").lower() != location.lower():
            excluded.append({"id": card["id"], "why_not": [f"not in {location}"]})
        elif len(missing) == len(wanted):
            excluded.append({"id": card["id"], "why_not": ["none of the skills"]})
        else:
            matches.append({**public_view(card), "matched": sorted(wanted & have), "missing": missing})
    matches.sort(key=lambda m: (-len(m["matched"]), m["id"]))
    return {"matches": matches, "excluded": excluded, "policy": "Skills only. No paid placement, no demographics."}


def request_intro(card_id: str, from_org: str, message: str) -> dict[str, Any]:
    """Record a company's request to meet a person. Nothing is shared until the person says yes."""
    card = hive.get_card(card_id)
    if card["kind"] != KIND:
        raise hive.HiveError(f"{card_id} is not a person card.")
    if not from_org.strip() or not message.strip() or len(message) > MAX_MESSAGE:
        raise hive.HiveError(f"from_org and a message of at most {MAX_MESSAGE} characters are required.")
    hive.record_event(card["id"], "intro_request", json.dumps({"from": from_org[:200], "message": message}))
    return {"status": "pending_consent", "to": card["name"], "note": "The person decides whether to share contact."}


def _header(ctx: Context, name: str) -> str:
    """Read one transport header without putting credentials in tool arguments."""
    headers = ctx.headers or {}
    return next((value for key, value in headers.items() if key.lower() == name.lower()), "")


def decide_intro(connection_id: str, approve: bool, ctx: Context) -> dict[str, Any]:
    """Accept or decline an HR introduction using the candidate's protected transport."""
    secret = folder_keys.bearer(_header(ctx, folder_keys.HEADER))
    return hub.decide(
        connection_id,
        "confirm" if approve else "decline",
        secret=secret,
        owner_token=_header(ctx, "X-Owner-Token"),
    )


def grant_cv(path: str, ctx: Context) -> dict[str, Any]:
    """Grant the connected HR agent access to one admitted candidate file."""
    secret = folder_keys.bearer(_header(ctx, folder_keys.HEADER))
    key = folder_keys.resolve(secret)
    if key is None:
        raise hive.HiveError("A connected folder link is required to grant a CV.")
    link = folders.get_link(key["link"])
    if key["handle"] != link["to_handle"]:
        raise hive.HiveError("Only the candidate side of the folder link may grant a CV.")
    return folders.grant(f"{key['handle']}/{path}", key["peer"])


def read_cv(path: str, ctx: Context) -> dict[str, Any]:
    """Read one CV after the candidate granted it, returning bytes for the HR agent."""
    secret = folder_keys.bearer(_header(ctx, folder_keys.HEADER))
    key = folder_keys.resolve(secret)
    if key is None:
        raise hive.HiveError("A connected folder link is required to read a CV.")
    reference = f"{key['peer']}/{path}"
    entry = folders.entry(reference)
    if entry is None or not folders.can_read(reference, key["handle"]):
        raise hive.HiveError("This CV has not been granted on the connected folder link.")
    content = folders.read(reference, key["handle"])
    return {
        "path": path,
        "media_type": entry["media_type"],
        "bytes": len(content),
        "digest": entry["digest"],
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def _hiring_hub_client() -> httpx.Client:
    """Create the configured Hiring Hub client, refusing an incomplete integration."""
    if not config.HIRING_HUB_URL:
        raise hive.HiveError("Hiring Hub integration is not configured: set HIRING_HUB_URL.")
    if not config.HIRING_HUB_API_KEY:
        raise hive.HiveError("Hiring Hub integration is not configured: set HIRING_HUB_API_KEY.")
    return httpx.Client(
        base_url=config.HIRING_HUB_URL,
        headers={"x-api-key": config.HIRING_HUB_API_KEY},
        timeout=config.HIRING_HUB_TIMEOUT_S,
    )


def create_job_posting(job: dict[str, Any]) -> dict[str, Any]:
    """Create a Hiring Hub position from an HR job requirement JSON document."""
    title = str(job.get("title") or "").strip()
    if not title:
        raise hive.HiveError("A job requirement needs a title.")
    payload = {
        "title": title,
        "description": str(job.get("description") or "").strip() or None,
        "custom_fields": job.get("custom_fields") or [],
    }
    try:
        with _hiring_hub_client() as client:
            response = client.post("/positions", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as err:
        raise hive.HiveError(f"Hiring Hub could not create the job posting: {err}") from err


def submit_cv(position_id: int, path: str, ctx: Context) -> dict[str, Any]:
    """Read a granted CV and upload it to an existing Hiring Hub position."""
    if position_id < 1:
        raise hive.HiveError("A valid Hiring Hub position_id is required.")
    secret = folder_keys.bearer(_header(ctx, folder_keys.HEADER))
    key = folder_keys.resolve(secret)
    if key is None:
        raise hive.HiveError("A connected folder link is required to submit a CV.")
    reference = f"{key['peer']}/{path}"
    entry = folders.entry(reference)
    if entry is None or not folders.can_read(reference, key["handle"]):
        raise hive.HiveError("This CV has not been granted on the connected folder link.")
    try:
        content = folders.read(reference, key["handle"])
        with _hiring_hub_client() as client:
            response = client.post(
                f"/positions/{position_id}/cvs",
                files={"files": (path.rsplit("/", 1)[-1], content, entry["media_type"])},
            )
            response.raise_for_status()
            return {"position_id": position_id, "path": path, "upload": response.json()}
    except httpx.HTTPError as err:
        raise hive.HiveError(f"Hiring Hub could not receive the CV: {err}") from err


def register(server: MCPServer) -> None:
    """Add the HR tools to the Hive's MCP server."""

    @server.tool()
    def hr_find_people(skills: list[str], location: str | None = None) -> dict[str, Any]:
        """Find people by skills (and optionally location). Returns public profiles only, never contact details."""
        return safe(find_people, skills, location)

    @server.tool()
    def hr_request_intro(card_id: str, from_org: str, message: str) -> dict[str, Any]:
        """Ask to be introduced to a person. The request waits for the person's consent; no contact data is returned."""
        return safe(request_intro, card_id, from_org, message)

    @server.tool()
    def hr_decide_intro(connection_id: str, approve: bool, ctx: Context) -> dict[str, Any]:
        """Accept or decline an HR introduction using an owner token or the candidate's link credential."""
        return safe(decide_intro, connection_id, approve, ctx)

    @server.tool()
    def hr_grant_cv(ctx: Context, path: str = "cv.pdf") -> dict[str, Any]:
        """Grant the connected HR agent access to one candidate file; the candidate's transport proves authority."""
        return safe(grant_cv, path, ctx)

    @server.tool()
    def hr_read_cv(ctx: Context, path: str = "cv.pdf") -> dict[str, Any]:
        """Read a granted candidate CV as base64 data with its signed-folder metadata."""
        return safe(read_cv, path, ctx)

    @server.tool()
    def hr_create_job(job: dict[str, Any]) -> dict[str, Any]:
        """Create a Hiring Hub job posting from the HR requirement JSON."""
        return safe(create_job_posting, job)

    @server.tool()
    def hr_submit_cv(position_id: int, ctx: Context, path: str = "cv.pdf") -> dict[str, Any]:
        """Upload a candidate's consented CV directly to a Hiring Hub position."""
        return safe(submit_cv, position_id, path, ctx)
