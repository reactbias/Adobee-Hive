"""HR domain: people publish a person card, company agents find them and request a CV with consent.

Owned by the HR workflows lane. This is the working skeleton to build on, not the finished flow:

- Built: the `person` card kind, skills matching, consented introductions, the MCP CV exchange, and the upload to
  a Hiring Hub. `panels/HRPanel.tsx` plays this flow as a labelled script; it calls none of these tools.
- Next: seed fictional people, a person view and studio in the frontend, and a way for a candidate to hold their
  own link secret, which today only the operator can mint (`documentation/LIMITS.md`).
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

from .. import audit, config, folder_keys, folders, guard, hive, hub
from .base import safe

KIND = "person"
HIRING_KEY_HEADER = "X-Hiring-Hub-Key"
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
    # An empty path is the whole folder to `folders.grant`, so it is refused here as on the REST route.
    name = path.strip().strip("/")
    if not name or "*" in name or "?" in name:
        raise hive.HiveError("A CV grant names one path, with no pattern, and not the whole folder.")
    return folders.grant(f"{key['handle']}/{name}", key["peer"])


def _read_granted(path: str, ctx: Context, doing: str) -> tuple[dict[str, Any], bytes]:
    """The listing and bytes of one granted file, under the same rules as `GET /api/folders/file`.

    These tools are a second door to the same files, so they hold the same line: `folders.SERVED`, the
    link's read budget, the size ceiling, one refusal for every kind of no, and a ledger row the owner
    can read. `doing` says in that row what the bytes were read for.
    """
    key = folder_keys.resolve(folder_keys.bearer(_header(ctx, folder_keys.HEADER)))
    if key is None:
        raise hive.HiveError("A connected folder link is required to read a CV.")
    if over := guard.over_budget(guard.folder_reads, key["link"]):
        raise hive.HiveError(over)
    reference = f"{key['peer']}/{path}"
    refused = hive.HiveError("This CV has not been granted on the connected folder link.")
    try:
        entry = folders.entry(reference)
        allowed = folders.can_read(reference, key["handle"])
    except folders.FolderError:
        raise refused from None
    if entry is None or not allowed or entry["visibility"] not in folders.SERVED:
        raise refused
    if entry["bytes"] > config.FOLDER_READ_MAX_BYTES:
        raise hive.HiveError(
            f"That file is {entry['bytes']} bytes and this hub serves at most {config.FOLDER_READ_MAX_BYTES}."
        )
    content = folders.read(reference, key["handle"])
    folder_keys.touch(key["id"])
    audit.record(
        "folder.read",
        reference,
        f"{doing} over folder link {key['link']}",
        credential="link secret",
        detail=f"key {key['id']}",
        actor=key["handle"],
    )
    return entry, content


def read_cv(path: str, ctx: Context) -> dict[str, Any]:
    """Read one CV after the candidate granted it, returning bytes for the HR agent."""
    entry, content = _read_granted(path, ctx, "read through hr_read_cv")
    return {
        "path": path,
        "media_type": entry["media_type"],
        "bytes": len(content),
        "digest": entry["digest"],
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def _hiring_hub_client(ctx: Context) -> httpx.Client:
    """The configured Hiring Hub client, for a caller who shows the organisation's own key.

    The hub holds one organisation's key and every MCP caller is anonymous, so without this any of
    them could create positions in that organisation and start its paid CV extraction. Fails closed.
    """
    if not config.HIRING_HUB_URL:
        raise hive.HiveError("Hiring Hub integration is not configured: set HIRING_HUB_URL.")
    if not config.HIRING_HUB_API_KEY:
        raise hive.HiveError("Hiring Hub integration is not configured: set HIRING_HUB_API_KEY.")
    if not guard.secret_matches(_header(ctx, HIRING_KEY_HEADER), config.HIRING_HUB_API_KEY):
        raise hive.HiveError(f"The Hiring Hub tools need the organisation's key in the {HIRING_KEY_HEADER} header.")
    return httpx.Client(
        base_url=config.HIRING_HUB_URL,
        headers={"x-api-key": config.HIRING_HUB_API_KEY},
        timeout=config.HIRING_HUB_TIMEOUT_S,
    )


def create_job_posting(job: dict[str, Any], ctx: Context) -> dict[str, Any]:
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
        with _hiring_hub_client(ctx) as client:
            response = client.post("/positions", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as err:
        raise hive.HiveError(f"Hiring Hub could not create the job posting: {err}") from err


def submit_cv(position_id: int, path: str, ctx: Context) -> dict[str, Any]:
    """Read a granted CV and upload it to an existing Hiring Hub position."""
    if position_id < 1:
        raise hive.HiveError("A valid Hiring Hub position_id is required.")
    # The key first: a caller without it must not spend the link's budget or leave a read in the ledger.
    with _hiring_hub_client(ctx) as client:
        entry, content = _read_granted(path, ctx, f"sent to Hiring Hub position {position_id}")
        try:
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
        """Accept or decline an HR introduction, as `hub.decide` allows: owner token or the target's link secret."""
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
    def hr_create_job(job: dict[str, Any], ctx: Context) -> dict[str, Any]:
        """Create a Hiring Hub job posting; the organisation's key must arrive in the X-Hiring-Hub-Key header."""
        return safe(create_job_posting, job, ctx)

    @server.tool()
    def hr_submit_cv(position_id: int, ctx: Context, path: str = "cv.pdf") -> dict[str, Any]:
        """Upload a granted CV to a Hiring Hub position; needs the link secret and the X-Hiring-Hub-Key header."""
        return safe(submit_cv, position_id, path, ctx)
