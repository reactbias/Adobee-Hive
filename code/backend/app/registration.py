"""Joining a hub: one signed JSON document, and what the hub does with it.

A registration is not an account. It is an **application**, and the hub is free to refuse it. That
matters more than it sounds: a hub's standing with its peers is measured by whether its published
ratings survive contact with real people (see calibration.py), so a hub that lets anyone in will
publish claims it cannot stand behind, its error will climb, and *every* entity it carries will
rank lower everywhere. Vetting is self-interest, not altruism. It is the reason a federated
directory can work without anybody in charge.

## The journey

1. The applicant generates an Ed25519 keypair. **The private key never leaves their machine.**
2. They compose the application below and sign the canonical JSON of everything except
   `signature`.
3. `POST /api/hub/register`, or the `hub_register` MCP tool if an agent is doing it for them.
4. The hub runs the checks in `CHECKS`, in order, and stops at the first that fails.
5. Depending on `ADMISSION_POLICY` the application is admitted at once, queued for a human, or
   refused — always with a reason, and always with what to do next.
6. On admission the entity is published into the index and is findable.

```json
{
  "entity": {"id": "hotel-krafft", "kind": "stay", "name": "...", "description": "...",
             "sharing": "public"},
  "public_key": "<base64 Ed25519>",
  "proofs": [{"type": "dns-txt", "subject": "hotelkrafft.example"}],
  "invite": "<token, when the hub is invite-only>",
  "signature": "<base64, over the canonical JSON of this document without `signature`>"
}
```

## What the signature proves, and what it does not

It proves the applicant holds the private key for `public_key`. That is all, and it is enough to
pin an identity: from then on the hub can tell this applicant from anyone claiming to be them.

It proves nothing about who they are in the world. That is what `proofs` are for, and they are
recorded rather than trusted — no proof is checked over the network during registration, because
the demo has to run offline and because a hub that blocks on a DNS lookup is a hub that falls over
when a registrar does. An unconfirmed proof raises nothing; a confirmed one raises the entity's
`verification`, which peers weigh against what they actually observe.

## Key custody

Bringing a `public_key` means the owner holds the signing key and the hub pins the public half.
Leaving it out falls back to the hub generating and holding the key, which is what the demo does
today and is recorded honestly as `custody: "hub"` rather than being dressed up. A peer can see
the difference, and should.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from . import blocklist, config, db, guard, hive, limits

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_applications (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    state VARCHAR NOT NULL,
    entity_id VARCHAR NOT NULL,
    kind VARCHAR,
    name VARCHAR,
    public_key VARCHAR,
    custody VARCHAR,
    verification VARCHAR,
    proofs VARCHAR,
    payload VARCHAR,
    checks VARCHAR,
    decided_at TIMESTAMP,
    decided_by VARCHAR,
    reason VARCHAR,
    withdraw_sha256 VARCHAR
);
"""

PENDING, ADMITTED, REJECTED, WITHDRAWN = "pending", "admitted", "rejected", "withdrawn"

#: How much the hub actually established, lowest first. A hub declares the level it aims at; peers
#: weigh the claim against what they observe, which is why overstating it is a bad trade.
LADDER = ("none", "signed", "domain", "identity")

OPEN, VETTED, INVITE, CLOSED = "open", "vetted", "invite", "closed"
POLICIES = (OPEN, VETTED, INVITE, CLOSED)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PROOF_TYPES = ("dns-txt", "rel-me", "email")
#: One source for how many claims an application may carry: `limits.py` publishes it, and
#: `_check_size` bounds what each one says.
MAX_PROOFS = limits.MAX_PROOFS


class RegistrationError(ValueError):
    """An application that cannot be accepted as submitted."""


def init() -> None:
    """Create the table, and add `withdraw_sha256` to one that predates it.

    Added rather than assumed, like `connections.folder_link`: the demo hub has a Postgres snapshot
    of applications written before withdrawal needed proving. Such a row has no capability and
    `withdraw` says so instead of falling over — see `withdraw`.
    """
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)
        held = {r[1] for r in cur.execute("PRAGMA table_info('hub_applications')").fetchall()}
        if "withdraw_sha256" not in held:
            cur.execute("ALTER TABLE hub_applications ADD COLUMN withdraw_sha256 VARCHAR")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def unsigned(application: dict[str, Any]) -> dict[str, Any]:
    """The document as it was signed: everything but the signature itself."""
    return {k: v for k, v in application.items() if k != "signature"}


