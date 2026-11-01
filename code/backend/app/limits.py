"""How much room an entry has on this hub, and what gets tidied rather than refused.

Every field a Card carries has a ceiling, and the ceilings are published (see
`documentation/cards/README.md`) so an applicant can read what will be accepted before writing it.

## Why there are limits at all, and what they are *not*

A hub that accepts unbounded text is a hub whose index can be flooded, whose database can be
filled, and whose signed documents stop fitting in a request. That is an engineering problem and it
is the only problem this module solves. **Nothing here reads the content of a field.** There is no
density check, no keyword detection, no judgement about how a description is written — a Card's
`description` *is* the entity's pitch to an agent, and writing it well for discovery is the product
working as designed, not an attack on it. It gets 2000 characters because that is room to describe
yourself properly.

The honest defence against an entity describing itself as something it is not was never prose
analysis. It is the economic loop: over-promise, get matched to the wrong people, get scored badly
after the real meeting, and the carrying hub's calibration error rises (`calibration.py`), which
costs every entity on that hub ranking weight everywhere. Nobody has to read the prose for that to
work.

## Normalising, not refusing

Three things are tidied in passing rather than turned away, because they are invisible to a reader
and would otherwise change a card's digest for no reason anybody could see:

- Unicode is normalised to NFC, so two spellings of the same character are one string.
- Control characters and zero-width characters (ZWSP, word joiner, soft hyphen, the bidi overrides)
  are dropped. A zero-width character is invisible, counts against nothing, and changes a signature.
- Runs of whitespace collapse to a single space and the ends are trimmed. A Card's text fields are
  one line of prose each.

## Both doors

`registration.apply()` checks an application before anything expensive happens to it, and
`hive.publish()` checks every version after. Enforcing only at signup would let an entity register
politely and then grow unbounded on its next update.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, NamedTuple


class LimitError(ValueError):
    """A Card or an application that carries more than this hub accepts."""


class Limit(NamedTuple):
    """One published ceiling: what it applies to, what it is counted in, and what the field is for."""

    field: str
    unit: str
    cap: int
    about: str


# ---------------------------------------------------------------- the ceilings
#
# Every number is set from the real corpus in `testdata/vaults/` with room to spare: a limit that
# refuses a legitimate hotel is worse than one slightly too generous. The widest entry in the
# corpus is noted beside each.
#
# `structure` and the whole-card ceiling carry the most headroom on purpose. Today a vault is a
# folder of markdown and `structure` lists four rows; it is about to list every file an owner has,
# photos and price lists included, so a real card will get an order of magnitude longer without
# anybody doing anything wrong.

MAX_ID = 63  # the id regex already allows 63; corpus widest 24
MAX_KIND = 32  # corpus widest 10
MAX_NAME = 120  # corpus widest 25
MAX_TAGLINE = 200  # corpus widest 90; the vault builder clamps its own at 90
MAX_DESCRIPTION = 2000  # corpus widest 358. The entity's pitch to an agent: room to write it
MAX_TEXT = 500  # any other string a card carries; corpus widest 112 (`provenance.note`)

MAX_ENTRY_TITLE = 200  # corpus widest 96; the vault builder clamps its own at 120
MAX_ENTRY_SUMMARY = 600  # corpus widest 166; the vault builder clamps its own at 300
MAX_TAG = 40  # corpus widest 9
MAX_FEATURE = 60  # corpus widest 20
MAX_PATH = 400  # a folder path in `structure`; corpus widest 10
MAX_DIGEST = 120  # "sha256:" plus a hash; corpus widest 19
MAX_CONTACT_VALUE = 200  # corpus widest 39 (an email); a postal address is the long one
MAX_KEY = 40  # an object key, e.g. a contact channel name; corpus widest 7
MAX_PROOF_TEXT = 200  # a proof's subject, e.g. a domain name. Recorded unverified, so only bounded

MAX_OFFERS = 50  # corpus widest 6
MAX_NEEDS = 50  # corpus widest 3
MAX_FEATURES = 50  # corpus widest 9
MAX_UNITS = 100  # corpus widest 3
MAX_STRUCTURE = 1_000  # one row per file in the owner's folder; corpus widest 4 (markdown only, for now)
MAX_LINKS = 50
MAX_ATTESTATIONS = 50
MAX_TAGS = 20  # corpus widest 4
MAX_CONTACT_CHANNELS = 20  # corpus widest 4; the map stays open, so this is the only bound
MAX_PROOFS = 8  # claims about the world, recorded unverified; `registration.CHECKS` reads this too
MAX_LIST = 200  # any other list a card carries

MAX_KEYS = 64  # keys in any one object; corpus widest 15 (the card itself)
MAX_DEPTH = 12  # how deeply a card may nest; corpus widest 4
MAX_CARD_BYTES = 256_000  # the canonical JSON of a whole card; corpus widest 3_532
MAX_APPLICATION_BYTES = 320_000  # a card plus its key, proofs and signature
MAX_BODY_BYTES = 1_048_576  # any request body, refused by size before it is parsed

#: Character ceilings for the named text fields of a card.
CARD_TEXT = {
    "id": MAX_ID,
    "slug": MAX_ID,
    "kind": MAX_KIND,
    "name": MAX_NAME,
    "tagline": MAX_TAGLINE,
    "description": MAX_DESCRIPTION,
}

#: Entry ceilings for the named list fields of a card.
CARD_LISTS = {
    "offers": MAX_OFFERS,
    "needs": MAX_NEEDS,
    "features": MAX_FEATURES,
    "units": MAX_UNITS,
    "structure": MAX_STRUCTURE,
    "links": MAX_LINKS,
    "attestations": MAX_ATTESTATIONS,
}

#: Character ceilings inside one offer or one need.
ENTRY_TEXT = {"title": MAX_ENTRY_TITLE, "summary": MAX_ENTRY_SUMMARY}

#: Character ceilings inside one `structure` row.
STRUCTURE_TEXT = {"path": MAX_PATH, "digest": MAX_DIGEST}

#: The published table, in the order `documentation/cards/README.md` prints it. `tests/test_limits.py`
#: fails when a row here is missing from that page, so the two cannot drift apart.
LIMITS: tuple[Limit, ...] = (
    Limit("id", "characters", MAX_ID, "`hive:<hub>/<entity>` without the hub part. Lower case, digits, hyphens"),
    Limit("kind", "characters", MAX_KIND, "What sort of entity this is, so a search can narrow by it"),
    Limit("name", "characters", MAX_NAME, "What a person sees in a result"),
    Limit("tagline", "characters", MAX_TAGLINE, "One phrase under the name"),
    Limit("description", "characters", MAX_DESCRIPTION, "Your pitch to an agent. Write it for discovery"),
    Limit("offers", "entries", MAX_OFFERS, "What you provide. Half the index"),
    Limit("needs", "entries", MAX_NEEDS, "What you are looking for. The other half"),
    Limit("offers[].title", "characters", MAX_ENTRY_TITLE, "The name of one thing you offer or need"),
    Limit("offers[].summary", "characters", MAX_ENTRY_SUMMARY, "The line it came from, in your own words"),
    Limit("offers[].tags", "entries", MAX_TAGS, "Words a search should match that the prose does not carry"),
    Limit("features", "entries", MAX_FEATURES, "Short facts a search can filter on"),
    Limit("units", "entries", MAX_UNITS, "Bookable rooms or slots"),
    Limit("structure", "entries", MAX_STRUCTURE, "One row per file in your folder: path and digest, never contents"),
    Limit("contact", "channels", MAX_CONTACT_CHANNELS, "The open map of how to reach you"),
    Limit("contact.<channel>", "characters", MAX_CONTACT_VALUE, "One channel's value, e.g. a postal address"),
    Limit("proofs", "entries", MAX_PROOFS, "Claims about the world. Recorded unverified, never trusted"),
    Limit("proofs[].subject", "characters", MAX_PROOF_TEXT, "What one proof is about, e.g. a domain name"),
    Limit("any other text", "characters", MAX_TEXT, "Any string the card carries that is not named above"),
    Limit("any other list", "entries", MAX_LIST, "Any list the card carries that is not named above"),
    Limit("keys per object", "keys", MAX_KEYS, "How many keys one object may carry"),
    Limit("nesting", "levels", MAX_DEPTH, "How deeply a card may nest"),
    Limit("the whole card", "bytes", MAX_CARD_BYTES, "The canonical JSON of everything above"),
    Limit("the application", "bytes", MAX_APPLICATION_BYTES, "The card plus its key, proofs and signature"),
    Limit("the request body", "bytes", MAX_BODY_BYTES, "Refused by size before it is parsed into objects"),
)


# ---------------------------------------------------------------- normalising


#: Whitespace, control characters and the invisibles, in one pass.
_INVISIBLE = ("Cc", "Cf")


def clean(value: str) -> str:
    """Tidy one string: NFC, invisibles out, whitespace runs to one space, ends trimmed.

    Idempotent, so a card that has already been through here is unchanged by a second pass.
    """
    text = unicodedata.normalize("NFC", value)
    kept = [ch for ch in text if ch.isspace() or unicodedata.category(ch) not in _INVISIBLE]
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def normalise(value: Any) -> Any:
    """Tidy every string in a card, keys included. A key that cleans away to nothing is dropped.

    Call `document_refusal` first: this walks the document, and a document deep enough to matter
    should be refused before anything recurses over it.
    """
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            name = clean(key) if isinstance(key, str) else key
            if name == "":
                continue
            out[name] = normalise(item)
        return out
    if isinstance(value, list):
        return [normalise(item) for item in value]
    return clean(value) if isinstance(value, str) else value


# ---------------------------------------------------------------- the checks


def depth(value: Any) -> int:
    """How deeply a document nests, counted without recursion so a deep one cannot blow the stack.

    A 2000-level body used to parse fine and then take the process down on the way out; nothing
    that walks a document may itself be recursive.
    """
    deepest, stack = 0, [(value, 1)]
    while stack:
        node, level = stack.pop()
        deepest = max(deepest, level)
        children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
        for child in children:
            if isinstance(child, dict | list):
                stack.append((child, level + 1))
    return deepest


def document_refusal(document: dict[str, Any], *, cap: int = MAX_CARD_BYTES, what: str = "a card") -> str:
    """Refuse a document by shape and total size, before anything walks or recurses over it.

    Depth is checked first: serialising a deeply nested document is itself recursive, so measuring
    its size before measuring its nesting is an order that crashes.
    """
    nesting = depth(document)
    if nesting > MAX_DEPTH:
        return f"{what} nests at most {MAX_DEPTH} levels deep; this one nests {nesting}"
    size = len(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode())
    if size > cap:
        return f"{what} is at most {cap} bytes of JSON; this one is {size}"
    return ""


def _name_for(path: tuple[str, ...]) -> str:
    """What to call the field at `path` in a refusal, so an applicant can find it in their document."""
    return f"`{'.'.join(path)}`" if path else "a card"


def _text_cap(path: tuple[str, ...]) -> int:
    """The character ceiling for the string at `path`."""
    if not path:
        return MAX_TEXT
    leaf, root = path[-1], path[0]
    if len(path) == 1 and leaf in CARD_TEXT:
        return CARD_TEXT[leaf]
    if root in ("offers", "needs"):
        if leaf in ENTRY_TEXT:
            return ENTRY_TEXT[leaf]
        if leaf == "tags":
            return MAX_TAG
    if root == "structure" and leaf in STRUCTURE_TEXT:
        return STRUCTURE_TEXT[leaf]
    if root == "contact":
        return MAX_CONTACT_VALUE
    if root == "features":
        return MAX_FEATURE
    if root == "proofs":
        return MAX_PROOF_TEXT
    return MAX_TEXT


def _list_cap(path: tuple[str, ...]) -> int:
    """The entry ceiling for the list at `path`."""
    if not path:
        return MAX_LIST
    if len(path) == 1 and path[-1] in CARD_LISTS:
        return CARD_LISTS[path[-1]]
    if path[0] in ("offers", "needs") and path[-1] == "tags":
        return MAX_TAGS
    if path == ("proofs",):
        return MAX_PROOFS
    return MAX_LIST


def _keys_cap(path: tuple[str, ...]) -> int:
    """How many keys the object at `path` may carry. `contact` is an open map, so it has its own."""
    return MAX_CONTACT_CHANNELS if path[-1:] == ("contact",) else MAX_KEYS


def _walk_refusal(value: Any, path: tuple[str, ...]) -> str:
    """The first field at or under `path` that is over its ceiling, as a sentence, or "" if none is."""
    if isinstance(value, dict):
        cap = _keys_cap(path)
        if len(value) > cap:
            return f"{_name_for(path)} holds at most {cap} keys; this one has {len(value)}"
        for key, item in value.items():
            if isinstance(key, str) and len(key) > MAX_KEY:
                return f"a key is at most {MAX_KEY} characters; {key[:20]!r} is {len(key)}"
            if reason := _walk_refusal(item, (*path, str(key))):
                return reason
        return ""
    if isinstance(value, list):
        cap = _list_cap(path)
        if len(value) > cap:
            return f"{_name_for(path)} holds at most {cap} entries; this one has {len(value)}"
        for item in value:
            if reason := _walk_refusal(item, path):
                return reason
        return ""
    if isinstance(value, str):
        cap = _text_cap(path)
        if len(value) > cap:
            return f"{_name_for(path)} is at most {cap} characters; this one is {len(value)}"
    return ""


def refusal(card: dict[str, Any]) -> str:
    """Why this hub will not carry this card, as a sentence an applicant can act on, or "" if it will.

    The sentence always names the ceiling and the actual size, because "too long" is not something
    anybody can fix. Run it on a normalised card: a string of zero-width characters is tidied away
    rather than counted.
    """
    return document_refusal(card) or _walk_refusal(card, ())


def vet(card: dict[str, Any]) -> dict[str, Any]:
    """Normalise a card and return it, or raise `LimitError` naming the first ceiling it passes.

    The one function both doors call. Order matters: shape and total size before anything walks the
    document, then normalising, then the field-by-field check on what normalising left.
    """
    if reason := document_refusal(card):
        raise LimitError(reason)
    clean_card = normalise(card)
    if reason := refusal(clean_card):
        raise LimitError(reason)
    return clean_card


def application_refusal(application: dict[str, Any]) -> str:
    """Why this hub will not accept this application, or "" if it will.

    Checks the whole signed document for shape and size — which is why `registration.CHECKS` runs
    it before the signature, verifying a 20 MB document being exactly the work not worth doing —
    and then the entity inside it, as it will be once normalised.
    """
    if reason := document_refusal(application, cap=MAX_APPLICATION_BYTES, what="an application"):
        return reason
    proofs = application.get("proofs")
    if isinstance(proofs, list) and (reason := _walk_refusal(normalise(proofs), ("proofs",))):
        return reason
    entity = application.get("entity")
    if not isinstance(entity, dict):
        return ""  # not this check's business: `_check_shape` says what an entity has to be
    return refusal(normalise(entity))


def storable(entity: dict[str, Any]) -> dict[str, Any]:
    """What to keep in the application queue for an entity too big to keep: that it was, not its text.

    A refusal is recorded, and recording it must not itself be the way the database gets filled. An
    entity that merely has one field over its ceiling is kept in full, so an applicant can see what
    they sent; one over the whole-document ceiling is kept as its id, kind, name and a flag.
    """
    if not document_refusal(entity):
        return entity
    return {
        "id": str(entity.get("id") or "")[:MAX_ID],
        "kind": str(entity.get("kind") or "")[:MAX_KIND],
        "name": str(entity.get("name") or "")[:MAX_NAME],
        "oversized": True,
    }


# ---------------------------------------------------------------- the request door


class BodyLimit:
    """ASGI middleware refusing a request body larger than `MAX_BODY_BYTES`, before it is parsed.

    Neither FastAPI nor uvicorn bounds a request body: a 20 MB application was read into memory,
    parsed into objects and stored. This answers 413 on the declared `Content-Length`, and counts
    the bytes as they arrive for a chunked request that declares nothing.

    Pure ASGI rather than `BaseHTTPMiddleware` on purpose: the MCP endpoint is mounted inside this
    app and streams, and wrapping it in a middleware that buffers would break it.
    """

    def __init__(self, app: Any, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Pass the request on, or answer 413 saying the limit and the size that arrived."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await _too_large(send, declared)
            return

        seen = 0
        refused = False

        async def counting_receive() -> dict[str, Any]:
            nonlocal seen, refused
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body") or b"")
                if seen > self.max_bytes:
                    refused = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: dict[str, Any]) -> None:
            if not refused:
                await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            # Cutting the body off mid-stream looks to the app like a client that hung up, and the
            # caller is owed the reason rather than that exception. Anything else is not ours.
            if not refused:
                raise
        if refused:
            await _too_large(send, seen)


def _declared_length(scope: dict[str, Any]) -> int | None:
    """The request's `Content-Length`, or None when it declares none or declares nonsense."""
    for name, value in scope.get("headers") or []:
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def body_refusal(size: int) -> str:
    """The sentence a caller gets when their body is too big: the limit and what arrived."""
    return f"a request body is at most {MAX_BODY_BYTES} bytes; this one is {size}"


