"""The hub's own settings, as data an interface can render.

There is no admin GUI yet, and this module is written on the assumption that there will be one.
So nothing here returns a sentence meant for a terminal: every call returns the same shape a form
would need — the current value, what the field is for, and, where the choice is closed, the options.

An operator can change three things: who is blocked, who the neighbours are, and how the hub
describes itself. Everything else about a hub is earned rather than set.

Every write needs the admin token (`X-Admin-Token`). When no token is configured the write
endpoints refuse rather than run open, because a hub whose blocklist anyone can edit has no
blocklist. Reads are open: what a hub blocks and who it peers with is exactly the sort of thing it
should be willing to say out loud.
"""

from __future__ import annotations

from typing import Any

from . import blocklist, calibration, config, connections, federation, registration, sharing


def settings() -> dict[str, Any]:
    """How this hub describes itself, in the shape a settings form wants."""
    return {
        "fields": [
            {
                "key": "hub_id",
                "label": "Hub id",
                "value": config.HIVE_HUB_ID,
                "help": "How peers name this hub. Changing it loses the standing peers have built for the old name.",
                "editable": False,
            },
            {
                "key": "name",
                "label": "Name",
                "value": config.HIVE_NAME,
                "help": "Shown to a person reading a result that came from here.",
                "editable": True,
            },
            {
                "key": "description",
                "label": "Description",
                "value": config.HIVE_DESCRIPTION,
                "help": "One line on what this hub carries.",
                "editable": True,
            },
            {
                "key": "verification",
                "label": "Verification",
                "value": config.HIVE_VERIFICATION,
                "help": "What this hub checks before carrying an entity. Peers weigh the claim against what they see.",
                "options": ["none", "email", "signed", "identity"],
                "editable": True,
            },
            {
                "key": "max_radius",
                "label": "Maximum search radius",
                "value": federation.MAX_RADIUS,
                "help": "How many hops a search starting here may travel.",
                "editable": False,
            },
        ],
        "sharing_flags": [
            {"value": sharing.PUBLIC, "label": "Public", "help": "Anyone may find it and connect at once."},
            {
                "value": sharing.CONFIRM,
                "label": "Needs confirmation",
                "help": "Findable; a connection waits for a yes.",
            },
            {"value": sharing.PUSH, "label": "Only when I send it", "help": "Held, never searchable, owner sends it."},
            {"value": sharing.NEVER, "label": "Never shared", "help": "Stays on this hub."},
        ],
        "rating": {
            "scale": [connections.MIN_STARS, connections.MAX_STARS],
            "unit": "tenths of a star",
            "help": "A person scores a real meeting afterwards. 43 is 4.3 stars.",
            "stale_after_days": connections.STALE_AFTER_DAYS,
            "confirm_within_days": connections.CONFIRM_WITHIN_DAYS,
        },
        "calibration": {
            "lower_is_better": True,
            "help": (
                "A peer is scored on whether its published ratings matched what our people found: "
                "published minus realised, in tenths of a star. Over-promising costs, being modest earns credit."
            ),
            "min_evidence": calibration.MIN_EVIDENCE,
            "half_life_days": calibration.HALF_LIFE_DAYS,
            "under_promise_weight": calibration.UNDER_PROMISE_WEIGHT,
        },
    }


def overview() -> dict[str, Any]:
    """Everything an admin front page shows: the three stores, counted, plus peer standing."""
    peers = calibration.ranked()
    return {
        "hub": config.HIVE_HUB_ID,
        "name": config.HIVE_NAME,
        "index": {"entities": _index_size()},
        "neighbours": {
            "configured": len(config.HIVE_PEER_URLS),
            "blocked": len(blocklist.blocked_hubs()),
            "with_evidence": len([p for p in peers if p["error"] is not None]),
        },
        "blocklist": {"hubs": len(blocklist.blocked_hubs()), "entities": len(blocklist.blocked_entities())},
        "connections": _connection_counts(),
        "peers": peers,
    }


def _index_size() -> int:
    from . import hive

    return len(hive.list_cards())


