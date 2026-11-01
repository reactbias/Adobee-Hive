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

from . import blocklist, calibration, config, connections, federation, registration, removals, sharing


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
    from . import peers as store

    peers = calibration.ranked()
    return {
        "hub": config.HIVE_HUB_ID,
        "name": config.HIVE_NAME,
        "index": {"entities": _index_size()},
        "neighbours": {
            # The live list, which is the stored one once anything has been stored (peers.py).
            "configured": len(store.urls()),
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
    withdrawn = {row["entity_id"]: row for row in removals.entries()}
    rows = [_entity_row(card, withdrawn) for card in _cards()]
    return {
        "entities": rows,
        # The count is what the hub carries, so a withdrawn entity is listed but not counted. The
        # overview's number has to mean the same thing as this one.
        "count": len([r for r in rows if r["carried"]]),
        "withdrawn": len([r for r in rows if not r["carried"]]),
    }


def _cards() -> list[dict[str, Any]]:
    """Every card in the index, what this hub has withdrawn included: administration sees both."""
    from . import hive

    return hive.list_cards(include_withdrawn=True)


def _entity_row(card: dict[str, Any], withdrawn: dict[str, Any] | None = None) -> dict[str, Any]:
    """One row of the entity table: who it is, whether it claimed itself, and how it has been rated."""
    trust = card.get("trust") or {}
    reviews = trust.get("verified_reviews") or {}
    removal = (withdrawn or {}).get(card["id"])
    return {
        # Carried or withdrawn. A withdrawn entity keeps its card and its signed history; what
        # changed is that this hub no longer offers it (removals.py).
        "carried": removal is None,
        "removal": removal,
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
    removal = next((r for r in removals.entries() if r["entity_id"] == card["id"]), None)
    return {
        "entity": _entity_row(card, {removal["entity_id"]: removal} if removal else {}),
        "carried": removal is None,
        "removal": removal,
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
    from . import peers as store

    blocked = blocklist.blocked_hubs()
    standing = {p["hub"]: p for p in calibration.ranked()}
    rows = []
    for url in store.urls():
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


def peer_table() -> dict[str, Any]:
    """The peers an operator can act on: URL, hub id, name, whether it answers, calibration, state.

    A database read joined with what the background asking already learned (`federation.peer_row`).
    Nothing here fetches, so an unreachable neighbour cannot make this page slow or blank: it reads
    as not answering, with the time it was last tried, which is the honest thing to show anyway.
    """
    from . import peers as store

    standing = {p["hub"]: p for p in calibration.ranked()}
    blocked = blocklist.blocked_hubs()
    rows = []
    for row in store.listing():
        # Who the peer says it is, and whether it is answering, from federation's own book: asked in
        # the background, read here without fetching. One fact, one store (see peers.py).
        live = federation.peer_row(row["url"])
        hub_id = row["hub_id"] or live["hub"]
        cal = standing.get(hub_id, {})
        rows.append(
            {
                **row,
                **{k: v for k, v in live.items() if k not in ("url", "hub", "name")},
                "hub": hub_id,
                # What the operator typed wins over what a peer claims about itself; the peer's own
                # name fills the gap when nobody has typed one.
                "name": row["name"] or live["name"],
                # Blocked is not removed: see peers.py. Both are shown, because an operator will
                # otherwise reach for the wrong one.
                "blocked": hub_id in blocked,
                "error": cal.get("error"),
                "error_stars": cal.get("error_stars"),
                "evidence": cal.get("evidence", 0),
                "verdict": cal.get("verdict", "unproven"),
                "why": cal.get("why", "no introductions through this hub yet"),
            }
        )
    return {
        "peers": rows,
        "live": store.urls(),
        "seed": list(config.HIVE_PEER_URLS),
        # True while nothing has been stored: the environment variable is still the live list, and
        # the first change an operator makes is what takes the hub off it.
        "from_environment": not rows,
        "blocked_hubs": sorted(blocked),
    }


def directory(base_url: str = "") -> dict[str, Any]:
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

    `base_url` is the address this hub was reached at, which is the only honest source for its *own* row: a
    process does not know what name a client used to get to it. `config.HIVE_PUBLIC_URL` overrides it for a hub
    behind a proxy. Without either the row's URL stays empty rather than guessing, and `why_not_asked` says so.
    """
    standing = {p["hub"]: p for p in calibration.ranked()}
    blocked = blocklist.blocked_hubs()
    rows = [_home_row(standing, blocked, base_url)]
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
        # How many scored introductions a verdict needs, so a row can say "2 of 3" instead of a bare "unproven".
        "min_evidence": calibration.MIN_EVIDENCE,
        # What a verdict means, in the answer, for the same reason `admission_meanings` is: a row that reads
        # `verdict: "unproven", evidence: 0` tells a reader a word and a number and nothing they can act on.
        # Every row also carries its own `why`, which is this sentence applied to that hub's actual count.
        "verdict_meanings": VERDICT_MEANINGS,
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


#: What each calibration verdict means, for a reader who has only ever seen the word. Keyed by the values
#: `calibration.score` produces, so a new verdict there shows up here as a missing key rather than as a wrong
#: sentence; `tests/test_hub_directory.py` pins that they agree.
VERDICT_MEANINGS = {
    "unproven": (
        "nobody has scored an introduction through this hub yet, or not enough of them. It is not a bad sign and"
        " not a good one: there is no evidence either way, so judge the hub on what it carries and how it admits"
        " members instead."
    ),
    "calibrated": "the ratings this hub published have matched what real people found, within half a star.",
    "over-promises": "its published ratings have come out higher than what real people found.",
    "under-promises": "its published ratings have come out lower than what real people found: better than it says.",
}


def _home_row(standing: dict, blocked: set, base_url: str = "") -> dict[str, Any]:
    """This hub's own row: the only one that can answer for itself without asking anybody.

    It answers for itself and that used to read as knowing nothing about itself — a blank `url`, a relative
    `apply_at`, and `last_asked` null with nothing to say why. The address now comes from
    `config.HIVE_PUBLIC_URL` or from the request that asked, because a process cannot know what name a client
    used to reach it; `apply_at` is absolute whenever the address is known. The nulls stay null, because nothing
    was asked and claiming a time would be a lie, and `why_not_asked` says that instead of leaving it to be read
    as a failure.
    """
    url = (config.HIVE_PUBLIC_URL or base_url or "").rstrip("/")
    return {
        "hub": config.HIVE_HUB_ID,
        "url": url,
        "home": True,
        **_standing_of(config.HIVE_HUB_ID, standing, blocked),
        "name": config.HIVE_NAME,
        "description": config.HIVE_DESCRIPTION,
        "admission": config.ADMISSION_POLICY,
        "accepting": config.ADMISSION_POLICY != registration.CLOSED,
        "verification": config.HIVE_VERIFICATION,
        "entities": _index_size(),
        "apply_at": f"{url}/api/hub/register" if url else "/api/hub/register",
        # This hub answers for itself, so there is nothing to ask and nothing to be out of date.
        "last_asked": None,
        "last_asked_ok": None,
        "why_not_asked": "this hub's own row: it answers for itself, so nothing is asked and nothing can be stale",
        "stale": False,
        "known": True,
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
