"""Who was introduced to whom, and what came of it.

A rating here is not a click. It is a person saying, afterwards, how the real meeting went. So the
hub records the introduction and then waits, sometimes for weeks, for a human to come back and
score it. Everything the trust layer knows is built on these rows.

The life of a connection:

    requested ──confirm──> open ──sign off──> rated
        │                   │
        └──decline──>       └──no answer for STALE_AFTER_DAYS──> stale

`stale` is the honest end. An introduction nobody scored tells us nothing, and letting it be scored
a year later would invite exactly the kind of score-settling a rating system has to resist. A stale
row is kept — it is evidence about a hub's hit rate — but it can never become a rating.

Ratings are **tenths of a star**: an integer 0 to 50, shown as 0.0 to 5.0. Stars because people
think in stars, tenths because 4.3 is a real answer and floats drift when you average them.

The field that makes the trust layer work is `published_rating`: whatever the other hub claimed
this entity was worth, captured at the moment of introduction. Compare it with what the human
reports later and you have measured that hub's honesty. See calibration.py.

**A booking stands on a folder link.** Before a row exists here, the two agents' folders have met
(folders.py): a connection cannot be *made* without a link between requester and target, and cannot
be *opened* until that link is established. A booking made with no link is a booking made on what
the public index said rather than on what the two agents actually agreed, which is the one thing
this product is arguing against. `folder_link` holds the link the row stands on.

The precondition is on making a new booking, not on reading the log of bookings already made. A row
written before any of this existed carries no link, and nothing here asks it for one: it can still
be confirmed, scored, counted and gone stale. Old evidence does not stop being evidence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from . import config, db, folders

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_connections (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    state VARCHAR NOT NULL,
    requester VARCHAR NOT NULL,
    requester_hub VARCHAR,
    target VARCHAR NOT NULL,
    target_hub VARCHAR,
    via_hub VARCHAR,
    sharing VARCHAR,
    published_rating INTEGER,
    opened_at TIMESTAMP,
    stale_at TIMESTAMP,
    rated_at TIMESTAMP,
    rating INTEGER,
    note VARCHAR,
    folder_link VARCHAR
);
"""

REQUESTED = "requested"
OPEN = "open"
RATED = "rated"
STALE = "stale"
DECLINED = "declined"

MIN_STARS, MAX_STARS = 0, 50  # tenths of a star: 43 is 4.3 stars
STALE_AFTER_DAYS = 30  # a human has this long to score a meeting before the row closes unscored
CONFIRM_WITHIN_DAYS = 7  # an unanswered request expires sooner than an unrated meeting
STALE_SOON_DAYS = 7  # an open row with this long or less left is worth asking about now


class ConnectionError_(ValueError):
    """A connection that cannot be made or scored as asked."""


def init() -> None:
    """Create the table, add `folder_link` to one that predates it, and make sure folders.py is ready.

    The column is added rather than assumed, because the demo hub has a Postgres snapshot of rows
    written before folder links existed. A missing link on an old row is a fact about that row, not
    a reason for the hub to fall over on boot.
    """
    folders.init()
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)
        held = {r[1] for r in cur.execute("PRAGMA table_info('hub_connections')").fetchall()}
        if "folder_link" not in held:
            cur.execute("ALTER TABLE hub_connections ADD COLUMN folder_link VARCHAR")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def stars(tenths: int | None) -> float | None:
    """Tenths of a star as the number a person reads. 43 becomes 4.3."""
    return None if tenths is None else round(tenths / 10, 1)