def _connection_counts() -> dict[str, int]:
    """How many introductions sit in each state. The number that matters is `awaiting`."""
    from . import db

    connections.expire_stale()
    with db.cursor() as cur:
        rows = cur.execute("SELECT state, count(*) FROM hub_connections GROUP BY state").fetchall()
    counts = {state: int(n) for state, n in rows}
    return {
        "awaiting_confirmation": counts.get(connections.REQUESTED, 0),
        "awaiting_rating": counts.get(connections.OPEN, 0),
        "rated": counts.get(connections.RATED, 0),
        "stale": counts.get(connections.STALE, 0),
        "declined": counts.get(connections.DECLINED, 0),
    }


def entities() -> dict[str, Any]:
    """Everything this hub carries, as a table an operator can scan.

    The overview counts the index; this is the list behind the count, and it is deliberately the
    same call (`hive.list_cards`), so the two can never disagree about what the hub carries.
    Nothing here is a side channel: every field is already on the public card.
    """
    rows = [_entity_row(card) for card in _cards()]
    return {"entities": rows, "count": len(rows)}


def _cards() -> list[dict[str, Any]]:
    from . import hive

    return hive.list_cards()


def _entity_row(card: dict[str, Any]) -> dict[str, Any]:
    """One row of the entity table: who it is, whether it claimed itself, and how it has been rated."""
    trust = card.get("trust") or {}
    reviews = trust.get("verified_reviews") or {}
    return {
        "id": card["id"],
        "slug": card.get("slug") or card["id"],
        "name": card.get("name") or card["id"],
        "kind": card.get("kind") or "",
        # An unclaimed card was compiled from public information: a lead, never a business that agreed.
        "claimed": bool(trust.get("claimed")),
        # None until a signed receipt earns one. Zero would read as a bad business, not a new one.
        "rating": reviews.get("average"),
        "rating_count": int(reviews.get("count") or 0),
        "published_at": card.get("published_at"),
        "version": card.get("version"),
        "signature_valid": bool(trust.get("signature_valid")),
        "bookable": bool(card.get("units")) and bool(trust.get("claimed")),
    }


def entity(entity_id: str) -> dict[str, Any]:
    """One entity in full, for the operator deciding what to do about it.

    Everything a decision needs in one answer: the row as the list shows it, the whole signed card,
    the two sides of the market it is indexed by, how it can be reached and under which sharing
    flag, its trust block, and the signature state spelled out rather than left to be read off a
    nested dict. Raises `hive.HiveError` for an id this hub has never carried.

    The sharing flag per channel is the *resolved* one — the stricter of the entity's default and
    the channel's own — because that is what the hub actually does, and an operator looking at a
    contact row needs to know whether it would be handed out, not what two separate fields say.
    """
    from . import hive, hub

    card = hive.get_card(entity_id)
    trust = card.get("trust") or {}
    block = next((e for e in blocklist.entries(blocklist.ENTITY) if e["subject"] == card["id"]), None)
    return {
        "entity": _entity_row(card),
        # The card exactly as the owner signed it. The trust block is reported separately because it
        # is this hub's reading of the card, not part of what was signed.
        "card": {k: v for k, v in card.items() if k != "trust"},
        "offers": list(card.get("offers") or []),
        "needs": list(card.get("needs") or []),
        "contact": _contact_rows(card, hub._entity_default(card)),
        "contact_sharing": dict(card.get("contact_sharing") or {}),
        "sharing_default": hub._entity_default(card),
        "trust": trust,
        "signature": {
            "valid": bool(trust.get("signature_valid")),
            "signature": trust.get("signature") or "",
            "public_key": trust.get("public_key") or "",
            "algorithm": trust.get("algorithm") or "",
            "fresh": bool(trust.get("fresh")),
            "valid_until": card.get("valid_until"),
            "version": card.get("version"),
        },
        # Removing is about this hub no longer carrying an entity; blocking is about refusing it
        # wherever it comes from. Both are offered from here, so the view has to say which is on.
        "blocked": block is not None,
        "block": block,
    }


