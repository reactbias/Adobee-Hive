"""Who is asking: a secret bound to one folder link, so a read has a caller.

`folders.py` decides access and moves no bytes. Every decision it makes needs a *handle* — and
until this module there was no way for an HTTP request to prove it was one. `grep -cE "token|secret"
app/folders.py` found one incidental hit. A read route without a caller identity serves everything
or nothing, so this comes before the routes do.

**The link is the credential, not an account.** When a link is accepted, one party is handed a
secret of 32 random bytes. Presenting it in `Authorization: Bearer <secret>` resolves to the handle
that holds it and the peer on the other end of that link:

    Authorization: Bearer <secret>   ->   (key id, link id, handle, peer)

Why the link and not an account, of which this hub has none: the link is already the unit of trust
and already revocable, so revoking it kills its reads with it and there is no second set of books to
keep in step. `resolve` therefore re-reads the link's state on **every** request rather than trusting
anything cached — a revoked link stops reading on the next call, not at a cache expiry.

Three rules the rest of the hub relies on:

- **Hashed at rest.** Only `sha256(secret)` is stored. A stolen database dump is not a stolen folder.
  A plain digest and not a slow KDF on purpose: the secret is 32 bytes from `secrets`, so there is no
  guessable password here to stretch, and a lookup by digest is what makes `resolve` one indexed read.
- **Returned exactly once.** `mint` is the only call that ever puts the plaintext in a response. It
  is not stored, so nothing can hand it out a second time; a party that loses it mints another.
- **Never logged.** The secret is not in an exception message, a log line or the audit ledger. What
  the ledger records is the key *id* and the handle, which is the part an owner needs to read.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from . import db, folders

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS folder_keys (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    link_id VARCHAR NOT NULL,
    handle VARCHAR NOT NULL,
    peer VARCHAR NOT NULL,
    secret_sha256 VARCHAR NOT NULL,
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP
);
"""

#: Bytes of entropy in a link secret. 32 is what ClaudeConnect's own bot tokens carry, and far past
#: anything brute-forceable through a rate-limited HTTP endpoint.
SECRET_BYTES = 32

#: Looking a secret up: by digest, and never a revoked key. Spelled once because both doors that
#: take a secret ask it — `resolve` for a read and `party_of` for who is holding it — and a lookup
#: that forgot `revoked_at` in one of them would leave a revoked key working at the other.
_LIVE_KEY = "SELECT id, link_id, handle, peer FROM folder_keys WHERE secret_sha256 = ? AND revoked_at IS NULL"

#: The header a read presents it in. Spelled once, so the docs and the routes cannot drift.
HEADER = "Authorization"
SCHEME = "Bearer"


class KeyError_(ValueError):
    """A link key that cannot be minted or resolved as asked."""