# ---------------------------------------------------------------- the answer door
#
# The other half of `BodyLimit`. Bounding what arrives and not what leaves is half a job: a
# `hive_discover` at radius 2 over MCP answered with all 73 cards inline, about 690 KB, because a
# federated match carries the whole signed card rather than a reference to it. Nothing was over any
# limit and no counter had been breached — an unbounded answer is a resource hole on its own, and the
# caller had no way to ask for less because the tool took no limit at all.
#
# Bounded here at the MCP tool rather than in `hive.discover`: the ranking, the answer key in
# `testdata/` and the app all want the whole list, and a core that silently returned fewer matches
# than it found would make every measurement over it a different measurement. The agent-facing door
# is the one that needed a ceiling.

MAX_ANSWER_MATCHES = 50  # the most matches one MCP discovery answer carries, whatever the radius
DEFAULT_ANSWER_MATCHES = 20  # what it carries when the caller does not say


def bound_answer(found: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    """Cut a discovery answer down to `limit` matches, saying so when it cut anything.

    `limit` is clamped into 1..`MAX_ANSWER_MATCHES`, so neither a caller asking for everything nor
    one asking for nothing gets it. An answer that was cut carries `total_matches` and
    `truncated: True` beside the matches it kept: a client that reads only `matches` is never
    misled into thinking it saw the whole Hive, which is the honest half of a ceiling.

    Anything that is not a discovery answer — a refusal, say — is returned untouched.
    """
    matches = found.get("matches")
    if not isinstance(matches, list):
        return found
    cap = DEFAULT_ANSWER_MATCHES if limit is None else max(1, min(int(limit), MAX_ANSWER_MATCHES))
    if len(matches) <= cap:
        return found
    return found | {
        "matches": matches[:cap],
        "total_matches": len(matches),
        "truncated": True,
        "note": (
            f"This hub answers with at most {MAX_ANSWER_MATCHES} matches and {cap} were asked for; "
            f"{len(matches)} fit the query. Narrow it, or raise `limit`."
        ),
    }


async def _too_large(send: Any, size: int) -> None:
    """Answer 413 in the shape every other refusal on this hub has: `detail`, a sentence, no code."""
    body = json.dumps({"detail": body_refusal(size)}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