# ---------------------------------------------------------------- the checks


def _check_shape(app: dict[str, Any], _: dict) -> tuple[bool, str]:
    entity = app.get("entity")
    if not isinstance(entity, dict):
        return False, "the application needs an `entity` object"
    entity_id = str(entity.get("id") or "").strip().lower()
    if not ID_RE.match(entity_id):
        return False, "an id is 2 to 63 characters of lower-case letters, digits and hyphens"
    if not str(entity.get("name") or "").strip():
        return False, "an entity needs a name: it is what a person sees in a result"
    if not str(entity.get("kind") or "").strip():
        return False, "an entity needs a kind, so searches can tell a room from a person"
    proofs = app.get("proofs") or []
    if not isinstance(proofs, list) or len(proofs) > MAX_PROOFS:
        return False, f"proofs is a list of at most {MAX_PROOFS} entries"
    for proof in proofs:
        if not isinstance(proof, dict) or proof.get("type") not in PROOF_TYPES:
            return False, f"each proof needs a type, one of {', '.join(PROOF_TYPES)}"
    return True, "well formed"


def _check_size(app: dict[str, Any], _: dict) -> tuple[bool, str]:
    """Refuse an application that carries more than this hub accepts, naming the limit and the size.

    Before the signature on purpose: verifying a 20 MB document is exactly the work not worth doing,
    and the limits are published (`documentation/cards/README.md`) so this is never a surprise.
    """
    reason = limits.application_refusal(app)
    return (False, reason) if reason else (True, "within the sizes this hub publishes")


def _check_signature(app: dict[str, Any], _: dict) -> tuple[bool, str]:
    """Prove the applicant holds the key they are registering. Skipped when the hub will hold it."""
    public_key = str(app.get("public_key") or "").strip()
    if not public_key:
        return True, "no key offered: this hub will generate and hold one (demo custody)"
    signature = str(app.get("signature") or "").strip()
    if not signature:
        return False, "an application that brings a public key must be signed with the private half"
    try:
        ok = hive.verify(unsigned(app), signature, public_key)
    except Exception:
        return False, "the signature or the key is not readable"
    if not ok:
        return False, "the signature does not match the key offered"
    return True, "signature valid: the applicant holds this key"


def _check_not_blocked(app: dict[str, Any], _: dict) -> tuple[bool, str]:
    entity_id = str(app["entity"]["id"]).strip().lower()
    if blocklist.is_blocked(blocklist.ENTITY, entity_id):
        return False, f"{entity_id} is blocked on this hub"
    for proof in app.get("proofs") or []:
        subject = str(proof.get("subject") or "")
        if subject and blocklist.is_blocked(blocklist.ENTITY, subject):
            return False, f"{subject} is blocked on this hub"
    return True, "not on the blocklist"


def _check_not_taken(app: dict[str, Any], _: dict) -> tuple[bool, str]:
    entity_id = str(app["entity"]["id"]).strip().lower()
    if hive.get_record(entity_id) is not None:
        return False, f"{entity_id} is already registered here; choose another id"
    with db.cursor() as cur:
        clash = cur.execute(
            "SELECT id FROM hub_applications WHERE entity_id = ? AND state IN (?, ?)",
            [entity_id, PENDING, ADMITTED],
        ).fetchone()
    return (False, f"{entity_id} is already applied for") if clash else (True, "the id is free")


def _check_invite(app: dict[str, Any], _: dict) -> tuple[bool, str]:
    if config.ADMISSION_POLICY != INVITE:
        return True, "this hub does not require an invite"
    offered = str(app.get("invite") or "").strip()
    if offered and offered in config.INVITE_TOKENS:
        return True, "invite accepted"
    return False, "this hub is invite-only and the invite is missing or not recognised"


#: Run in order; the first failure stops the application. Order is deliberate — shape before
#: signature so a malformed document gets a useful answer, size before the signature so nobody
#: pays Ed25519 for a 20 MB document, and blocklist before anything expensive.
CHECKS = (
    ("shape", _check_shape),
    ("size", _check_size),
    ("signature", _check_signature),
    ("blocklist", _check_not_blocked),
    ("availability", _check_not_taken),
    ("invite", _check_invite),
)