def init() -> None:
    """Create the table. Idempotent, and safe to call beside `folders.init`."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def fingerprint(secret: str) -> str:
    """The stored form of a secret. The only thing this module ever writes down about it."""
    return hashlib.sha256((secret or "").encode()).hexdigest()


def parties(link: dict[str, Any], handle: str) -> tuple[str, str]:
    """This handle and the one at the other end of the link, refused if it is party to neither.

    A key names a side of a link rather than a direction of reading, because both sides of one link
    do the same two things with it: read what the other has granted, and grant from their own
    folder. Deriving the peer here, once, is what lets the read routes take no handle parameter at
    all — and an endpoint that takes no handle has no enumeration surface to abuse.
    """
    name = folders.check_handle(handle)
    a, b = link["from_handle"], link["to_handle"]
    if name == a:
        return a, b
    if name == b:
        return b, a
    raise KeyError_(f"{name} is not a party to folder link {link['id']}")


def mint(link_id: str, handle: str, *, pending_ok: bool = False) -> dict[str, Any]:
    """Mint a key for one party to an established link, and return the secret **once**.

    Refused on a link that is not established: a secret for a handshake the other side has not
    accepted would be a capability handed out before consent. The plaintext is in the returned dict
    under `secret` and nowhere else — not in the database, and not in anything this module logs.

    `pending_ok` mints on a link still waiting for the other side, and grants nothing by doing so.
    `resolve` re-reads the link's state on **every** request, so such a key reads nothing until the
    other side accepts, and stops reading again the moment the link is revoked — the key is a name
    for a side of a link, and the link is what decides. One caller needs that: `hub.connect`, which
    speaks for the requester it names and is the requester's only chance to be handed a credential
    for the introduction it just made. Without it a `confirm` introduction had no requester-side
    proof in existence, so the person who asked for the meeting could not prove it was theirs to
    score (#107). Refusing here would have moved the problem, not solved it.
    """
    link = folders.get_link(link_id)
    if link["state"] != folders.ESTABLISHED and not pending_ok:
        raise KeyError_(
            f"folder link {link_id} is {link['state']}, not established; there is nothing to read with a key yet"
        )
    me, peer = parties(link, handle)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    key_id = f"fk-{db.new_id()}"
    with db.write() as cur:
        cur.execute(
            "INSERT INTO folder_keys (id, created_at, link_id, handle, peer, secret_sha256) VALUES (?,?,?,?,?,?)",
            [key_id, _now(), link["id"], me, peer, fingerprint(secret)],
        )
    return {"id": key_id, "link": link["id"], "handle": me, "peer": peer, "secret": secret, "scheme": SCHEME}


def resolve(secret: str) -> dict[str, Any] | None:
    """Who is holding this secret, or None — for a wrong one, a revoked one, or a revoked link.

    The link's state is read here, on every request. That is the whole reason the credential is
    bound to the link: `folders.revoke_link` makes this return None on the next call, with no
    session store to expire and no window in which a withdrawn link still serves bytes.
    """
    if not secret:
        return None
    with db.cursor() as cur:
        row = cur.execute(
            _LIVE_KEY,
            [fingerprint(secret)],
        ).fetchone()
    if row is None:
        return None
    key = {"id": row[0], "link": row[1], "handle": row[2], "peer": row[3]}
    try:
        link = folders.get_link(key["link"])
    except folders.FolderError:
        return None
    if link["state"] != folders.ESTABLISHED:
        return None
    return key


def party_of(secret: str) -> dict[str, Any] | None:
    """Which side of which link holds this secret, or None. **Not** permission to read anything.

    `resolve` is the read door and refuses a link that is not established, because reading what the
    other side has not yet agreed to share would be a capability ahead of consent. This answers a
    different question: *who is holding this*. A key names a side of a link from the moment it is
    minted, and that is a fact about the holder rather than a grant.

    One caller needs the distinction. An introduction waiting for its owner's yes stands on a link
    that is, by definition, not established yet — so the owner's own credential for the row could
    never be checked through `resolve`, and the decision would have had nothing per-party behind it
    at all (#107). Authority over a connection row is not access to a folder, and conflating the two
    is what made this look impossible.

    A revoked key is nobody, and so is a key on a revoked link: both are read here on every call,
    with no cache to expire, exactly as `resolve` does it.
    """
    if not secret:
        return None
    with db.cursor() as cur:
        row = cur.execute(
            _LIVE_KEY,
            [fingerprint(secret)],
        ).fetchone()
    if row is None:
        return None
    key = {"id": row[0], "link": row[1], "handle": row[2], "peer": row[3]}
    try:
        link = folders.get_link(key["link"])
    except folders.FolderError:
        return None
    return None if link["state"] == folders.REVOKED else key


def touch(key_id: str) -> None:
    """Note that this key was used, so an owner can see a grant of theirs is live."""
    with db.write() as cur:
        cur.execute("UPDATE folder_keys SET last_used_at = ? WHERE id = ?", [_now(), key_id])


def revoke(key_id: str) -> bool:
    """Retire one key. True when it was live until now."""
    with db.write() as cur:
        row = cur.execute("SELECT id FROM folder_keys WHERE id = ? AND revoked_at IS NULL", [key_id]).fetchone()
        if row is None:
            return False
        cur.execute("UPDATE folder_keys SET revoked_at = ? WHERE id = ?", [_now(), key_id])
    return True


def revoke_for_link(link_id: str) -> int:
    """Retire every key on one link, and say how many. Called when the link itself is revoked.

    Belt and braces: `resolve` already refuses a key whose link is not established, so revoking the
    link is enough on its own. Marking the rows too means the ledger shows when each key died rather
    than leaving it to be inferred from the link.
    """
    with db.write() as cur:
        rows = cur.execute("SELECT id FROM folder_keys WHERE link_id = ? AND revoked_at IS NULL", [link_id]).fetchall()
        if rows:
            cur.execute(
                "UPDATE folder_keys SET revoked_at = ? WHERE link_id = ? AND revoked_at IS NULL",
                [_now(), link_id],
            )
    return len(rows)


def keys_for(link_id: str) -> list[dict[str, Any]]:
    """The keys on one link, newest first and without a word about their secrets."""
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT id, created_at, link_id, handle, peer, last_used_at, revoked_at FROM folder_keys"
            " WHERE link_id = ? ORDER BY created_at DESC",
            [link_id],
        ).fetchall()
    keys = ("id", "created_at", "link", "handle", "peer", "last_used_at", "revoked_at")
    out = []
    for row in rows:
        item = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in zip(keys, row, strict=True)}
        out.append({**item, "live": item["revoked_at"] is None})
    return out


def bearer(header_value: str) -> str:
    """The secret out of an `Authorization` header, or `""` for anything that is not our scheme.

    Lenient about the scheme's case, as RFC 7235 requires, and about nothing else. A header that is
    not a bearer token yields the empty string, which `resolve` turns into None — the same answer a
    wrong secret gets, because "you sent no credential" and "you sent a bad one" are both just no.
    """
    scheme, _, rest = (header_value or "").strip().partition(" ")
    return rest.strip() if scheme.lower() == SCHEME.lower() else ""