def check_rating(value: int) -> int:
    """A rating has to be a whole number of tenths of a star inside the scale."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConnectionError_(f"a rating is a whole number of tenths of a star, got {value!r}")
    if not MIN_STARS <= value <= MAX_STARS:
        raise ConnectionError_(f"a rating runs {MIN_STARS} to {MAX_STARS} (0.0 to 5.0 stars), got {value}")
    return value


def _row(r: tuple) -> dict[str, Any]:
    keys = (
        "id",
        "created_at",
        "state",
        "requester",
        "requester_hub",
        "target",
        "target_hub",
        "via_hub",
        "sharing",
        "published_rating",
        "opened_at",
        "stale_at",
        "rated_at",
        "rating",
        "note",
        "folder_link",
    )
    raw = dict(zip(keys, r, strict=True))
    out: dict[str, Any] = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in raw.items()}
    out["rating_stars"] = stars(out["rating"])
    out["published_rating_stars"] = stars(out["published_rating"])
    # `stale_at` alone makes every reader do date arithmetic to find out whether it still has time,
    # and an agent that gets that wrong either nags a person about nothing or lets the one piece of
    # evidence this hub's trust layer runs on expire unscored. So the row says it.
    left = out["stale_in_days"] = _days_left(raw["stale_at"])
    out["stale_soon"] = out["state"] == OPEN and left is not None and left <= STALE_SOON_DAYS
    return out


def _days_left(stale_at: Any) -> int | None:
    """Whole days until this row can no longer be scored: 0 on its last day, None when it has no deadline."""
    if not isinstance(stale_at, datetime):
        return None
    return max(0, (stale_at - _now()).days)


SELECT = (
    "SELECT id, created_at, state, requester, requester_hub, target, target_hub, via_hub, sharing, "
    "published_rating, opened_at, stale_at, rated_at, rating, note, folder_link FROM hub_connections"
)


def link_for(requester: str, target: str, folder_link: str = "", *, opening: bool = False) -> dict[str, Any]:
    """The folder link this booking stands on, or a refusal naming what is missing.

    Two bars, which are the two states a link has. Making a booking needs a link to *exist*: these
    two agents have at least asked to connect their folders. Opening one needs that link to be
    *established*, because an open connection is the hub saying the introduction happened, and it
    has not happened while one side is still waiting to be let in.

    `folder_link` is checked against the pair rather than trusted. A link id is not a capability —
    passing someone else's would otherwise book on the strength of a handshake between two other
    agents.
    """
    try:
        link = folders.between(folders.handle_for(requester), folders.handle_for(target))
    except folders.FolderError as err:  # a name with nothing legal in it is nobody's handle
        raise ConnectionError_(str(err)) from err
    if link is None:
        raise ConnectionError_(
            f"{requester} and {target} have no folder link; the two agents connect their folders"
            " before a booking is made"
        )
    if folder_link and folder_link != link["id"]:
        raise ConnectionError_(
            f"folder link {folder_link} is not the link between {requester} and {target};"
            " a booking stands on their own handshake, not on somebody else's"
        )
    if opening and link["state"] != folders.ESTABLISHED:
        raise ConnectionError_(
            f"the folder link between {requester} and {target} is {link['state']}, not established;"
            f" a booking opens once {target} has accepted it"
        )
    return link


def request(
    requester: str,
    target: str,
    *,
    requester_hub: str = "",
    target_hub: str = "",
    via_hub: str = "",
    sharing: str = "",
    published_rating: int | None = None,
    needs_confirmation: bool = True,
    folder_link: str = "",
) -> dict[str, Any]:
    """Record an introduction. Open at once when the item was public, otherwise await the owner's yes.

    Refused outright unless the two agents have a folder link, and refused as an *open* connection
    unless that link is established (see `link_for`). The row keeps the link it stood on.

    `published_rating` is what the carrying hub said this entity was worth, in tenths of a star,
    frozen here. Later honesty is measured against this number and not against whatever the hub
    claims by the time the human gets round to scoring.
    """
    if not requester or not target:
        raise ConnectionError_("a connection needs both a requester and a target")
    if published_rating is not None:
        check_rating(published_rating)
    link = link_for(requester, target, folder_link, opening=not needs_confirmation)
    now, cid = _now(), f"cx-{uuid.uuid4().hex[:12]}"
    state = REQUESTED if needs_confirmation else OPEN
    opened = None if needs_confirmation else now
    stale_at = now + timedelta(days=CONFIRM_WITHIN_DAYS if needs_confirmation else STALE_AFTER_DAYS)
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hub_connections (id, created_at, state, requester, requester_hub, target, target_hub,"
            " via_hub, sharing, published_rating, opened_at, stale_at, folder_link) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                cid,
                now,
                state,
                requester,
                requester_hub,
                target,
                target_hub,
                via_hub,
                sharing,
                published_rating,
                opened,
                stale_at,
                link["id"],
            ],
        )
    return get(cid)


def confirm(connection_id: str) -> dict[str, Any]:
    """The owner says yes, to the introduction and to the folder link in the same breath.

    They are one decision and the hub asks it once. A `confirm` Card's link waits precisely because
    its owner had not yet said anything; when they do, the folders are linked and the connection
    opens together.

    Refused for an entity another hub carries: see the comment below. Declining stays allowed,
    because that is this hub's own caller giving up on its own request.

    A row whose link has gone — written before links existed, or left behind by a demo reset — is
    confirmed anyway. The precondition is on making a booking, and this booking was made.
    """
    from . import hive  # local: hive imports nothing from here, and this is the only call that needs it

    row = get(connection_id)
    if row["state"] != REQUESTED:
        raise ConnectionError_(f"only a requested connection can be confirmed, this one is {row['state']}")
    # An introduction to an entity on another hub is this hub's to *record* and not to complete. The
    # owner is not its member and their card is not its card, so a yes given here would be a consent
    # nobody gave. The row stays `requested`, exactly as a local one does while its owner is silent.
    # Narrow on purpose: it is the entity being absent from this index that makes the yes somebody
    # else's, not a `target_hub` a caller happened to put on a row about a local entity.
    elsewhere = row.get("target_hub") or ""
    if elsewhere and elsewhere != config.HIVE_HUB_ID and hive.get_record(row["target"]) is None:
        raise ConnectionError_(
            f"{row['target']} is carried by {elsewhere}, not by this hub, so this hub cannot say yes for it:"
            f" its owner confirms the introduction on {elsewhere}. This hub has recorded that it was asked for"
        )
    if row["folder_link"]:
        try:
            folders.accept_link(row["folder_link"], by=row["target"])
        except folders.FolderError as err:
            log.warning("connections: %s has no folder link to accept (%s); confirming anyway", connection_id, err)
    now = _now()
    with db.write() as cur:
        cur.execute(
            "UPDATE hub_connections SET state = ?, opened_at = ?, stale_at = ? WHERE id = ?",
            [OPEN, now, now + timedelta(days=STALE_AFTER_DAYS), connection_id],
        )
    return get(connection_id)


def decline(connection_id: str, note: str = "") -> dict[str, Any]:
    """The owner says no. Nothing further happens, and it never becomes a rating."""
    row = get(connection_id)
    if row["state"] != REQUESTED:
        raise ConnectionError_(f"only a requested connection can be declined, this one is {row['state']}")
    with db.write() as cur:
        cur.execute(
            "UPDATE hub_connections SET state = ?, note = ? WHERE id = ?", [DECLINED, note[:500], connection_id]
        )
    return get(connection_id)


def rate(connection_id: str, rating: int, note: str = "") -> dict[str, Any]:
    """The human scores the real meeting, once.

    Only an open connection can be scored: not one still waiting for a yes, not a declined one,
    and not one that went stale. Scoring is final, because a rating that can be revised is a
    rating that can be bargained over.
    """
    check_rating(rating)
    row = expire_stale_one(connection_id)
    if row["state"] == RATED:
        raise ConnectionError_("this connection has already been scored; a score is given once")
    if row["state"] == STALE:
        raise ConnectionError_(
            f"this connection went unscored for {STALE_AFTER_DAYS} days and is closed; it cannot be scored now"
        )
    if row["state"] != OPEN:
        raise ConnectionError_(f"only an open connection can be scored, this one is {row['state']}")
    now = _now()
    with db.write() as cur:
        cur.execute(
            "UPDATE hub_connections SET state = ?, rating = ?, rated_at = ?, note = ? WHERE id = ?",
            [RATED, rating, now, note[:500], connection_id],
        )
    return get(connection_id)


def get(connection_id: str) -> dict[str, Any]:
    """One connection by id."""
    with db.cursor() as cur:
        row = cur.execute(f"{SELECT} WHERE id = ?", [connection_id]).fetchone()
    if row is None:
        raise ConnectionError_(f"no connection {connection_id!r}")
    return _row(row)


def expire_stale_one(connection_id: str) -> dict[str, Any]:
    """Close this connection if its moment has passed, then return it."""
    row = get(connection_id)
    if row["state"] in (REQUESTED, OPEN) and row["stale_at"] and row["stale_at"] < _now().isoformat():
        with db.write() as cur:
            cur.execute("UPDATE hub_connections SET state = ? WHERE id = ?", [STALE, connection_id])
        return get(connection_id)
    return row


def expire_stale() -> int:
    """Close every connection whose moment has passed. Returns how many. Safe to run often."""
    now = _now()
    with db.write() as cur:
        rows = cur.execute(
            "SELECT id FROM hub_connections WHERE state IN (?, ?) AND stale_at IS NOT NULL AND stale_at < ?",
            [REQUESTED, OPEN, now],
        ).fetchall()
        if rows:
            cur.execute(
                "UPDATE hub_connections SET state = ? WHERE state IN (?, ?) AND stale_at IS NOT NULL AND stale_at < ?",
                [STALE, REQUESTED, OPEN, now],
            )
    return len(rows)


def awaiting_rating(requester: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Open connections still waiting on a human. This is what a 'how did it go?' prompt reads."""
    expire_stale()
    sql, args = f"{SELECT} WHERE state = ?", [OPEN]
    if requester:
        sql += " AND requester = ?"
        args.append(requester)
    sql += " ORDER BY stale_at ASC LIMIT ?"
    args.append(max(1, min(int(limit), 200)))
    with db.cursor() as cur:
        return [_row(r) for r in cur.execute(sql, args).fetchall()]


