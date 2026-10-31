"""The peer hubs this hub asks, as rows an operator can change while the hub is running.

Peers used to be `HIVE_PEER_URLS` and nothing else: an environment variable read once at import,
so adding a neighbour meant editing a deployment and restarting. That is not administration, it is
a redeploy, and a hub whose neighbour list only a deployer can change is not a hub an operator runs.

So the list lives here, in `hub_peers`, shaped like `blocklist.py`: a table, a reason required on
every change, and a row that can still be read in six months. The environment variable keeps one
job — **the seed for a fresh hub**. `init()` copies it in the first time the table is empty, and
after that the table is the live list and the variable is history. That matters for removal: once
anything is stored, including a removal, the environment is never consulted again, so a peer an
operator dropped does not come back at the next restart.

`federation._choose_peers` reads `urls()`, so a peer added here is asked by the very next search
above radius 0 — no restart, no redeploy. There is no cache to invalidate, because the list is read
per query.

**Removing a peer is not blocking it.** Removing says *this hub no longer asks that one and no
longer carries what it relays*; the peer is free to exist and this hub is free to add it back
tomorrow. Blocking (`blocklist.py`, kind `hub`) says *refuse it in both directions, and drop any
card that travelled through it even when another peer hands it over*. An operator reaching for the
wrong one of those gets a surprise either way, which is why both say so on screen.

This module answers *which peers exist*. It deliberately does not answer *who a peer is* or *whether
it is answering*: `federation.py` keeps that in its own book, asked in the background every
`PEER_ASK_SECONDS` and read back by `federation.peer_row` without fetching anything. Two stores for
one fact would drift, and an admin page that showed two different answers to "is this hub up" would
be worse than one that showed none.

So nothing here reaches out to a peer, and neither does the admin peer page: it is this table joined
with what the background asking already learned. An unreachable peer therefore costs an admin page
nothing — it reads as not answering, with the time it was last tried.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from . import audit, config, db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_peers (
    url VARCHAR PRIMARY KEY,
    hub_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    note VARCHAR,
    state VARCHAR NOT NULL,
    added_at TIMESTAMP NOT NULL,
    added_by VARCHAR,
    changed_at TIMESTAMP,
    removed_at TIMESTAMP,
    removed_reason VARCHAR
);
"""

ACTIVE = "active"
REMOVED = "removed"

MAX_URL = 300
MAX_NAME = 200
MAX_REASON = 500


class PeerError(ValueError):
    """A peer change this hub refuses, such as a URL that is not http(s) or a change with no reason."""


