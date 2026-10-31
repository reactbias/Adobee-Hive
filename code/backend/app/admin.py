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
            {
                "key": "peer_ask_seconds",
                "label": "Ask the peers every",
                "value": config.PEER_ASK_SECONDS,
                "help": (
                    "Seconds between rounds of asking each peer's discovery document who it is. This is why a "
                    "name or an entity count in the directory can be up to this old. 0 turns the asking off."
                ),
                "editable": False,
            },
            {
                "key": "peer_stale_after_seconds",
                "label": "Call a peer's answer stale after",
                "value": config.PEER_STALE_AFTER_S,
                "help": (
                    "Seconds an answer stays current. Past this it is still shown, marked stale, rather than "
                    "thrown away: an old name is more use than no name, as long as the row says it is old."
                ),
                "editable": False,
            },
            {
                "key": "peer_ask_timeout_seconds",
                "label": "Give one peer at most",
                "value": config.PEER_ASK_TIMEOUT_S,
                "help": (
                    "Seconds one peer may take to answer. Peers are asked all at once and off the request path, "
                    "so a peer that has stopped answering never makes the directory slow."
                ),
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
        # The peer's own id where it has told us one, so standing and the blocklist are looked up under the name
        # the peer actually answers to rather than under its address.
        hub_id = federation.peer_row(url)["hub"]
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

    A peer's own name, description, admission policy and entity count come from the discovery document it
    publishes, read by `federation`. This call only reads what has already arrived, so a peer that has stopped
    answering cannot make choosing a hub slow. Each peer row says when it was last asked (`last_asked`, ISO 8601
    UTC) and whether that ask was answered (`last_asked_ok`), both `None` when it has genuinely never been asked.
    """
    standing = {p["hub"]: p for p in calibration.ranked()}
    blocked = blocklist.blocked_hubs()
    rows = [_home_row(standing, blocked)]
    for url in config.HIVE_PEER_URLS:
        rows.append(_directory_row(federation.peer_row(url), standing, blocked))
    for hub_id in standing:
        # A hub we have standing for but no longer peer with: it still belongs in the list, named and unasked.
        if hub_id not in {r["hub"] for r in rows}:
            rows.append(_directory_row(federation.peer_row("") | {"hub": hub_id}, standing, blocked))
    return {
        "hubs": rows,
        "help": (
            "Pick the hub whose admission and subject suit you, then apply to it. Your card is yours: "
            "a hub carries it, and moving means republishing one file somewhere else."
        ),
        "admission_meanings": registration.policy()["means"],
        "asked_every_seconds": config.PEER_ASK_SECONDS,
    }


def _standing_of(hub_id: str, standing: dict, blocked: set) -> dict[str, Any]:
    """What this hub's own people found when they were sent through `hub_id`. Never the hub's word for itself."""
    row = standing.get(hub_id, {})
    return {
        "blocked": hub_id in blocked,
        # Lower is better; None means we have not sent anyone there yet.
        "error": row.get("error"),
        "error_stars": row.get("error_stars"),
        "evidence": row.get("evidence", 0),
        "verdict": row.get("verdict", "unproven"),
        "why": row.get("why", "no introductions through this hub yet"),
    }


def _home_row(standing: dict, blocked: set) -> dict[str, Any]:
    """This hub's own row: the only one that can answer for itself without asking anybody."""
    return {
        "hub": config.HIVE_HUB_ID,
        "url": "",
        "home": True,
        **_standing_of(config.HIVE_HUB_ID, standing, blocked),
        "name": config.HIVE_NAME,
        "description": config.HIVE_DESCRIPTION,
        "admission": config.ADMISSION_POLICY,
        "accepting": config.ADMISSION_POLICY != registration.CLOSED,
        "verification": config.HIVE_VERIFICATION,
        "entities": _index_size(),
        "apply_at": "/api/hub/register",
        # This hub answers for itself, so there is nothing to ask and nothing to be out of date.
        "last_asked": None,
        "last_asked_ok": None,
        "stale": False,
    }


def _directory_row(peer: dict[str, Any], standing: dict, blocked: set) -> dict[str, Any]:
    """One peer's row, from what it published about itself plus what this hub observed of it.

    A peer that has answered is described in its own words. One that has not keeps its URL as its label and
    stays honestly unknown: `accepting` is `None` rather than `False`, because "we have not asked" and "it is
    closed" are different claims and only one of them is true.
    """
    url = peer["url"]
    known = peer["known"]
    admission = peer["admission"] if peer["admission"] in registration.POLICIES else "unknown"
    return {
        "hub": peer["hub"],
        "url": url,
        "home": False,
        **_standing_of(peer["hub"], standing, blocked),
        "name": peer["name"],
        "description": peer["description"],
        "admission": admission,
        "accepting": (admission != registration.CLOSED) if admission != "unknown" else None,
        "verification": peer["verification"],
        "entities": peer["entities"],
        "apply_at": f"{url.rstrip('/')}/api/hub/register" if url else "",
        "last_asked": peer["last_asked"],
        "last_asked_ok": peer["last_asked_ok"],
        # When the answer on screen arrived, which is not the same moment as the last ask once one has failed.
        "last_answered": peer["last_answered"],
        "stale": peer["stale"],
        "known": known,
    }
