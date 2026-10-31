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
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db

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
    note VARCHAR
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


class ConnectionError_(ValueError):
    """A connection that cannot be made or scored as asked."""


def init() -> None:
    """Create the table."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


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
    )
    out: dict[str, Any] = {}
    for key, value in zip(keys, r, strict=True):
        out[key] = value.isoformat() if isinstance(value, datetime) else value
    out["rating_stars"] = stars(out["rating"])
    out["published_rating_stars"] = stars(out["published_rating"])
    return out


SELECT = (
    "SELECT id, created_at, state, requester, requester_hub, target, target_hub, via_hub, sharing, "
    "published_rating, opened_at, stale_at, rated_at, rating, note FROM hub_connections"
)


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
) -> dict[str, Any]:
    """Record an introduction. Open at once when the item was public, otherwise await the owner's yes.

    `published_rating` is what the carrying hub said this entity was worth, in tenths of a star,
    frozen here. Later honesty is measured against this number and not against whatever the hub
    claims by the time the human gets round to scoring.
    """
    if not requester or not target:
        raise ConnectionError_("a connection needs both a requester and a target")
    if published_rating is not None:
        check_rating(published_rating)
    now, cid = _now(), f"cx-{uuid.uuid4().hex[:12]}"
    state = REQUESTED if needs_confirmation else OPEN
    opened = None if needs_confirmation else now
    stale_at = now + timedelta(days=CONFIRM_WITHIN_DAYS if needs_confirmation else STALE_AFTER_DAYS)
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hub_connections (id, created_at, state, requester, requester_hub, target, target_hub,"
            " via_hub, sharing, published_rating, opened_at, stale_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
            ],
        )
    return get(cid)


def confirm(connection_id: str) -> dict[str, Any]:
    """The owner says yes. The clock to score it starts now, not when the request was made."""
    row = get(connection_id)
    if row["state"] != REQUESTED:
        raise ConnectionError_(f"only a requested connection can be confirmed, this one is {row['state']}")
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