def verification_for(app: dict[str, Any], checks: list[dict[str, Any]]) -> str:
    """What the hub actually established, which is rarely what the applicant claimed.

    Holding the key proves continuity of identity and nothing more, so a signed application sits at
    `signed`. Proofs are recorded unconfirmed and raise nothing until something checks them, because
    a claim is not a verification.
    """
    signed = bool(str(app.get("public_key") or "").strip()) and any(
        c["check"] == "signature" and c["ok"] for c in checks
    )
    return "signed" if signed else "none"


# ---------------------------------------------------------------- withdrawing it again
#
# A pending application is a state transition waiting to happen, and it used to need nothing to make
# it happen: knowing the application id — which `GET /api/hub/register/{id}` hands to anybody — was
# enough to withdraw somebody else's application, and the row then said "withdrawn by the applicant"
# about an act the applicant knew nothing about. The authorized admin could no longer admit it,
# because it was no longer pending (#108).
#
# An id is a lookup, never a credential. So withdrawal takes one of three things, and the row records
# which of the three it actually was rather than crediting the applicant for all of them:
#
# - a **signed action** under the key the applicant registered, for an application that brought one.
#   The strongest of the three and the only one tied to *this* applicant: nothing the hub holds could
#   produce it. It binds the application id, the action, a nonce and an expiry, so it authorises one
#   withdrawal of one application inside a window and cannot be replayed onto anything else.
# - a **capability**, for an application whose key the hub holds, which has no applicant signature to
#   check. 32 bytes from `secrets`, returned exactly once by `apply`, stored only as SHA-256, and
#   absent from every read — `SELECT` does not name the column, so no queue, status or log can leak
#   it. Same contract as a `folder_keys` link secret, for the same reason.
# - the **operator**, as an explicitly separate administrative act behind the admin credential.
#
# Nothing else. With no proof the application is untouched, which is the opposite of the owner-edit
# REST route's "an unset secret means the check is off" — there is no secret to be unset here, the
# applicant's proof either exists or does not, so this fails closed like `guard.require_admin`.

#: How long a signed withdrawal is good for, when the applicant does not say. Short: it authorises a
#: destructive act, and a window is the only thing bounding a signature that has been captured.
WITHDRAW_WINDOW_S = 300

#: Bytes of entropy in a withdrawal capability. 32, as `folder_keys.SECRET_BYTES`.
WITHDRAW_SECRET_BYTES = 32

#: The header the capability travels in. A header and not a field, for the reason `owner.TOKEN_HEADER`
#: gives: a tool argument is written into the agent's transcript and its client's logs, and a shared
#: secret written down in two places is no longer one secret. It is also kept out of the URL, so it
#: cannot be read back out of a proxy log or a browser history.
KEY_HEADER = "X-Application-Key"

#: Who the row credits. `applicant` only where an applicant proof was actually shown.
BY_SIGNATURE, BY_CAPABILITY, BY_OPERATOR = "applicant (signed)", "applicant (capability)", "hub operator"

WITHDRAW_ACTION = "withdraw"


def fingerprint(secret: str) -> str:
    """The stored form of a withdrawal capability. The only thing ever written down about it."""
    return hashlib.sha256((secret or "").encode()).hexdigest()


def withdrawal_statement(app_id: str, nonce: str, expires: str) -> dict[str, Any]:
    """The exact document a withdrawal signature covers.

    Four fields and no more. The **application** so a signature for one cannot withdraw another, the
    **action** so a signature made for anything else cannot withdraw at all, a **nonce** so two
    withdrawals of the same application are two different documents, and an **expiry** so a captured
    signature stops working. Published through `policy` and `withdrawal_to_sign`, so an applicant's
    client signs the bytes this hub will check rather than guessing at them.
    """
    return {"application": app_id, "action": WITHDRAW_ACTION, "nonce": nonce, "expires": expires}