def pending_confirmation(target: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Requests waiting on the owner's yes."""
    expire_stale()
    sql, args = f"{SELECT} WHERE state = ?", [REQUESTED]
    if target:
        sql += " AND target = ?"
        args.append(target)
    sql += " ORDER BY created_at ASC LIMIT ?"
    args.append(max(1, min(int(limit), 200)))
    with db.cursor() as cur:
        return [_row(r) for r in cur.execute(sql, args).fetchall()]


def rated_via(hub_id: str) -> list[dict[str, Any]]:
    """Every scored connection that came through this hub. The input to calibration.py."""
    with db.cursor() as cur:
        rows = cur.execute(
            f"{SELECT} WHERE state = ? AND rating IS NOT NULL AND published_rating IS NOT NULL"
            " AND (via_hub = ? OR target_hub = ?) ORDER BY rated_at DESC",
            [RATED, hub_id, hub_id],
        ).fetchall()
    return [_row(r) for r in rows]


def hubs_with_ratings() -> list[str]:
    """Every hub we have scored evidence about."""
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT DISTINCT coalesce(nullif(via_hub, ''), target_hub) AS hub FROM hub_connections"
            " WHERE state = ? AND rating IS NOT NULL AND published_rating IS NOT NULL",
            [RATED],
        ).fetchall()
    return [r[0] for r in rows if r[0]]
