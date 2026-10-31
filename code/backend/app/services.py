"""Optional outside services, and the keys they need, set by an operator rather than by a redeploy.

Everything in Adobee Hive works with **no** key at all: the offline planner answers, owner edits are
rule-based, semantic search uses its offline provider. That is a promise, not a fallback, and nothing
here weakens it — a service with no key is simply off, and the hub says so.

What was missing is the other half: an operator who *does* have a key could only use it by editing a
deployment's environment and restarting. So the keys live here, in `hub_service_keys`, persisted the
way the blocklist is, and the next call picks one up without a restart.

## Write-only, on purpose

A key goes in and never comes out. No endpoint returns one, nothing here logs one, and the only
things an interface ever sees are **presence**, a **fingerprint** (the first 12 hex of its SHA-256)
and its **last four characters** — enough for an operator to tell which key is loaded, useless to
anyone who reads the screen over their shoulder. `check()` error messages are scrubbed of the secret
before they are stored, because a vendor that echoes a bad key back in an error would otherwise put
it in the ledger.

## What this does not claim

The key is stored in this hub's DuckDB file **in the clear**. There is no envelope encryption and no
secret manager: a hub with encryption at rest has it, and a hub without it does not. The UI says
exactly that. Claiming otherwise would be the one unforgivable thing in a module like this.

## The environment is still the seed

`key_for()` prefers the stored key and falls back to the matching environment variable, so a hub
deployed with `OPENAI_API_KEY` set behaves exactly as it did before anyone opened the admin panel.
Clearing a stored key therefore returns the hub to its environment, which is the honest meaning of
"clear" — the panel says which of the two is in use.

Adding a service is one `Service` row plus, if it can be tested, one probe. The shape is deliberately
general: an embedding provider slots in beside the model vendors without touching anything else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from . import audit, config, db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hub_service_keys (
    service VARCHAR PRIMARY KEY,
    secret VARCHAR NOT NULL,
    fingerprint VARCHAR NOT NULL,
    last_four VARCHAR NOT NULL,
    stored_at TIMESTAMP NOT NULL,
    stored_by VARCHAR,
    checked_at TIMESTAMP,
    working BOOLEAN,
    last_error VARCHAR
);
"""

MAX_SECRET = 500
MAX_ERROR = 300

#: What the hub never says out loud about a stored key, however it is asked.
NEVER_RETURNED = ("secret",)

#: Said on screen next to every key field. A protection we did not build is not claimed.
STORAGE_WARNING = (
    "A key is stored on this hub, in its database, in the clear unless this host encrypts its disk. "
    "It is never shown again and never logged; only its fingerprint and last four characters are."
)


@dataclass(frozen=True)
class Service:
    """One optional integration: what it is for, and which environment variable seeds its key."""

    name: str
    label: str
    purpose: str
    env: str
    #: What stops working without it. Empty means nothing does — it only adds something.
    without: str = ""


SERVICES: tuple[Service, ...] = (
    Service(
        name="openai",
        label="OpenAI",
        purpose=(
            "Runs the booking agent, the owner's plain-language card edits, the relevance check, the "
            "verifier and the web scout. Also the embedding provider for semantic search."
        ),
        env="OPENAI_API_KEY",
        without="The scripted planner answers, edits are rule-based, and semantic search uses its offline provider.",
    ),
    Service(
        name="anthropic",
        label="Claude",
        purpose="The same work as OpenAI, from the other vendor. Used when OpenAI has no key.",
        env="ANTHROPIC_API_KEY",
        without="The scripted planner answers and edits are rule-based.",
    ),
)

BY_NAME = {s.name: s for s in SERVICES}

#: Where the key in use came from, which is the one thing an operator cannot guess.
STORED = "stored"
ENVIRONMENT = "environment"
NONE = "none"


class ServiceError(ValueError):
    """A key change this hub refuses: an unknown service, or an empty key."""


