"""HR domain (starter): people publish a person card, company agents find them and ask for an introduction.

Owned by the HR workflows lane. This is the working skeleton to build on, not the finished flow:

- Built: the `person` card kind, `hr_find_people` (skills match with reasons, like stays discovery) and
  `hr_request_intro` (recorded for the person, who decides).
- Built beside it, in `recruit.py`: `hr_shortlist` and `hr_interview` search people by a whole job posting and
  let a recruiter's agent question theirs (`talent.py`, `interview.py`); CV import is `code/cv_analyzer`.
- Next: a person view and studio in the frontend, and the person's yes/no on an intro and on a screening.
  (`hive.discover` lists person cards now — they are found by what they offer and need like anyone else — so a
  seeded person is public presence, and only their contact stays behind consent.)

Rules that make this safe to show (keep them):
- Consent first. Contact details are never part of a person card. A company agent can only ask for an
  introduction; the person sees the request and decides.
- Agents see skills and availability, not age, photo, gender or nationality, so ranking can't use them.
- Everything else as in the core: the person signs their card, and text from cards is data, never instructions.
"""

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from .. import hive
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