def withdrawal_to_sign(app_id: str, nonce: str = "", expires: str = "") -> dict[str, Any]:
    """A ready-to-sign withdrawal document, its canonical bytes, and when it runs out.

    Offered so a client never has to construct the canonical form itself; passing the same `nonce`
    and `expires` back with the signature is what makes the hub check the document it handed out.
    """
    nonce = (nonce or secrets.token_urlsafe(16)).strip()
    expires = (expires or (_now() + timedelta(seconds=WITHDRAW_WINDOW_S)).isoformat()).strip()
    statement = withdrawal_statement(app_id, nonce, expires)
    return {
        "statement": statement,
        "canonical": base64.b64encode(hive.canonical(statement)).decode(),
        "nonce": nonce,
        "expires": expires,
        "signature_field": "signature",
    }


def _expired(expires: str) -> bool:
    """True when this withdrawal document's window has closed, or its expiry is unreadable.

    Unreadable counts as expired. A signature over an expiry nothing can parse has no window at all,
    and the safe reading of "no window" on a destructive act is "closed".
    """
    try:
        when = datetime.fromisoformat((expires or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is not None:
        when = when.astimezone(UTC).replace(tzinfo=None)
    return when <= _now()


def _applicant_proof(row: dict[str, Any], key: str, signature: str, nonce: str, expires: str) -> str:
    """Which applicant proof this request carried, or "" — with the refusal raised where it is wrong.

    A *missing* proof returns "", because the caller may still be the operator. A proof that is
    present and wrong raises: a wrong credential is never treated as no credential, or an attacker
    would get the operator's error message and learn which door to try next.
    """
    registered = str(row.get("public_key") or "")
    if signature or nonce or expires:
        if not registered:
            raise RegistrationError(
                f"application {row['id']} brought no public key, so this hub holds its key and there is no"
                f" applicant signature to check. Withdraw it with the capability `apply` returned, in the"
                f" {KEY_HEADER} header"
            )
        if not (signature and nonce and expires):
            raise RegistrationError(
                "a signed withdrawal needs `signature`, `nonce` and `expires` together: the nonce and the"
                " expiry are part of the document that was signed. GET /api/hub/register/{id}/withdrawal"
                " returns a document to sign"
            )
        if _expired(expires):
            raise RegistrationError(
                "this withdrawal document has expired; ask for another and sign that."
                f" A signed withdrawal is good for {WITHDRAW_WINDOW_S} s"
            )
        if not hive.verify(withdrawal_statement(row["id"], nonce, expires), signature, registered):
            raise RegistrationError(
                "the signature does not match the key this application registered, or it covers a different"
                " document. It is made over the canonical JSON of"
                " {application, action: 'withdraw', nonce, expires}"
            )
        return BY_SIGNATURE
    if key:
        stored = _withdraw_fingerprint(row["id"])
        if not stored:
            raise RegistrationError(
                f"application {row['id']} carries no withdrawal capability — it predates them, or it brought"
                " a public key and is withdrawn by signing instead"
            )
        if not guard.secret_matches(fingerprint(key), stored):
            raise RegistrationError(f"that is not application {row['id']}'s withdrawal key")
        return BY_CAPABILITY
    return ""


def _withdraw_fingerprint(app_id: str) -> str:
    """The stored hash of one application's capability. Read here and nowhere else, never returned."""
    with db.cursor() as cur:
        found = cur.execute("SELECT withdraw_sha256 FROM hub_applications WHERE id = ?", [app_id]).fetchone()
    return str(found[0]) if found and found[0] else ""


# ---------------------------------------------------------------- applying


def apply(application: dict[str, Any], *, decided_by: str = "policy") -> dict[str, Any]:
    """Run an application through the checks and the hub's admission policy.

    Always returns an answer with the reason and what to do next; never raises for a refusal, since
    a refusal is an outcome rather than an error.
    """
    if config.ADMISSION_POLICY not in POLICIES:
        raise RegistrationError(f"this hub's ADMISSION_POLICY is not one of {', '.join(POLICIES)}")

    app_id = f"ap-{uuid.uuid4().hex[:12]}"
    checks: list[dict[str, Any]] = []
    failed: str | None = None
    for name, fn in CHECKS:
        try:
            ok, detail = fn(application, {})
        except Exception as exc:  # a malformed document must not take the hub down
            ok, detail = False, f"could not be checked: {exc}"
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            failed = detail
            break

    entity = application.get("entity") if isinstance(application.get("entity"), dict) else {}
    entity_id = str(entity.get("id") or "").strip().lower()
    public_key = str(application.get("public_key") or "").strip()
    custody = "owner" if public_key else "hub"
    verification = verification_for(application, checks) if failed is None else "none"

    if failed is not None:
        state, reason = REJECTED, failed
    elif config.ADMISSION_POLICY == CLOSED:
        state, reason = REJECTED, "this hub is not accepting registrations"
    elif config.ADMISSION_POLICY == VETTED:
        state, reason = PENDING, "every application here is read by a person before it is admitted"
    else:
        state, reason = ADMITTED, "admitted automatically: this hub admits anything that passes its checks"

    # Minted before the row is stored, and only for an application that will actually sit in a queue:
    # an admitted or rejected one has nothing left to withdraw, so handing out a capability for it
    # would be a secret with no purpose. An application that brought its own key needs none either —
    # it withdraws by signing, which is stronger and which the hub cannot forge on its applicant's
    # behalf. The plaintext is returned **once**, here, and is in nothing this module stores or logs.
    secret = secrets.token_urlsafe(WITHDRAW_SECRET_BYTES) if state == PENDING and not public_key else ""
    _store(
        app_id,
        application,
        entity_id,
        state,
        custody,
        verification,
        checks,
        reason,
        decided_by,
        fingerprint(secret) if secret else "",
    )
    if state == ADMITTED:
        _publish(app_id, application, custody)
    out = get(app_id)
    if secret:
        out["withdraw_key"] = secret
        out["withdraw_with"] = (
            f"Keep this. It is shown once and this hub stores only its hash. To withdraw before a decision,"
            f" send it in the {KEY_HEADER} header of POST /api/hub/register/{app_id}/withdraw."
        )
    elif state == PENDING:
        out["withdraw_with"] = (
            f"You brought a public key, so you withdraw by signing rather than with a secret this hub gave you."
            f" GET /api/hub/register/{app_id}/withdrawal returns the document to sign."
        )
    return out


def _store(
    app_id, application, entity_id, state, custody, verification, checks, reason, decided_by, withdraw_sha256=""
) -> None:
    """Write the application row. `withdraw_sha256` is the only trace a capability ever leaves."""
    entity = application.get("entity") if isinstance(application.get("entity"), dict) else {}
    now = _now()
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hub_applications (id, created_at, state, entity_id, kind, name, public_key, custody,"
            " verification, proofs, payload, checks, decided_at, decided_by, reason, withdraw_sha256)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                app_id,
                now,
                state,
                entity_id,
                str(entity.get("kind") or ""),
                str(entity.get("name") or ""),
                str(application.get("public_key") or ""),
                custody,
                verification,
                json.dumps(application.get("proofs") or []),
                # An oversized application is recorded as its size, never its text: a refusal that
                # has to be kept must not itself be the way the database gets filled.
                json.dumps(limits.storable(entity)),
                json.dumps(checks),
                now if state != PENDING else None,
                decided_by if state != PENDING else None,
                reason,
                withdraw_sha256,
            ],
        )


def _publish(app_id: str, application: dict[str, Any], custody: str) -> None:
    """Put an admitted entity into the index, recording who holds its key."""
    entity = dict(application["entity"])
    entity["id"] = str(entity["id"]).strip().lower()
    entity.setdefault("slug", entity["id"])
    entity["custody"] = custody
    entity["registered_via"] = app_id
    if custody == "owner":
        # The hub pins the owner's key and never sees the private half. hive.publish still
        # counter-signs with the hub's own key, so a reader can tell who vouched for what.
        entity["owner_public_key"] = str(application.get("public_key") or "")
    hive.publish(entity)


# ---------------------------------------------------------------- the operator's side


def decide(app_id: str, admit: bool, *, reason: str = "", decided_by: str = "admin") -> dict[str, Any]:
    """A person admits or refuses a pending application. A refusal needs a reason."""
    row = get(app_id)
    if row["state"] != PENDING:
        raise RegistrationError(f"only a pending application can be decided, this one is {row['state']}")
    reason = (reason or "").strip()
    if not admit and not reason:
        raise RegistrationError("a refusal needs a reason: the applicant is told it")
    with db.write() as cur:
        cur.execute(
            "UPDATE hub_applications SET state = ?, decided_at = ?, decided_by = ?, reason = ? WHERE id = ?",
            [ADMITTED if admit else REJECTED, _now(), decided_by, reason or "admitted", app_id],
        )
    if admit:
        stored = get(app_id)
        _publish(app_id, {"entity": stored["entity"], "public_key": stored["public_key"]}, stored["custody"])
    return get(app_id)


def withdraw(
    app_id: str,
    *,
    key: str = "",
    signature: str = "",
    nonce: str = "",
    expires: str = "",
    by_operator: str = "",
) -> dict[str, Any]:
    """Withdraw a pending application, for whoever can prove they may. Refused for anyone who cannot.

    One of three proofs, described at the top of this section: a signed action under the key the
    application registered, the capability `apply` returned once for an application whose key the hub
    holds, or the operator through an explicitly separate administrative route. `by_operator` is the
    *kind* of admin credential the route already accepted, never the credential; it is trusted here
    because only a route behind `admin_only` can pass it.

    Fails closed. No proof means the application is not touched, and the refusal says which proof
    this application takes rather than listing all three at somebody who cannot use two of them.

    The transition is conditional on the row still being `pending`, inside the same transaction that
    reads it, so admission and withdrawal have exactly one winner however they race. That is also
    what makes a replayed proof inert: the second attempt finds a row that is no longer pending.

    Attribution is the actual actor. `decided_by` is only an `applicant` form when an applicant proof
    was shown — an operator withdrawal says so, and the reason says so, because a row claiming the
    applicant changed their mind when nobody asked them is the part of #108 that outlasts the bug.
    """
    row = get(app_id)
    if row["state"] != PENDING:
        raise RegistrationError(f"only a pending application can be withdrawn, this one is {row['state']}")

    proof = _applicant_proof(row, key, signature, nonce, expires)
    if not proof and by_operator:
        proof = BY_OPERATOR
    if not proof:
        raise RegistrationError(_no_proof(row))

    reason = (
        f"withdrawn by the hub operator ({by_operator}), not by the applicant"
        if proof == BY_OPERATOR
        else f"withdrawn by the applicant, proved by {'a signed action' if proof == BY_SIGNATURE else 'capability'}"
    )
    with db.write() as cur:
        # The read and the write are one statement on one row: `WHERE state = PENDING` is the whole
        # race guard, and it is inside the transaction that the earlier `get` is not.
        cur.execute(
            "UPDATE hub_applications SET state = ?, decided_at = ?, decided_by = ?, reason = ?"
            " WHERE id = ? AND state = ?",
            [WITHDRAWN, _now(), proof, reason, app_id, PENDING],
        )
    after = get(app_id)
    if after["state"] != WITHDRAWN:
        raise RegistrationError(
            f"application {app_id} was decided while this withdrawal was being checked; it is now {after['state']}"
        )
    return after


def _no_proof(row: dict[str, Any]) -> str:
    """Why this withdrawal is refused, naming only the proof this particular application can give."""
    if str(row.get("public_key") or ""):
        return (
            f"withdrawing application {row['id']} needs a signed action under the key it registered. Knowing an"
            " application id is not authority to change it: the id is how anybody looks the application up."
            f" GET /api/hub/register/{row['id']}/withdrawal returns the document to sign. An operator can also"
            " withdraw it, as their own act, through POST /api/admin/applications/{id}/withdraw"
        )
    return (
        f"withdrawing application {row['id']} needs the capability this hub returned once when it was submitted,"
        f" in the {KEY_HEADER} header. Knowing an application id is not authority to change it: the id is how"
        " anybody looks the application up. Lost it? An operator can withdraw the application as their own act,"
        " through POST /api/admin/applications/{id}/withdraw"
    )


SELECT = (
    "SELECT id, created_at, state, entity_id, kind, name, public_key, custody, verification, proofs,"
    " payload, checks, decided_at, decided_by, reason FROM hub_applications"
)


def _row(r: tuple) -> dict[str, Any]:
    keys = (
        "id",
        "created_at",
        "state",
        "entity_id",
        "kind",
        "name",
        "public_key",
        "custody",
        "verification",
        "proofs",
        "payload",
        "checks",
        "decided_at",
        "decided_by",
        "reason",
    )
    out: dict[str, Any] = {}
    for key, value in zip(keys, r, strict=True):
        out[key] = value.isoformat() if isinstance(value, datetime) else value
    out["proofs"] = json.loads(out["proofs"] or "[]")
    out["checks"] = json.loads(out["checks"] or "[]")
    out["entity"] = json.loads(out.pop("payload") or "{}")
    out["next"] = _next_step(out)
    return out


def _next_step(row: dict[str, Any]) -> str:
    """What the applicant should do now. An answer with no next step is a dead end."""
    if row["state"] == PENDING:
        signing = " You brought a key, so a withdrawal is signed with it." if row.get("public_key") else ""
        return (
            "Nothing: a person on this hub reads every application. Check back with this id."
            " To withdraw before they decide, prove it is yours." + signing
        )
    if row["state"] == ADMITTED:
        return "You are in the index and findable. Publish updates by signing a new version of your card."
    if row["state"] == REJECTED:
        return "Fix what the reason names and apply again, or try a hub whose admission policy suits you."
    return "This application was withdrawn. Apply again whenever you like."


def get(app_id: str) -> dict[str, Any]:
    """One application by id."""
    with db.cursor() as cur:
        row = cur.execute(f"{SELECT} WHERE id = ?", [app_id]).fetchone()
    if row is None:
        raise RegistrationError(f"no application {app_id!r}")
    return _row(row)


def listing(state: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Applications, newest first. The admin queue when state is `pending`."""
    sql, args = SELECT, []
    if state:
        sql += " WHERE state = ?"
        args.append(state)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    with db.cursor() as cur:
        return [_row(r) for r in cur.execute(sql, args).fetchall()]


def policy() -> dict[str, Any]:
    """What this hub asks of someone who wants to join. Published so an applicant can read it first."""
    return {
        "policy": config.ADMISSION_POLICY,
        "means": {
            OPEN: "anything that passes the checks is admitted at once",
            VETTED: "a person reads every application before it is admitted",
            INVITE: "an invite token is required, then the checks apply as usual",
            CLOSED: "this hub is not accepting registrations",
        }[config.ADMISSION_POLICY],
        "checks": [name for name, _ in CHECKS],
        # Published so an applicant reads what will be accepted before writing it, rather than
        # finding out from a refusal. The prose version is documentation/cards/README.md.
        "limits": [limit._asdict() for limit in limits.LIMITS],
        "verification_offered": config.HIVE_VERIFICATION,
        "verification_ladder": list(LADDER),
        "proof_types": list(PROOF_TYPES),
        "key_custody": "Bring a public key and you keep the private half. Omit it and this hub holds one for you.",
        # Published with everything else this hub asks of an applicant, so withdrawing is a rule read
        # in advance rather than a refusal discovered later.
        "withdrawal": {
            "means": (
                "An application id is a lookup, not authority to change it. Withdrawing a pending application"
                " needs proof it is yours."
            ),
            "with_an_owner_key": (
                "Sign the canonical JSON of {application, action: 'withdraw', nonce, expires} with the private"
                " half of the key you registered, and send signature, nonce and expires."
                " GET /api/hub/register/{id}/withdrawal returns the document and its canonical bytes."
            ),
            "with_hub_custody": (
                f"Send the capability this hub returned once when you applied, in the {KEY_HEADER} header."
                " It is a header and not a field so it stays out of URLs, logs and agent transcripts;"
                " this hub stores only its SHA-256 and can never show it to you again."
            ),
            "window_seconds": WITHDRAW_WINDOW_S,
            "operator": (
                "An operator can also withdraw an application, through POST /api/admin/applications/{id}/withdraw."
                " That is recorded as the operator's own act and never as the applicant's consent."
            ),
        },
        "example": {
            "entity": {
                "id": "your-id",
                "kind": "stay",
                "name": "Your name",
                "description": "One line.",
                "sharing": "public",
            },
            "public_key": "<base64 Ed25519>",
            "proofs": [{"type": "dns-txt", "subject": "your-domain.example"}],
            "signature": "<base64 over the canonical JSON of this document without `signature`>",
        },
    }


def canonical_to_sign(application: dict[str, Any]) -> str:
    """The exact bytes an applicant signs, base64'd, so a client can be checked against the hub."""
    return base64.b64encode(hive.canonical(unsigned(application))).decode()