def init() -> None:
    """Create the table."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


def _service(name: str) -> Service:
    service = BY_NAME.get((name or "").strip())
    if service is None:
        raise ServiceError(f"unknown service: {name!r}; expected {' or '.join(BY_NAME)}")
    return service


def fingerprint(secret: str) -> str:
    """A short, one-way fingerprint of a key: enough to tell two keys apart, never to rebuild one."""
    return hashlib.sha256(secret.encode()).hexdigest()[:12]


def _scrub(message: str, secret: str) -> str:
    """Take the key out of a vendor's error message before it is stored. Vendors do echo keys back."""
    text = message.replace(secret, "[key]") if secret else message
    return text[:MAX_ERROR]


def _row(name: str) -> dict[str, Any] | None:
    """The stored row for one service, the secret included. Private: callers get `listing()`."""
    with db.cursor() as cur:
        found = db.rows(cur.execute("SELECT * FROM hub_service_keys WHERE service = ?", [name]))
    return found[0] if found else None


def key_for(name: str) -> str:
    """The key in use for one service: the stored one, or the environment's as the seed. "" when off.

    The one function the rest of the backend calls. Never logged by anything here, and the callers
    pass it straight to a vendor client. A table that does not exist yet (a unit test that never
    opened the app) falls back to the environment rather than raising: a missing store must never be
    the thing that breaks a model call.
    """
    try:
        service = _service(name)
    except ServiceError:
        return ""
    try:
        row = _row(service.name)
    except Exception:
        row = None
    if row and row["secret"]:
        return str(row["secret"])
    return str(getattr(config, service.env, "") or "")


def source(name: str) -> str:
    """Whether the key in use is stored here, inherited from the environment, or absent."""
    service = _service(name)
    row = _row(service.name)
    if row and row["secret"]:
        return STORED
    return ENVIRONMENT if getattr(config, service.env, "") else NONE


def set_key(name: str, secret: str, stored_by: str = "admin") -> dict[str, Any]:
    """Store a key for one service. Returns presence and a fingerprint, never the key.

    Replacing a key clears what was known about whether the old one worked: the answer belonged to
    the old key, and showing it next to the new one would be a lie by juxtaposition.
    """
    service = _service(name)
    secret = (secret or "").strip()
    if not secret:
        raise ServiceError("a key cannot be empty; clear the service instead")
    if len(secret) > MAX_SECRET:
        raise ServiceError(f"a key is at most {MAX_SECRET} characters")
    now = datetime.now(UTC).replace(tzinfo=None)
    with db.write() as cur:
        cur.execute("DELETE FROM hub_service_keys WHERE service = ?", [service.name])
        cur.execute(
            "INSERT INTO hub_service_keys (service, secret, fingerprint, last_four, stored_at, stored_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [service.name, secret, fingerprint(secret), secret[-4:], now, stored_by],
        )
    # The ledger records that a key was set and by which credential. Never the key, and never its
    # fingerprint either: a ledger is read by more people than a settings page.
    audit.record("service.set", service.name, "a key was stored for this service", credential=stored_by)
    return status(service.name)


def clear_key(name: str, cleared_by: str = "admin") -> dict[str, Any]:
    """Forget the stored key. The hub falls back to the environment, or to working without one."""
    service = _service(name)
    with db.write() as cur:
        cur.execute("DELETE FROM hub_service_keys WHERE service = ?", [service.name])
    audit.record("service.clear", service.name, "the stored key was cleared", credential=cleared_by)
    return status(service.name)


def status(name: str) -> dict[str, Any]:
    """One service as an interface may see it: what it is for, whether a key is set, and how it went.

    Everything except the key itself. `fingerprint` and `last_four` are the whole of what is
    revealed, and they are only ever about a key an operator stored here themselves.
    """
    service = _service(name)
    row = _row(service.name)
    stored = bool(row and row["secret"])
    where = source(service.name)
    return {
        "name": service.name,
        "label": service.label,
        "purpose": service.purpose,
        "without": service.without,
        "env": service.env,
        # Is anything configured at all, from either place? This is what "optional" turns on.
        "configured": where != NONE,
        "source": where,
        "stored": stored,
        "fingerprint": str(row["fingerprint"]) if stored else "",
        "last_four": str(row["last_four"]) if stored else "",
        "stored_at": row["stored_at"].isoformat() if stored and row["stored_at"] else None,
        # Whether the last test call worked. None means nobody has tested this key yet, which is
        # not the same as a failure and is not drawn as one.
        "working": None if not row or row["working"] is None else bool(row["working"]),
        "checked_at": row["checked_at"].isoformat() if row and row["checked_at"] else None,
        "last_error": str(row["last_error"] or "") if row else "",
        "testable": service.name in PROBES,
        "storage_warning": STORAGE_WARNING,
    }


