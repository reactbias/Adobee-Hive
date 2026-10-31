"""Manual admin blocks: the one place a person overrules the hub.

Everything else in this Hive is earned or computed — trust accrues, calibration is measured,
ranking explains itself. This is the override, and it is deliberately blunt and deliberately
auditable: an operator names a hub or an entity, gives a reason, and it is gone in both
directions. No score, no decay, no appeal in code.

Two kinds:

- `hub` — a peer Hive. Nothing of ours goes to it and nothing of its arrives. A blocked hub is
  not asked, and a card relayed *through* it is dropped even when the card itself is valid.
- `entity` — one business or person. Not returned in a search, not reachable by a connection,
  wherever it is carried from.

A reason is required. An operator reading the list in six months has to be able to tell a spam
block from a legal one, and "why is this hub missing" is a question the GUI must be able to answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_blocklist (
    kind VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    added_at TIMESTAMP NOT NULL,
    added_by VARCHAR,
    PRIMARY KEY (kind, subject)
);
"""

HUB = "hub"
ENTITY = "entity"
KINDS = (HUB, ENTITY)


class BlockError(ValueError):
    """A block that cannot be recorded as asked."""


def init() -> None:
    """Create the table."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


def _check(kind: str, subject: str, reason: str = "x") -> tuple[str, str, str]:
    subject = (subject or "").strip()
    reason = (reason or "").strip()
    if kind not in KINDS:
        raise BlockError(f"unknown block kind: {kind!r}; expected {' or '.join(KINDS)}")
    if not subject:
        raise BlockError("a block needs a subject")
    if not reason:
        raise BlockError("a block needs a reason: someone has to be able to read this list later")
    return kind, subject, reason[:500]


def block(kind: str, subject: str, reason: str, added_by: str = "admin") -> dict[str, Any]:
    """Block a peer hub or an entity. Re-blocking updates the reason rather than failing."""
    kind, subject, reason = _check(kind, subject, reason)
    now = datetime.now(UTC).replace(tzinfo=None)
    with db.write() as cur:
        cur.execute("DELETE FROM hub_blocklist WHERE kind = ? AND subject = ?", [kind, subject])
        cur.execute(
            "INSERT INTO hub_blocklist (kind, subject, reason, added_at, added_by) VALUES (?, ?, ?, ?, ?)",
            [kind, subject, reason, now, added_by],
        )
    return {"kind": kind, "subject": subject, "reason": reason, "added_at": now.isoformat(), "added_by": added_by}


def unblock(kind: str, subject: str) -> bool:
    """Lift a block. True when something was actually lifted."""
    kind, subject, _ = _check(kind, subject)
    with db.write() as cur:
        before = cur.execute("SELECT count(*) FROM hub_blocklist WHERE kind = ? AND subject = ?", [kind, subject])
        existed = bool(before.fetchone()[0])
        cur.execute("DELETE FROM hub_blocklist WHERE kind = ? AND subject = ?", [kind, subject])
    return existed


def is_blocked(kind: str, subject: str) -> bool:
    """Whether this hub or entity is blocked. The hot path, called on every search and every hop."""
    if not subject:
        return False
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT 1 FROM hub_blocklist WHERE kind = ? AND subject = ?", [kind, (subject or "").strip()]
        ).fetchone()
    return row is not None


def blocked_hubs() -> set[str]:
    """Every blocked peer, for filtering a whole peer list at once."""
    with db.cursor() as cur:
        return {r[0] for r in cur.execute("SELECT subject FROM hub_blocklist WHERE kind = ?", [HUB]).fetchall()}


def blocked_entities() -> set[str]:
    """Every blocked entity, for filtering a result set at once."""
    with db.cursor() as cur:
        return {r[0] for r in cur.execute("SELECT subject FROM hub_blocklist WHERE kind = ?", [ENTITY]).fetchall()}


def entries(kind: str | None = None) -> list[dict[str, Any]]:
    """The whole list, newest first. This is what the admin GUI renders."""
    sql = "SELECT kind, subject, reason, added_at, added_by FROM hub_blocklist"
    args: list[Any] = []
    if kind:
        if kind not in KINDS:
            raise BlockError(f"unknown block kind: {kind!r}")
        sql += " WHERE kind = ?"
        args.append(kind)
    sql += " ORDER BY added_at DESC"
    with db.cursor() as cur:
        rows = cur.execute(sql, args).fetchall()
    return [
        {"kind": k, "subject": s, "reason": r, "added_at": a.isoformat() if a else None, "added_by": b}
        for k, s, r, a, b in rows
    ]


def filter_path(path: list[str]) -> str | None:
    """The first blocked hub on a result's provenance chain, or None when the whole route is clean.

    A card is dropped when *any* hub that carried it is blocked, not only the one that handed it
    over. Blocking a hub that simply relays for a blocked one would otherwise achieve nothing.
    """
    blocked = blocked_hubs()
    return next((hub for hub in path if hub in blocked), None)