def _contact_rows(card: dict[str, Any], default: str) -> list[dict[str, Any]]:
    """Every published contact channel with the sharing flag that actually applies to it."""
    flags = card.get("contact_sharing") or {}
    return [
        {
            "channel": channel,
            "value": value,
            "sharing": sharing.resolve(default, flags.get(channel)),
            "searchable": sharing.searchable(default, flags.get(channel)),
        }
        for channel, value in (card.get("contact") or {}).items()
    ]


def neighbours() -> dict[str, Any]:
    """The peer list as a table: configured, blocked, and how each one's ratings have held up."""
    blocked = blocklist.blocked_hubs()
    standing = {p["hub"]: p for p in calibration.ranked()}
    rows = []
    for url in config.HIVE_PEER_URLS:
        hub_id = url.rstrip("/").split("//")[-1]
        row = standing.get(hub_id, {})
        rows.append(
            {
                "url": url,
                "hub": hub_id,
                "blocked": hub_id in blocked,
                "error": row.get("error"),
                "error_stars": row.get("error_stars"),
                "evidence": row.get("evidence", 0),
                "verdict": row.get("verdict", "unproven"),
                "why": row.get("why", "never asked"),
            }
        )
    extra = [s for hub_id, s in standing.items() if hub_id not in {r["hub"] for r in rows}]
    return {"peers": rows + extra, "blocked_hubs": sorted(blocked)}


def directory() -> dict[str, Any]:
    """Every Hive we know of, as something a person choosing one can read.

    Modelled on instances.social, which solved this for Mastodon: before you can join a federated
    network you have to pick a door, and a list of names is not enough to choose by. So each row
    carries what actually decides it — whether it is taking members, what it asks of them, what it
    carries, and how honest its ratings have turned out to be.

    That last column is the one a Mastodon directory cannot offer. A hub here is not described only
    by what it says about itself; it is described by whether its claims survived contact with other
    people's users. `error` is published minus realised, in tenths of a star, and lower is better.
    """
    standing = {p["hub"]: p for p in calibration.ranked()}
    blocked = blocklist.blocked_hubs()
    rows = [_directory_row(config.HIVE_HUB_ID, "", standing, blocked, home=True)]
    for url in config.HIVE_PEER_URLS:
        rows.append(_directory_row(url.rstrip("/").split("//")[-1], url, standing, blocked))
    for hub_id in standing:
        if hub_id not in {r["hub"] for r in rows}:
            rows.append(_directory_row(hub_id, "", standing, blocked))
    return {
        "hubs": rows,
        "help": (
            "Pick the hub whose admission and subject suit you, then apply to it. Your card is yours: "
            "a hub carries it, and moving means republishing one file somewhere else."
        ),
        "admission_meanings": registration.policy()["means"],
    }


def _directory_row(hub_id: str, url: str, standing: dict, blocked: set, home: bool = False) -> dict[str, Any]:
    """One row of the directory. Only the home hub can answer for itself in detail."""
    row = standing.get(hub_id, {})
    entry = {
        "hub": hub_id,
        "url": url,
        "home": home,
        "blocked": hub_id in blocked,
        # Lower is better; None means we have not sent anyone there yet.
        "error": row.get("error"),
        "error_stars": row.get("error_stars"),
        "evidence": row.get("evidence", 0),
        "verdict": row.get("verdict", "unproven"),
        "why": row.get("why", "no introductions through this hub yet"),
    }
    if home:
        entry |= {
            "name": config.HIVE_NAME,
            "description": config.HIVE_DESCRIPTION,
            "admission": config.ADMISSION_POLICY,
            "accepting": config.ADMISSION_POLICY != registration.CLOSED,
            "verification": config.HIVE_VERIFICATION,
            "entities": _index_size(),
            "apply_at": "/api/hub/register",
        }
    else:
        # A peer's own description is read from its discovery document when it is asked; until then
        # the honest answer is that we do not know, rather than a guess.
        entry |= {
            "name": "",
            "description": "",
            "admission": "unknown",
            "accepting": None,
            "verification": "unknown",
            "entities": None,
            "apply_at": f"{url.rstrip('/')}/api/hub/register" if url else "",
        }
    return entry
