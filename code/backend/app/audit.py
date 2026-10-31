"""The admin ledger: what an operator changed, when, and why.

Every other store in this hub records a fact about the world — a card, a booking, a rating. This
one records a decision about the hub itself: a peer added, a peer dropped, an entity withdrawn from
the index. Those are the changes nobody else can see the reason for afterwards, so the reason is
stored with them rather than left in an operator's memory.

**"Who" is thin here, and the honest answer is to say so rather than to invent a name.** This hub
has one shared `ADMIN_PASSWORD` and one shared `ADMIN_TOKEN`, so there are no operator accounts and
no way to tell two operators apart. What can be recorded is recorded: the time, the action, the
subject, the reason, and *which credential* was used — the static token (curl, CI) or a browser
session minted from the password. For an operator's decision `actor` is therefore always `admin`,
which is a limit of the design, not of the ledger. Per-operator accounts are the fix, and
`SECURITY.md` says so.

The one kind of row that *can* name who acted is a folder read (`folders.py`, `folder_keys.py`):
there the caller presented a secret bound to one link, which identifies a handle rather than an
operator. Those rows carry that handle as their `actor`, because an owner who grants a path should
be able to see who used it. `WHO_LIMIT` says which is which.

Nothing in here is ever deleted or rewritten. A withdrawal that was a mistake is undone by a
restore, which is its own row; the mistake stays visible, because a ledger that can be tidied is
not a ledger.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_admin_log (
    id VARCHAR PRIMARY KEY,
    -- `at` is a reserved word in DuckDB; the column is spelled out and the API still calls it `at`.
    happened_at TIMESTAMP NOT NULL,
    action VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    actor VARCHAR NOT NULL,
    credential VARCHAR NOT NULL,
    detail VARCHAR
);
"""

#: The one operator this hub can name. See the module docstring: it is a shared secret, not a person.
ACTOR = "admin"

#: What the ledger can and cannot prove, in one line an interface can print next to the rows.
WHO_LIMIT = (
    "This hub has one shared admin password, so every operator row reads 'admin'. The time, the "
    "reason and which credential was used are real; the person is not recorded, because the hub "
    "cannot tell. A folder read names its actor, because a link secret identifies a handle."
)

MAX_REASON = 500


def init() -> None:
    """Create the ledger table."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


def record(
    action: str,
    subject: str,
    reason: str,
    credential: str = "unknown",
    detail: str = "",
    actor: str = ACTOR,
) -> dict[str, Any]:
    """Append one decision to the ledger and return the row as written.

    `action` is a short code (`peer.add`, `entity.remove`), `subject` the thing it was done to,
    `reason` the operator's own words. Callers check the reason before getting here; this stores
    whatever it is given, because a ledger that edits its entries is worth nothing.

    `actor` defaults to the one operator this hub can name. A folder read passes the handle that
    presented the link secret instead — see the module docstring for why that one is real.
    """
    row = {
        "id": db.new_id(),
        "at": datetime.now(UTC).replace(tzinfo=None),
        "action": action,
        "subject": subject,
        "reason": (reason or "")[:MAX_REASON],
        "actor": actor or ACTOR,
        "credential": credential or "unknown",
        "detail": detail[:MAX_REASON],
    }
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hub_admin_log (id, happened_at, action, subject, reason, actor, credential, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [row[k] for k in ("id", "at", "action", "subject", "reason", "actor", "credential", "detail")],
        )
    return {**row, "at": row["at"].isoformat()}


def entries(subject: str = "", action_prefix: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """The ledger, newest first, optionally narrowed to one subject or one family of actions."""
    sql = "SELECT id, happened_at AS at, action, subject, reason, actor, credential, detail FROM hub_admin_log"
    where, args = [], []
    if subject:
        where.append("subject = ?")
        args.append(subject)
    if action_prefix:
        where.append("action LIKE ?")
        args.append(f"{action_prefix}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY happened_at DESC, id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 1000)))
    with db.cursor() as cur:
        rows = db.rows(cur.execute(sql, args))
    for row in rows:
        row["at"] = row["at"].isoformat() if row["at"] else None
    return rows
