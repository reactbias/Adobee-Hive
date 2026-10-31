"""Entities this hub no longer carries: a withdrawal, never a delete.

An operator has to be able to kick an entity out — a business that turned out to be a front, a
person who asked to be taken off, a card that is simply not this hub's to carry. The question is
what "out" means to the data, and there are only two honest answers.

**A hard delete is not available to us.** `hive_card_history` keeps every signed version so that a
booking receipt can later prove what a card said on the day it was booked; that is the *What was
promised* guarantee in `SECURITY.md`, and `hive.what_was_promised` is the code that keeps it. Delete
the rows and a guest holding a signed receipt can no longer be shown the terms they agreed to, and
the hub has quietly broken a promise it made to someone who is no longer around to object. The
guest is not the party being removed, and removing a business must not cost its past guests their
evidence.

**So removal is a withdrawal: the hub stops carrying the entity, and keeps what it signed.** The
card and its history stay exactly as they were, and this table says the hub no longer offers the
entity. A withdrawn entity is gone from `hive.list_cards`, therefore gone from discovery — out of
the matches *and* out of the excluded list, because being named as excluded is still being named —
and `hive.book` and `hive.check_availability` refuse it. Receipts, reviews and
`hive.what_was_promised` keep working, because they read history, not the index.

**A reason is required**, exactly as `blocklist.py` requires one, and for the same reason: "why is
this business missing" is a question the interface has to be able to answer six months later.

**Removing is not blocking.** Removing is about *this hub* no longer carrying an entity; the entity
is free to be carried by another hub, and a federated search still finds it there. Blocking
(`blocklist.py`, kind `entity`) is about refusing it wherever it comes from, including over a peer.
An operator usually wants removal for "not ours to carry" and a block for "not to be trusted
anywhere", and the two are offered side by side so the choice is deliberate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import audit, db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_removals (
    entity_id VARCHAR PRIMARY KEY,
    reason VARCHAR NOT NULL,
    removed_at TIMESTAMP NOT NULL,
    removed_by VARCHAR
);
"""

MAX_REASON = 500


class RemovalError(ValueError):
    """A removal this hub refuses: no entity, no reason, or an entity it does not carry."""


def init() -> None:
    """Create the table."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


def _check(entity_id: str, reason: str = "x") -> tuple[str, str]:
    entity_id = (entity_id or "").strip()
    reason = (reason or "").strip()
    if not entity_id:
        raise RemovalError("a removal needs an entity")
    if not reason:
        raise RemovalError("a removal needs a reason: someone has to be able to read this list later")
    return entity_id, reason[:MAX_REASON]


def withdraw(entity_id: str, reason: str, removed_by: str = "admin") -> dict[str, Any]:
    """Stop carrying an entity. Its signed card and every signed version of it are kept.

    Raises `RemovalError` without a reason, and `hive.HiveError` when this hub has no such entity:
    withdrawing something that was never here is a typo, and a silent success would hide it.
    """
    from . import hive

    entity_id, reason = _check(entity_id, reason)
    if hive.get_record(entity_id) is None:
        raise hive.HiveError(f"No Hive card '{entity_id}'.")
    now = datetime.now(UTC).replace(tzinfo=None)
    with db.write() as cur:
        cur.execute("DELETE FROM hub_removals WHERE entity_id = ?", [entity_id])
        cur.execute(
            "INSERT INTO hub_removals (entity_id, reason, removed_at, removed_by) VALUES (?, ?, ?, ?)",
            [entity_id, reason, now, removed_by],
        )
    hive.record_event(entity_id, "withdrawn", reason)
    audit.record("entity.remove", entity_id, reason, credential=removed_by)
    return {
        "entity_id": entity_id,
        "carried": False,
        "reason": reason,
        "removed_at": now.isoformat(),
        "removed_by": removed_by,
        # Said out loud in the answer, because it is the whole argument for a withdrawal.
        "history_kept": True,
    }


def restore(entity_id: str, reason: str, restored_by: str = "admin") -> dict[str, Any]:
    """Carry an entity again. The withdrawal row goes; the ledger keeps both decisions."""
    from . import hive

    entity_id, reason = _check(entity_id, reason)
    if not is_withdrawn(entity_id):
        raise RemovalError(f"{entity_id} is carried by this hub already")
    with db.write() as cur:
        cur.execute("DELETE FROM hub_removals WHERE entity_id = ?", [entity_id])
    hive.record_event(entity_id, "restored", reason)
    audit.record("entity.restore", entity_id, reason, credential=restored_by)
    return {"entity_id": entity_id, "carried": True, "reason": reason}


def is_withdrawn(entity_id: str) -> bool:
    """Whether this hub has stopped carrying an entity."""
    if not entity_id:
        return False
    with db.cursor() as cur:
        row = cur.execute("SELECT 1 FROM hub_removals WHERE entity_id = ?", [(entity_id or "").strip()]).fetchone()
    return row is not None


def withdrawn() -> set[str]:
    """Every withdrawn entity, for filtering a whole index at once. The hot path, called per search."""
    with db.cursor() as cur:
        return {r[0] for r in cur.execute("SELECT entity_id FROM hub_removals").fetchall()}


def entries() -> list[dict[str, Any]]:
    """Every withdrawal with its reason, newest first. What the admin entities view renders."""
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT entity_id, reason, removed_at, removed_by FROM hub_removals ORDER BY removed_at DESC"
        ).fetchall()
    return [
        {"entity_id": e, "reason": r, "removed_at": a.isoformat() if a else None, "removed_by": b}
        for e, r, a, b in rows
    ]