def listing() -> dict[str, Any]:
    """Every optional service, whether it is on, and what the hub does without it."""
    return {
        "services": [status(s.name) for s in SERVICES],
        "provider": provider(),
        "enabled": enabled(),
        "storage_warning": STORAGE_WARNING,
    }


def _probe_openai(secret: str) -> str:
    """One cheap authenticated call to OpenAI: list the models. No tokens, no completion, no data."""
    import openai

    openai.OpenAI(api_key=secret, timeout=10.0, max_retries=0).models.list()
    return "the key was accepted"


def _probe_anthropic(secret: str) -> str:
    """The same for Claude: listing models proves the key without spending a token."""
    import anthropic

    anthropic.Anthropic(api_key=secret, timeout=10.0, max_retries=0).models.list()
    return "the key was accepted"


#: A cheap authenticated call per service. A service with no probe simply cannot be tested from here.
PROBES: dict[str, Callable[[str], str]] = {"openai": _probe_openai, "anthropic": _probe_anthropic}


def check(name: str, probe: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Make one cheap call with the key in use and record whether it worked.

    So an operator finds out before a demo rather than during it. The result is stored against the
    key, and the error message is scrubbed of the key first. Nothing is raised for a key that does
    not work: that is an answer, not a failure of this endpoint.
    """
    service = _service(name)
    secret = key_for(service.name)
    run = probe or PROBES.get(service.name)
    if not secret:
        raise ServiceError(f"{service.label} has no key to test")
    if run is None:
        raise ServiceError(f"{service.label} cannot be tested from here")
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        run(secret)
        working, detail = True, ""
    except Exception as err:
        working, detail = False, _scrub(f"{type(err).__name__}: {err}", secret)
    if _row(service.name):
        with db.write() as cur:
            cur.execute(
                "UPDATE hub_service_keys SET working = ?, checked_at = ?, last_error = ? WHERE service = ?",
                [working, now, detail, service.name],
            )
    out = status(service.name)
    # An environment key has no row to write to, so the answer is reported rather than remembered.
    return {**out, "working": working, "checked_at": now.isoformat(), "last_error": detail}


def stored(name: str) -> bool:
    """Whether a key for this service was stored *here*, as opposed to inherited from the environment."""
    try:
        row = _row(_service(name).name)
    except Exception:
        return False
    return bool(row and row["secret"])


def any_stored() -> bool:
    """Whether an operator has stored a key for any service since this hub booted."""
    return any(stored(s.name) for s in SERVICES)


def enabled() -> bool:
    """Whether any model vendor is reachable right now. Running with none is supported, not a fault.

    `LLM_ENABLED` is still the switch for what the *environment* provides, so a deployment (or a
    test, or the offline demo) that turns the models off stays off whatever keys happen to be in
    its environment. What this adds is the other direction: a key an operator stored in the admin
    panel since boot turns the vendor on without a restart, because the environment never knew
    about it and `LLM_ENABLED` was decided before it existed.
    """
    return bool(config.LLM_ENABLED) or any_stored()


def provider() -> str:
    """Which model vendor the agents use right now, a key stored since boot included.

    `LLM_PROVIDER` decides when the environment named one, so a deployment that pinned a vendor
    keeps it. Otherwise it is whichever key an operator stored, OpenAI first, exactly the order
    `config` uses at boot — the difference being that this is asked per call rather than at import.

    This answers *which* vendor, never *whether* a model may be called: that is `enabled()`, and the
    two are deliberately separate. A caller picking a client wants the vendor; a caller deciding
    whether to reach for a model at all wants the switch, which is what keeps the offline demo
    offline on a machine that happens to have a key in its environment.
    """
    if config.LLM_PROVIDER != "offline":
        return config.LLM_PROVIDER
    if stored("openai"):
        return "openai"
    if stored("anthropic"):
        return "claude"
    return "offline"
