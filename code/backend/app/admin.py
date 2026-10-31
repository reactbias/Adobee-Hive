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

from . import blocklist, calibration, config, connections, federation, sharing


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
