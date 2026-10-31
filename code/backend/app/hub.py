"""The hub as something an agent talks to: search it, ask to be connected, score it afterwards.

Three stores sit behind this: the index (hive.py), the neighbours (federation.py) and the manual
blocklist (blocklist.py). This module is the door they are reached through, and the only place the
four of them are composed.

What an agent can do:

- `search` the index, across peer Hives at a chosen radius, getting JSON back. Items the owner
  closed never appear, and blocked hubs and entities are filtered on the way in and on the way out.
- `connect` to something it found. The two agents' folders link first (folders.py) and the answer
  carries the manifest that link opened; then a `public` item opens at once, a `confirm` item waits
  for the owner's yes, and a `push` item cannot be asked for at all. Either way the introduction is
  logged.
- `score` the introduction afterwards, once the human has actually met whoever it was.

That last step is what everything else is built on. The hub learns nothing useful from a search and
nothing trustworthy from a booking; it learns from a person saying, weeks later, how it went.
"""

from __future__ import annotations

from typing import Any

from . import blocklist, calibration, config, connections, folders, hive, sharing


class HubError(ValueError):
    """A hub request that cannot be served as asked."""


def _entity_default(card: dict[str, Any]) -> str:
    """The sharing flag an entity applies to everything it holds, unless an item is stricter.

    A business card on a public hub is public. A person is `confirm` unless their card says
    otherwise (hive.CONSENT_FIRST_KINDS): an introduction to a person is theirs to grant.
    """
    fallback = sharing.CONFIRM if card.get("kind") in hive.CONSENT_FIRST_KINDS else sharing.PUBLIC
    return str(card.get("sharing") or fallback)


def _published_rating(card: dict[str, Any]) -> int | None:
    """What this hub says the entity is worth, in tenths of a star, for later honesty checking.

    Frozen here on purpose. Honesty is measured against what was claimed at the introduction, not
    against whatever the hub is claiming by the time a human gets round to scoring it.
    """
    rating = card.get("rating")
    if rating is None:
        rating = ((card.get("trust") or {}).get("verified_reviews") or {}).get("average")
    return None if rating is None else int(round(float(rating) * 10))


def visible(match: dict[str, Any]) -> bool:
    """Whether a result may be shown at all: not blocked, and not closed by its owner."""
    if blocklist.is_blocked(blocklist.ENTITY, str(match.get("id") or "")):
        return False
    route = ((match.get("provenance") or {}).get("path")) or []
    if route and blocklist.filter_path([str(h) for h in route]):
        return False
    return sharing.searchable(match.get("sharing"), match.get("item_sharing"))


async def search(ask: dict[str, Any], radius: int = 0) -> dict[str, Any]:
    """Search the index and, above radius 0, the neighbours. Returns JSON an agent can act on.

    Every match says whether connecting to it needs the owner's yes, so an agent can tell the
    difference between something it can have now and something it has to ask for.
    """
    from . import federation  # local: federation imports hive, and hive must load first

    found = await federation.search(ask, radius=radius) if int(radius or 0) > 0 else _local(ask)
    out = []
    for match in found.get("matches") or []:
        if not visible(match):
            continue
        flag = sharing.resolve(match.get("sharing"), match.get("item_sharing"))
        out.append(
            {
                **match,
                "sharing": flag,
                "needs_confirmation": flag == sharing.CONFIRM,
                "connectable": sharing.connectable(match.get("sharing"), match.get("item_sharing")),
            }
        )
    return {**found, "matches": out, "hub": config.HIVE_HUB_ID}


def _local(ask: dict[str, Any]) -> dict[str, Any]:
    """A radius-0 search, kept separate so the async path above reads as one thing."""
    return hive.discover(**ask)


def connect(
    requester: str,
    entity_id: str,
    *,
    requester_hub: str = "",
    target_hub: str = "",
    via_hub: str = "",
) -> dict[str, Any]:
    """Ask to be introduced to something in the index, and log the introduction either way.

    Refused outright for a blocked entity, and for an item its owner marked `push` or `never` —
    those are the owner's to send, not anyone's to request.
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        raise HubError("a connection needs an entity to connect to")
    if blocklist.is_blocked(blocklist.ENTITY, entity_id):
        raise HubError(f"{entity_id} is blocked on this hub")
    if target_hub and blocklist.is_blocked(blocklist.HUB, target_hub):
        raise HubError(f"{target_hub} is blocked on this hub")

    record = hive.get_record(entity_id)
    if record is None:
        raise HubError(f"no entity {entity_id!r} on this hub")
    card = record["data"]
    flag = sharing.resolve(_entity_default(card), None)
    if not sharing.connectable(flag, None):
        raise HubError(
            f"{entity_id} cannot be asked for: its owner shares it only on their own initiative"
            if flag == sharing.PUSH
            else f"{entity_id} is not shared"
        )

    # The folders meet before the booking does. A published, freely connectable Card is a standing
    # yes to being contacted — that is what publishing one means — so its link is accepted in the
    # same step. A `confirm` Card's owner has said nothing yet, so its link waits for the same
    # moment they confirm the introduction. Either way the link opens no contents: that needs a
    # grant, which is the owner's to give (folders.py).
    who, them = folders.handle_for(requester), folders.handle_for(entity_id)
    link = folders.open_link(who, them, auto_accept=flag == sharing.PUBLIC, by=them)
    published = _published_rating(card)
    row = connections.request(
        requester,
        entity_id,
        requester_hub=requester_hub or config.HIVE_HUB_ID,
        target_hub=target_hub,
        via_hub=via_hub or target_hub,
        sharing=flag,
        published_rating=published,
        needs_confirmation=flag == sharing.CONFIRM,
        folder_link=link["id"],
    )
    return {**row, "folder": folders.manifest(them, who)}


def score(connection_id: str, rating: int, note: str = "") -> dict[str, Any]:
    """Score an introduction after the real meeting, and show what it did to the hub it came from.

    This is the only moment the trust layer learns anything, so the answer says plainly what the
    score changed: the gap against what was promised, and where that leaves the carrying hub.
    """
    row = connections.rate(connection_id, rating, note)
    hub_id = row.get("via_hub") or row.get("target_hub") or ""
    published = row.get("published_rating")
    out: dict[str, Any] = {"connection": row, "hub": hub_id}
    if hub_id and published is not None:
        gap = calibration.delta(published, row["rating"])
        out["gap"] = gap
        out["gap_stars"] = round(gap / 10, 2)
        out["says"] = (
            f"{hub_id} promised {connections.stars(published)} and you found {row['rating_stars']}"
            if gap
            else f"{hub_id} had it exactly right"
        )
        out["hub_standing"] = calibration.trust(hub_id)
    return out


def standing() -> dict[str, Any]:
    """What this hub currently thinks of its neighbours. The admin GUI's main table."""
    return {"hub": config.HIVE_HUB_ID, "peers": calibration.ranked()}