def init() -> None:
    """Create the table and, on a hub that has never been administered, seed it from the environment."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)
    if _rows_exist():
        return
    for url in config.HIVE_PEER_URLS:
        try:
            add(url, reason="seeded from HIVE_PEER_URLS when this hub first started", added_by="env")
        except PeerError:  # a malformed value in the environment is not a reason to refuse to boot
            continue


def _rows_exist() -> bool:
    with db.cursor() as cur:
        return bool(cur.execute("SELECT count(*) FROM hub_peers").fetchone()[0])


def hub_id_for(url: str) -> str:
    """The id to assume for a peer nobody has asked yet: its host, the same guess `admin.py` makes."""
    return url.strip().rstrip("/").split("//")[-1]


def canonical_url(url: str) -> str:
    """Normalise and check a peer URL. Raises `PeerError` when it is not an http(s) address."""
    url = (url or "").strip().rstrip("/")
    if not url:
        raise PeerError("a peer needs a URL")
    if len(url) > MAX_URL:
        raise PeerError(f"a peer URL is at most {MAX_URL} characters")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PeerError(f"a peer URL must be http(s) with a host, not {url!r}")
    return url


def _reason(reason: str) -> str:
    """Every peer change carries why. An operator reading this list later has to be able to tell."""
    reason = (reason or "").strip()
    if not reason:
        raise PeerError("a peer change needs a reason: someone has to be able to read this list later")
    return reason[:MAX_REASON]


def urls() -> list[str]:
    """The live peer list federation asks, oldest first.

    The stored rows, or the environment seed while nothing at all has been stored. A table with any
    row in it — an active peer or a removed one — is the whole answer, so a removal sticks.
    """
    with db.cursor() as cur:
        rows = cur.execute("SELECT url, state FROM hub_peers ORDER BY added_at, url").fetchall()
    if not rows:
        return list(config.HIVE_PEER_URLS)
    return [url for url, state in rows if state == ACTIVE]


def get(url: str) -> dict[str, Any] | None:
    """One stored peer row, removed ones included, or None."""
    with db.cursor() as cur:
        found = db.rows(cur.execute("SELECT * FROM hub_peers WHERE url = ?", [canonical_url(url)]))
    return _readable(found[0]) if found else None


def _readable(row: dict[str, Any]) -> dict[str, Any]:
    """One row as an interface wants it: timestamps as text, and the id guessed when nobody has asked."""
    out = dict(row)
    for key in ("added_at", "changed_at", "removed_at"):
        value = out.get(key)
        out[key] = value.isoformat() if isinstance(value, datetime) else None
    out["hub"] = out.get("hub_id") or hub_id_for(out["url"])
    return out


def listing(include_removed: bool = True) -> list[dict[str, Any]]:
    """Every stored peer, oldest first. This is what the admin peers table renders."""
    sql = "SELECT * FROM hub_peers"
    args: list[Any] = []
    if not include_removed:
        sql += " WHERE state = ?"
        args.append(ACTIVE)
    sql += " ORDER BY added_at, url"
    with db.cursor() as cur:
        return [_readable(r) for r in db.rows(cur.execute(sql, args))]


def add(
    url: str, reason: str, hub_id: str = "", name: str = "", note: str = "", added_by: str = "admin"
) -> dict[str, Any]:
    """Add a peer, or bring a removed one back. The next federated search asks it.

    Re-adding a URL that is already active is refused rather than silently doing nothing: an
    operator who typed it twice should be told, not left wondering which of the two took.
    """
    url = canonical_url(url)
    reason = _reason(reason)
    existing = get(url)
    if existing and existing["state"] == ACTIVE:
        raise PeerError(f"{url} is already a peer of this hub")
    now = datetime.now(UTC).replace(tzinfo=None)
    with db.write() as cur:
        cur.execute("DELETE FROM hub_peers WHERE url = ?", [url])
        cur.execute(
            "INSERT INTO hub_peers (url, hub_id, name, note, state, added_at, added_by, changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                url,
                hub_id.strip()[:MAX_NAME],
                name.strip()[:MAX_NAME],
                note.strip()[:MAX_REASON],
                ACTIVE,
                now,
                added_by,
                now,
            ],
        )
    audit.record("peer.add" if not existing else "peer.readd", url, reason, credential=added_by)
    return get(url) or {}


def edit(
    url: str,
    reason: str,
    hub_id: str | None = None,
    name: str | None = None,
    note: str | None = None,
    changed_by: str = "admin",
) -> dict[str, Any]:
    """Change what this hub records about a peer. Only the fields given are touched."""
    url = canonical_url(url)
    reason = _reason(reason)
    row = get(url)
    if row is None:
        raise PeerError(f"{url} is not a peer of this hub")
    changes = {
        key: value.strip()[: MAX_NAME if key != "note" else MAX_REASON]
        for key, value in (("hub_id", hub_id), ("name", name), ("note", note))
        if value is not None
    }
    if not changes:
        raise PeerError("an edit has to change something")
    sets = ", ".join(f"{key} = ?" for key in changes) + ", changed_at = ?"
    with db.write() as cur:
        cur.execute(
            f"UPDATE hub_peers SET {sets} WHERE url = ?",
            [*changes.values(), datetime.now(UTC).replace(tzinfo=None), url],
        )
    audit.record(
        "peer.edit", url, reason, credential=changed_by, detail="; ".join(f"{k}={v}" for k, v in changes.items())
    )
    return get(url) or {}


def remove(url: str, reason: str, removed_by: str = "admin") -> dict[str, Any]:
    """Stop asking a peer. Not a block: nothing is refused, this hub simply no longer reaches out.

    The row stays, marked `removed`, which is what keeps the environment seed from putting the peer
    back at the next restart and what lets the ledger name a URL that is no longer a live peer.
    """
    url = canonical_url(url)
    reason = _reason(reason)
    row = get(url)
    if row is None or row["state"] != ACTIVE:
        raise PeerError(f"{url} is not a peer of this hub")
    now = datetime.now(UTC).replace(tzinfo=None)
    with db.write() as cur:
        cur.execute(
            "UPDATE hub_peers SET state = ?, removed_at = ?, removed_reason = ?, changed_at = ? WHERE url = ?",
            [REMOVED, now, reason, now, url],
        )
    audit.record("peer.remove", url, reason, credential=removed_by)
    return get(url) or {}
