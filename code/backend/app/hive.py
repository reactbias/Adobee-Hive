"""The Hive: agent-facing presence for local businesses (and people).

A *Hive Card* is the post-website homepage: one structured, signed document per business
that agents can query and act on. The same card renders as a human page (human fallback).

Trust model (all real, not mocked):
- Provenance: every published card version is signed with the owner's Ed25519 key.
  Agents get the public key and verify the signature themselves.
- Attestations: third parties (e.g. Basel Tourism) vouch for single claims.
- Proof-of-stay reviews: a review needs the signed receipt of a completed booking,
  so nobody can post reviews for a stay that never happened.
- Transparent ranking: discovery returns the score breakdown and the reasons a business
  matched or was excluded. No paid boosts.
- Missed demand: every exclusion is logged so the owner sees what agents asked for.
"""

import base64
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import db, limits, removals, reputation, semantic

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hive_cards (
    id VARCHAR PRIMARY KEY,
    slug VARCHAR,
    kind VARCHAR,
    version INTEGER,
    data JSON,
    signature VARCHAR,
    public_key VARCHAR,
    published_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hive_card_history (
    card_id VARCHAR,
    version INTEGER,
    data JSON,
    signature VARCHAR,
    public_key VARCHAR,
    PRIMARY KEY (card_id, version)
);
CREATE TABLE IF NOT EXISTS hive_keys (
    card_id VARCHAR PRIMARY KEY,
    private_key VARCHAR
);
CREATE TABLE IF NOT EXISTS hive_attestations (
    card_id VARCHAR,
    claim VARCHAR,
    attested_by VARCHAR,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hive_bookings (
    id VARCHAR PRIMARY KEY,
    card_id VARCHAR,
    unit_id VARCHAR,
    guest_name VARCHAR,
    guests INTEGER,
    check_in DATE,
    check_out DATE,
    total_chf DOUBLE,
    status VARCHAR,
    agent VARCHAR,
    notes VARCHAR,
    receipt VARCHAR,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hive_reviews (
    id VARCHAR PRIMARY KEY,
    card_id VARCHAR,
    booking_id VARCHAR UNIQUE,
    rating INTEGER,
    text VARCHAR,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hive_events (
    card_id VARCHAR,
    kind VARCHAR,
    detail VARCHAR,
    created_at TIMESTAMP
);
"""


# Signed facts go stale: every version says until when it holds, so a copy scraped last season expires on its own.
FRESH_DAYS = 90


def is_fresh(card: dict[str, Any]) -> bool:
    """Whether a card's signed facts still hold. Cards signed before expiry existed count as fresh."""
    until = card.get("valid_until")
    return not until or datetime.fromisoformat(until) > datetime.now(UTC)


class HiveError(ValueError):
    """A request the Hive refuses, such as an unknown card or a sold-out room. Maps to HTTP 400."""


def init() -> None:
    """Create the Hive tables if they don't exist."""
    with db.cursor() as cur:
        cur.execute(SCHEMA_SQL)


# ---------------------------------------------------------------- signing


def canonical(data: dict[str, Any]) -> bytes:
    """Serialise data deterministically (sorted keys, compact), the exact bytes that get signed."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _key_for(card_id: str) -> Ed25519PrivateKey:
    with db.cursor() as cur:
        row = cur.execute("SELECT private_key FROM hive_keys WHERE card_id = ?", [card_id]).fetchone()
    if row:
        return serialization.load_pem_private_key(row[0].encode(), password=None)  # type: ignore[return-value]
    # A card with no key row was signed by its owner elsewhere. Minting one here would quietly replace the owner.
    if get_record(card_id) is not None:
        raise HiveError(f"{card_id} signs its own card, so this hub holds no key for it: use its own node.")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with db.write() as cur:
        cur.execute("INSERT INTO hive_keys VALUES (?, ?)", [card_id, pem.decode()])
    return key


def _public_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def verify(data: dict[str, Any], signature: str, public_key: str) -> bool:
    """What any agent can do on its own with the public key."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        pub.verify(base64.b64decode(signature), canonical(data))
        return True
    except (InvalidSignature, ValueError):
        return False


def signing_keys() -> dict[str, str]:
    """Every public key the Hive holds a signing key for: businesses by card id, ruleset authors as "ruleset:<id>"."""
    with db.cursor() as cur:
        rows = cur.execute("SELECT card_id, private_key FROM hive_keys ORDER BY card_id").fetchall()
    return {
        card_id: _public_b64(serialization.load_pem_private_key(pem.encode(), password=None))  # type: ignore[arg-type]
        for card_id, pem in rows
    }


def owner_keys() -> dict[str, str]:
    """The key registry: each business's pinned public key, published in /.well-known/hive.json.

    A valid signature alone proves nothing if anyone can put their own key in the card. Agents accept a card only if
    it is signed by the key pinned here for that card id.
    """
    with db.cursor() as cur:
        pinned = dict(cur.execute("SELECT id, public_key FROM hive_cards").fetchall())
    return pinned | {k: v for k, v in signing_keys().items() if not k.startswith("ruleset:")}


def verify_pinned(card: dict[str, Any], pins: dict[str, str]) -> bool:
    """Check a card as an agent received it: signed, and signed by the key pinned for its id."""
    trust = card.get("trust") or {}
    key = trust.get("public_key", "")
    data = {k: v for k, v in card.items() if k != "trust"}
    return bool(key) and pins.get(card.get("id", "")) == key and verify(data, trust.get("signature", ""), key)


def forge_demo(card_id: str) -> dict[str, Any]:
    """For the tamper demo: a copy with a changed fact, re-signed by a stranger's fresh key. Agents must reject it."""
    card = get_card(card_id)
    data = {k: v for k, v in card.items() if k != "trust"}
    if data.get("units"):
        data["units"][0]["price_chf"] = 1
    else:
        data["features"] = [*data.get("features", []), "free breakfast"]
    stranger = Ed25519PrivateKey.generate()
    signature = base64.b64encode(stranger.sign(canonical(data))).decode()
    return {**data, "trust": {**card["trust"], "signature": signature, "public_key": _public_b64(stranger)}}


def _sign_receipt(card_id: str, payload: dict[str, Any]) -> str:
    sig = _key_for(card_id).sign(canonical(payload))
    return base64.urlsafe_b64encode(canonical(payload)).decode() + "." + base64.urlsafe_b64encode(sig).decode()


def sign_statement(card_id: str, payload: dict[str, Any]) -> str:
    """Sign a statement (a receipt, an offer) with the business's key: base64url(body).base64url(signature)."""
    return _sign_receipt(card_id, payload)


def read_statement(statement: str) -> dict[str, Any]:
    """Return a signed statement's body without checking it; verify_statement() is the check."""
    try:
        return json.loads(base64.urlsafe_b64decode(statement.split(".")[0]))
    except (ValueError, IndexError) as err:
        raise HiveError("Malformed statement.") from err


def verify_statement(statement: str, public_key: str) -> bool:
    """What any agent can do on its own: check a signed statement against a business's pinned public key."""
    try:
        body_b64, sig_b64 = statement.split(".")
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        pub.verify(base64.urlsafe_b64decode(sig_b64), base64.urlsafe_b64decode(body_b64))
        return True
    except (InvalidSignature, ValueError):
        return False


def _check_receipt(card_id: str, receipt: str) -> dict[str, Any]:
    try:
        body_b64, sig_b64 = receipt.split(".")
        body = base64.urlsafe_b64decode(body_b64)
        _key_for(card_id).public_key().verify(base64.urlsafe_b64decode(sig_b64), body)
        return json.loads(body)
    except (ValueError, InvalidSignature) as err:
        raise HiveError("Receipt is not valid for this business.") from err


# ---------------------------------------------------------------- cards


def publish(card: dict[str, Any]) -> dict[str, Any]:
    """Sign and publish a new version of a card. `card` must carry id, slug, kind.

    The second door for `limits.py`: signup bounds what an entity may join with, and this bounds
    every version after it, or an entity registers politely and grows unbounded on its next update.
    """
    card = json.loads(json.dumps(card, default=str))
    card.pop("trust", None)
    try:
        card = limits.vet(card)
    except limits.LimitError as err:
        raise HiveError(str(err)) from err
    # Fill the standard contact channels before signing, so the guarantee is part of what the
    # owner signed rather than something added on the way out. Doing it after signing would
    # change the card's canonical form and break every signature check.
    card = with_contact(card)
    existing = get_record(card["id"])
    card["version"] = (existing["version"] + 1) if existing else 1
    signed_at = datetime.now(UTC)
    card["published_at"] = signed_at.isoformat(timespec="seconds")
    card["valid_until"] = (signed_at + timedelta(days=FRESH_DAYS)).isoformat(timespec="seconds")
    key = _key_for(card["id"])
    signature = base64.b64encode(key.sign(canonical(card))).decode()
    return _store_version(card, signature, _public_b64(key))


def _check_shape(card: dict[str, Any]) -> None:
    """Refuse a signed card this hub could not serve. A valid signature says who wrote it, not that it is usable."""
    for field in ("id", "slug", "kind", "name", "valid_until"):
        if not card.get(field) or not isinstance(card[field], str):
            raise HiveError(f"A signed card needs {field}, as text.")
    if not isinstance(card.get("version"), int) or isinstance(card["version"], bool) or card["version"] < 1:
        raise HiveError("A signed card needs version, as a positive whole number.")
    for field in ("description", "tagline", "address"):
        if not isinstance(card.get(field, ""), str):
            raise HiveError(f"A signed card's {field} must be text.")
    for field in ("contact", "distances_m", "policies"):
        if not isinstance(card.get(field, {}), dict):
            raise HiveError(f"A signed card's {field} must be a map.")
    features = card.get("features", [])
    if not isinstance(features, list) or not all(isinstance(f, str) for f in features):
        raise HiveError("A signed card's features must be a list of text.")
    units = card.get("units", [])
    if not isinstance(units, list) or not all(_is_unit(u) for u in units):
        raise HiveError("A signed card's units each need id, name, max_guests, price_chf and quantity.")


def _is_unit(unit: Any) -> bool:
    """Whether one unit has what availability and booking read from it."""
    return (
        isinstance(unit, dict)
        and all(isinstance(unit.get(field), str) and unit[field] for field in ("id", "name"))
        and all(
            isinstance(unit.get(field), int | float) and not isinstance(unit[field], bool)
            for field in ("max_guests", "price_chf", "quantity")
        )
    )


def accept_signed(card: dict[str, Any], signature: str, public_key: str) -> dict[str, Any]:
    """Store a card version its owner signed on their own node, exactly as signed.

    The first version pins the key, and every later version must verify against that key. The hub stores what it
    was given and holds no private key, so it can neither change this card nor book it.
    """
    card = json.loads(json.dumps(card, default=str))
    _check_shape(card)
    if not verify(card, signature, public_key):
        raise HiveError("The signature does not match this card and key.")
    try:
        if limits.vet(card) != card:  # normalising would change the signed bytes, so the owner has to do it
            raise HiveError("This card is not in the hub's normal form; publish it through hive.publish first.")
    except limits.LimitError as err:
        raise HiveError(str(err)) from err
    existing = get_record(card["id"])
    by_slug = get_record(card["slug"])
    if by_slug is not None and by_slug["id"] != card["id"]:
        raise HiveError(f"The slug {card['slug']} belongs to another card.")
    pinned = existing["public_key"] if existing else signing_keys().get(card["id"])
    if pinned and pinned != public_key:
        raise HiveError(f"{card['id']} is pinned to another key.")
    if existing:
        if card["version"] == existing["version"] and signature == existing["signature"]:
            return get_card(card["id"])  # a repeat of what is already stored, say after a restart
        if card["version"] <= existing["version"]:
            raise HiveError(f"Version {card['version']} is not newer than version {existing['version']}.")
    return _store_version(card, signature, public_key)


def _store_version(card: dict[str, Any], signature: str, public_key: str) -> dict[str, Any]:
    """Write one signed version as the current card and into its history."""
    with db.write() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO hive_cards VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                card["id"],
                card["slug"],
                card["kind"],
                card["version"],
                json.dumps(card),
                signature,
                public_key,
                db.now(),
            ],
        )
        # Every signed version is kept, so a receipt can later prove what the card said when it was booked.
        cur.execute(
            "INSERT OR REPLACE INTO hive_card_history VALUES (?, ?, ?, ?, ?)",
            [card["id"], card["version"], json.dumps(card), signature, public_key],
        )
    return get_card(card["id"])


def get_record(card_id_or_slug: str) -> dict[str, Any] | None:
    """Return the stored row for a card id or slug, or None."""
    with db.cursor() as cur:
        found = db.rows(
            cur.execute("SELECT * FROM hive_cards WHERE id = ? OR slug = ?", [card_id_or_slug, card_id_or_slug])
        )
    if not found:
        return None
    rec = found[0]
    rec["data"] = json.loads(rec["data"])
    return rec


def _trust(rec: dict[str, Any]) -> dict[str, Any]:
    with db.cursor() as cur:
        att = db.rows(
            cur.execute(
                "SELECT claim, attested_by FROM hive_attestations WHERE card_id = ? ORDER BY claim", [rec["id"]]
            )
        )
        stats = cur.execute("SELECT count(*), avg(rating) FROM hive_reviews WHERE card_id = ?", [rec["id"]]).fetchone()
        recent = db.rows(
            cur.execute(
                "SELECT rating, text, created_at FROM hive_reviews WHERE card_id = ? ORDER BY created_at DESC LIMIT 3",
                [rec["id"]],
            )
        )
    published = rec["published_at"]
    provenance = rec["data"].get("provenance")
    age_days = (datetime.now() - published).days if isinstance(published, datetime) else None
    return {
        "signature_valid": verify(rec["data"], rec["signature"], rec["public_key"]),
        # A card compiled from public sources is signed by the Hive as compiler, not by the business.
        "claimed": not (provenance and provenance.get("verified_by_owner") is False),
        "provenance": provenance,
        "signature": rec["signature"],
        "public_key": rec["public_key"],
        "algorithm": "Ed25519 over canonical JSON (sorted keys, no spaces)",
        "attestations": att,
        "verified_reviews": {
            "count": stats[0],
            "average": round(stats[1], 2) if stats[1] else None,
            "recent": recent,
            "rule": reputation.BOOKING_RECEIPT_RULE,
        },
        "freshness_days": age_days,
        "fresh": is_fresh(rec["data"]),
        # Still carried by this hub? A withdrawn entity keeps its signature and its history, so the
        # card reads exactly as the owner signed it; what changed is that this hub no longer offers it.
        "carried": not removals.is_withdrawn(rec["id"]),
    }


#: Channels every card carries, even when empty. A caller should never have to guard
#: `contact?.email?`: the key is there, and "" means "not published", which is renderable.
#: The map stays open — an entity may add mobile, address, mcp, or anything it actually uses.
CONTACT_CHANNELS = ("email", "phone")


def with_contact(card: dict[str, Any]) -> dict[str, Any]:
    """Guarantee `contact` exists and carries the standard channels, without inventing values.

    An absent channel and an empty one are not the same thing to a reader, so this only fills in
    the keys; it never fabricates a value. A channel the owner marked `never` stays absent
    entirely, because listing it in order to say it is private announces that it exists.
    """
    contact = dict(card.get("contact") or {})
    for channel in CONTACT_CHANNELS:
        if (card.get("contact_sharing") or {}).get(channel) in ("never", "push"):
            continue
        contact.setdefault(channel, "")
    return {**card, "contact": contact}


def get_card(card_id_or_slug: str) -> dict[str, Any]:
    """Return the latest card with its trust block (signature, public key, attestations, reviews)."""
    rec = get_record(card_id_or_slug)
    if not rec:
        raise HiveError(f"No Hive card '{card_id_or_slug}'.")
    return {**rec["data"], "trust": _trust(rec)}


def list_cards(kind: str | None = None, include_withdrawn: bool = False) -> list[dict[str, Any]]:
    """Return every card this hub carries, optionally only one kind, ordered by slug.

    An entity an operator withdrew is not carried, so it is left out here. This is the one place
    that guarantee is kept: discovery, the demand map and the hub's own count all read this list,
    so a withdrawal cannot be enforced in one of them and forgotten in the next. `include_withdrawn`
    is for administration, which has to be able to see what it removed in order to put it back.
    """
    with db.cursor() as cur:
        sql = "SELECT id FROM hive_cards" + (" WHERE kind = ?" if kind else "") + " ORDER BY slug"
        ids = [r[0] for r in cur.execute(sql, [kind] if kind else []).fetchall()]
    if not include_withdrawn:
        gone = removals.withdrawn()
        ids = [i for i in ids if i not in gone]
    return [get_card(i) for i in ids]


def carried(card_id: str) -> None:
    """Refuse an action on an entity this hub has withdrawn, naming it. Raises `HiveError`."""
    if removals.is_withdrawn(card_id):
        raise HiveError(f"This hub no longer carries '{card_id}'.")


def _log(card_id: str, kind: str, detail: str) -> None:
    _log_many([(card_id, kind, detail)])


def record_event(card_id: str, kind: str, detail: str) -> None:
    """Log a domain event against a card (shown to its owner). For use cases built on the Hive core."""
    _log(card_id, kind, detail)


def record_events(events: list[tuple[str, str, str]]) -> None:
    """Log several (card_id, kind, detail) events in one write."""
    _log_many(events)


def _log_many(events: list[tuple[str, str, str]]) -> None:
    if not events:
        return
    with db.write() as cur:
        cur.executemany("INSERT INTO hive_events VALUES (?, ?, ?, ?)", [[*e, db.now()] for e in events])


# ---------------------------------------------------------------- discovery


MAX_NIGHTS = 30
MAX_GUESTS = 20
MAX_TEXT = 2000  # review text and booking notes
MAX_NAME = 100


def stay_nights(check_in: str, check_out: str) -> int:
    """Return the nights between two ISO dates; refuses bad dates and stays over MAX_NIGHTS."""
    try:
        n = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    except (TypeError, ValueError) as err:
        raise HiveError("Dates must be YYYY-MM-DD.") from err
    if not 0 < n <= MAX_NIGHTS:
        raise HiveError(f"A stay must be 1 to {MAX_NIGHTS} nights.")
    return n


def _units_free(card: dict[str, Any], check_in: str, check_out: str, guests: int) -> list[dict[str, Any]]:
    with db.cursor() as cur:
        booked = dict(
            cur.execute(
                """SELECT unit_id, count(*) FROM hive_bookings
               WHERE card_id = ? AND status = 'confirmed' AND check_in < ? AND check_out > ?
               GROUP BY unit_id""",
                [card["id"], check_out, check_in],
            ).fetchall()
        )
    nights = stay_nights(check_in, check_out)
    free = []
    for unit in card.get("units", []):
        left = unit["quantity"] - booked.get(unit["id"], 0)
        if left > 0 and unit["max_guests"] >= guests:
            free.append({**unit, "left": left, "nights": nights, "total_chf": round(unit["price_chf"] * nights, 2)})
    return sorted(free, key=lambda u: u["total_chf"])


# Kept so the stay-specific paths (availability, booking) still know which kinds have rooms.
# It is no longer what discovery searches: see `discover`.
STAY_KINDS = ("hotel", "cafe")

#: Nothing is hidden from discovery by its kind any more. A hub holds hotels, developers and
#: hairdressers side by side, and a directory that can only answer "where do I sleep" is not a
#: directory. What an entity *offers* and what it *needs* is the index; `kind` only narrows it.
NOT_DISCOVERABLE: set[str] = set()

#: What the hard constraints are worth, and they have to be earned: this is paid for constraints
#: the ask actually carried and the card met, and not at all for an ask with nothing to check.
#: Granting it for the absence of a check was the worst bug in the ranking — a query for "dataviz"
#: answered with eight hotels, each on a free 50 for passing an empty test, above the one person
#: who offers a dataviz sprint and earned 20 for it honestly.
CONSTRAINT_POINTS = 50

#: What being *close* to the ask is worth, per query word the close match covers, and why it is eight rather
#: than ten: a literal hit on what an entity offers or needs is worth ten per word, so word for word, having
#: the thing beats having something like it, and `_close_hit` does not pay at all for a side the words already
#: matched. Counted per word and not in proportion to the similarity, because the rest of the scoring is
#: counted that way too — a term either appears or it does not, and repeating it earns nothing. A similarity
#: of 0.4 is not "40% of a match"; it is a match, found in a card written in another language.
SEMANTIC_POINTS = 8
#: And the ceiling, three words' worth: under the thirty a literal match can reach, so an entity that really
#: offers the thing still comes first when both match on the same breadth of the question.
SEMANTIC_CAP = 24

#: The same thing for the entity's own prose — its name, tagline, description and features — at half the rate,
#: because `offers` and `needs` are claims an entity can be held to and rated against while a description is
#: the entity's own words about itself. That is the only reason prose is worth less: not suspicion. Writing a
#: description an agent can find is the business doing its job, and it is how a hub reaches a *Gästehaus* whose
#: rooms are listed as "Zimmer". The four rates together are the whole ranking argument, per word of the ask:
#:
#:     really offers it 10  >  offers something close 8  >  says it 5  >  says something close 4
#:
#: so having the thing beats being near it, and a structured claim beats prose, at both ends. The prose is read
#: last as well as lowest: an entity whose `offers` answered the question, exactly or closely, is not also paid
#: for what it says about itself, so one card never collects twice for one question.
SEMANTIC_TEXT_POINTS = 4
SEMANTIC_TEXT_CAP = 12

#: Which side of the market a search is on. "offers" finds someone who provides the thing,
#: "needs" finds someone who wants what you provide, "any" both.
LOOKING_FOR = ("offers", "needs", "any")

#: Words in an offer or a need that a search should match on even when they are not in the prose. The prose
#: fields come first because a semantic hit quotes the entry back at the person who searched, and "Cut, wash
#: and finish" is a reason where "cut-wash-finish short practical" is a database row.
OFFER_FIELDS = ("title", "summary", "description", "skills", "unit", "tags", "id")

#: Kinds whose sharing default is `confirm` rather than `public` when their card sets no flag of
#: its own: an introduction to a person is that person's to grant, even if their card never said
#: so. Only reachable since discovery stopped hiding people — before, nobody could find one to ask.
CONSENT_FIRST_KINDS = {"person"}

#: Kinds that never get a `missed_demand` row written against them. Missed demand is a market
#: signal a business asked for ("agents wanted X and you don't have it"); kept against a person it
#: is a log of the times they were passed over, which is not the hub's to keep. People are
#: discoverable now, so this is what used to be the side effect of hiding them.
NO_MISSED_DEMAND = {"person"}

RANKING_POLICY = (
    "The constraints you gave first, and nothing is paid for a check nobody asked for; then what the entity "
    "offers or needs, then relevance, proximity, verified reviews, attestations. No paid placement."
)

#: The score components the *question* earned, as against what the entity earned over time.
#:
#: This split is the whole of "did anything actually match?". `reputation.business_points` pays an entity for
#: verified reviews and attestations whatever was asked, so the **total** cannot answer that question: four
#: Basel hotels score 1-2 on *every* query, including `asdfghjkl qwertz` and the empty one, with an empty
#: `why` — and "threshold on score > 0 yourself", which is what this hub told its callers to do, does not
#: work because of exactly those rows. These five components are the ones a caller can honestly threshold on.
RELEVANCE_COMPONENTS = ("constraints", "text_relevance", "offers_needs", "semantic", "proximity")


def relevance(match: dict[str, Any]) -> float:
    """How much of a match's score the question itself earned. Zero means it answered nothing.

    An entity can score without answering anything — reputation is paid on every query — so this, not
    `score`, is the test of whether a result is a result.
    """
    breakdown = match.get("score_breakdown") or {}
    return sum(breakdown.get(name) or 0 for name in RELEVANCE_COMPONENTS)


def asks_anything(
    query: str = "",
    features: list[str] | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
) -> bool:
    """Whether the caller gave the hub something to match on at all.

    The difference between a search and a browse, and the reason the threshold is not applied blindly. An
    empty ask is a legitimate "show me what is on this hub", and the honest answer to it is everything;
    an ask with words or constraints in it has something to be relevant *to*, and an entity that is
    relevant to none of it is not an answer to it. Without this distinction a thresholded hub would answer
    "show me everyone" with nobody.

    Deliberately tested on the raw query rather than on its tokens: a query made only of filler words is
    still a question somebody asked, and "nothing on this hub answers that" is the honest reply to it, not
    the whole directory. A place name is the exception: it is a stopword, so it could never earn anything,
    and a hub that answers "Basel" with "nothing here" is wrong about itself. Naming only a place is a
    browse. The hub does not check that its cards are in that place; see LIMITS.md.
    """
    text = (query or "").strip()
    names_only_a_place = not semantic.content_words(text) and bool(
        semantic.PLACE_NAMES.intersection(semantic.LETTERS.findall(semantic.fold(text)))
    )
    return bool((text and not names_only_a_place) or features or near or max_price_chf is not None)


def only_relevant(found: dict[str, Any], ask_had_content: bool, include_irrelevant: bool = False) -> dict[str, Any]:
    """Drop the matches the question earned nothing from, and say how many answered out of how many ranked.

    This is what makes "nothing matched" a state this hub can be in. Before it, a nonsense query returned
    all 73 entities with `matches: 73, excluded: 0` and four Basel hotels at the top on reputation alone
    with an empty `why` — and no field anywhere said that nothing had matched, so a caller could not tell a
    hit from a miss. The advice this hub gave instead, "threshold on `score > 0` yourself", does not work:
    those four hotels score 1-2 on every query there is, including the empty one.

    Hence `relevance` rather than `score`. Reputation is paid on every query, so it cannot be part of the
    test for whether a query was answered; the five components the ask itself earned can.

    Skipped for a browse (`ask_had_content` false — see `asks_anything`), because everything really is the
    answer to a question with nothing in it, and `include_irrelevant=True` turns it off for a caller that
    wants the unfiltered ranking back. It is a parameter rather than a policy for that reason: an open
    ranking does not get to decide on a caller's behalf what they are allowed to see.

    Applied at the doors, not inside `discover`: `main.py` for REST and `mcp_server.py` for MCP. The core
    keeps answering with the whole ranked list, because the answer key and `federation.py` read it and a core
    that returned fewer matches than it found would make every measurement taken over it a different
    measurement. The same reasoning put `limits.bound_answer`'s ceiling at the MCP door.

    What this is *not* is a response-size cap — that is `limits.bound_answer`. The two compose, and in the
    right order: the threshold removes the rows that answered nothing, which on a federated search are
    also the expensive ones, because every match carries a full inline card. Thresholding first means the
    ceiling spends its budget on matches instead of on filler.

    The inline `card` stays on the matches that survive, because the connect path reads it out of the
    search result (#146/#172). Fewer rows is what makes that affordable, not dropping the card.
    """
    matches = found.get("matches") or []
    considered = len(matches)
    if ask_had_content and not include_irrelevant:
        matches = [m for m in matches if relevance(m) > 0]
    return {
        **found,
        "matches": matches,
        # How many answered the question. This is the count to show a user, and `matched: 0` is the
        # "nothing matched" this hub could not say before.
        "matched": len(matches),
        # And how many entities were ranked to get them, so the first number has a denominator.
        "considered": considered,
    }


#: The shortest query word the literal search will look for. Literal containment pays 10 points a word on the
#: offers side, and a three-letter word is inside some card's prose by accident far more often than on
#: purpose, so the literal path asks for longer words than the similarity bag does.
MIN_TERM_LENGTH = 4

#: Filler words are `semantic.STOPWORDS`, and the literal search tokenises with `semantic.content_words`.
#:
#: There is no second list here any more. There was: 21 words, against the 323 of `semantic.STOPWORDS`, so
#: "where", "someone", "jemand", "pour" and "macht" were content words to the literal path and filler to the
#: semantic one. The literal path is the one that pays 10 points a word, which is how a screen-reader
#: auditor came second for a Python performance question on *"offers someone"*, and how the only card to
#: score for *"Ich suche jemanden, der meine Python-Simulation schneller macht"* was a roofer, on "macht".
#: Keeping a hub-specific list in step with a four-language one by hand is not a thing that stays done.
STOPWORDS = semantic.STOPWORDS


def query_terms(query: str) -> list[str]:
    """The words of a query the literal search will look for: folded, filler dropped, short words dropped.

    Sorted and de-duplicated, because each is scored once and the order of a caller's sentence is not
    evidence about a card.
    """
    return sorted(set(semantic.content_words(query, MIN_TERM_LENGTH)))


def _side_texts(card: dict[str, Any], side: str) -> list[str]:
    """One readable line per offer (or per need), whatever shape the owner wrote it in.

    An offer may be a string, or an object with a title, tags and a summary; a hub carries all
    sorts and the format should not decide whether someone is findable. One string per entry rather
    than one blob for the card, because a semantic hit quotes the entry it matched back to the
    person who searched.
    """
    texts = []
    for entry in card.get(side) or []:
        if isinstance(entry, str):
            texts.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        parts = []
        for field in OFFER_FIELDS:
            value = entry.get(field)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(v) for v in value)
        if parts:
            # Joined with a dash, so the snippet in a reason can stop at the owner's own first phrase.
            texts.append(" — ".join(parts))
    return texts


def _side_hits(card: dict[str, Any], side: str, terms: list[str]) -> list[str]:
    """Query terms that appear in an entity's offers or needs.

    Literal containment, and deliberately still literal: a term that is really there is worth more
    than one that is merely close. Returns the terms that matched, so a result can say *why* it
    matched rather than only that it did.
    """
    # Folded, not merely lower-cased: `terms` arrives folded, so an unfolded haystack would make folding
    # the query a regression — "cafe" is not a substring of "Café". Both sides, or neither.
    text = semantic.fold(" ".join(_side_texts(card, side)))
    return [term for term in terms if term in text]


#: How a match on each side is worth, and how it reads in a reason. `offers` and `needs` are what the entity
#: says it will do, `describes` is what it says it is.
SEMANTIC_SIDES = {
    "offers": (SEMANTIC_POINTS, SEMANTIC_CAP, "offers something close to"),
    "needs": (SEMANTIC_POINTS, SEMANTIC_CAP, "needs something close to"),
    "describes": (SEMANTIC_TEXT_POINTS, SEMANTIC_TEXT_CAP, "describes something close to"),
}


def _prose_texts(card: dict[str, Any]) -> list[str]:
    """What the entity says about itself, one sentence at a time.

    Sentence by sentence rather than as one blob, for the same reason the offers are read one entry at a
    time: a reason quotes the sentence it matched, and a whole description read at once dilutes the one
    sentence that answers the question with the five that do not.
    """
    prose = [card.get("name", ""), card.get("tagline") or "", " ".join(card.get("features", []))]
    prose += re.split(r"(?<=[.!?])\s+", card.get("description") or "")
    return [text.strip() for text in prose if text and text.strip()]


def _close_hit(card: dict[str, Any], query: str, sides: dict[str, list[str]]) -> tuple[str, semantic.Hit, int] | None:
    """The closest thing this entity offers, needs or says it is, with what that is worth. None below the floor.

    This is the whole answer to "a search for haircut misses a card that says cut, wash and finish". It reads
    the sides `_side_hits` and the text relevance read, and `sides` carries the literal hits found on each,
    because a side that already matched literally is not scored again: one side's evidence is counted once, at
    its strongest form. That keeps the component doing the job it was added for — finding what the words
    missed — and keeps a wording difference between two entities that both really offer the thing from
    deciding which of them comes first.

    The best side wins rather than the sides adding up, and ties on points go to the closer match, so an
    entity is paid for the strongest thing it has to say about the question and not for repeating it.
    """
    best: tuple[str, semantic.Hit, int] | None = None
    for side, literal in sides.items():
        if literal:
            continue
        rate, cap, _ = SEMANTIC_SIDES[side]
        texts = _prose_texts(card) if side == "describes" else _side_texts(card, side)
        hit = semantic.best(query, texts)
        if hit is None:
            continue
        points = min(cap, rate * len(hit.terms))
        if best is None or (points, hit.score) > (best[2], best[1].score):
            best = (side, hit, points)
    return best


def _close_reason(close: tuple[str, semantic.Hit, int] | None) -> list[str]:
    """Put a semantic hit into words: *offers something close to 'haircut': Cut, wash and finish*.

    "Open ranking" means every result explains itself, and a bare similarity number explains nothing, so the
    reason names the words of the question it answered and quotes the entity's own line back — a person can
    then judge the match instead of trusting it.

    There is no case where the points are paid and the reason is left out. There was: the reason used to be
    dropped when the literal reason already named the same words, which after `_close_hit` started reading the
    prose side meant a card could collect the points silently. A component nobody can see is not an open
    ranking, and `_close_hit` already refuses to score a side the words matched, so there is nothing to
    de-duplicate here.
    """
    if close is None:
        return []
    side, hit, _ = close
    return [f"{SEMANTIC_SIDES[side][2]} '{', '.join(hit.terms)}': {hit.snippet}"]


def fit(
    card: dict[str, Any],
    features: list[str],
    near: str | None = None,
    max_price_chf: float | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = 1,
) -> dict[str, Any]:
    """Check one card against hard constraints: why it fits, why not, the missing tags, its price and distance.

    `checked` is what the ask actually asked about and this card could be tested for, and `met` the
    part of it that held. An ask with no features, no dates and no budget checks nothing, and
    discover() pays nothing for passing it: a constraint score is earned, never granted.

    Pure: logs nothing. discover() ranks with it; standing requests (waiting.py) reuse it when a card changes.
    """
    reasons, misses = [], []
    checked, met = [], []
    if not is_fresh(card):
        misses.append(f"signed facts expired on {card['valid_until'][:10]}; the owner has to re-sign")
    card_feats = {f.lower() for f in card.get("features", [])}
    missing = [f for f in features if f not in card_feats]
    checked += features
    met += [f for f in features if f not in missing]
    if missing:
        misses.append(f"missing {', '.join(missing)}")
    elif features:
        reasons.append(f"has {', '.join(features)}")

    price, unit = None, None
    if check_in and check_out:
        checked.append("dates")
    if check_in and check_out and not card.get("units"):
        misses.append("takes no stay bookings")
    elif check_in and check_out:
        free = _units_free(card, check_in, check_out, guests)
        if not free:
            misses.append(f"no room for {guests} from {check_in} to {check_out}")
        else:
            unit, price = free[0], free[0]["price_chf"]
            met.append("dates")
            reasons.append(f"{unit['name']} free at CHF {price}/night")
    elif card.get("units"):
        price = min(u["price_chf"] for u in card["units"])
    # A budget can only be checked against a published price. An entity that publishes none is not
    # cheap, it is unknown, so it neither fails the budget nor earns anything for passing it.
    if max_price_chf is not None and price is not None:
        checked.append("budget")
        if price > max_price_chf:
            misses.append(f"cheapest fit CHF {price} > budget CHF {max_price_chf}")
        else:
            met.append("budget")

    dist = None
    if near:
        dist = (card.get("distances_m") or {}).get(near.lower())
        if dist is not None:
            reasons.append(f"{dist} m from {near}")
    return {
        "reasons": reasons,
        "misses": misses,
        "missing": missing,
        "price": price,
        "unit": unit,
        "distance_m": dist,
        "checked": checked,
        "met": met,
    }


def discover(
    query: str = "",
    kind: str | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    features: list[str] | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = 1,
    radius: int = 0,
    budget_ms: float | None = None,
    seen: list[str] | None = None,
    looking_for: str = "offers",
    semantic_search: bool = True,
) -> dict[str, Any]:
    """Find anyone on this Hive, by what they offer or what they need.

    Not a room search with other things bolted on. A hub carries hotels, developers and
    hairdressers side by side, so the index is `offers` and `needs`, and `kind` is a filter the
    caller may apply rather than a gate the hub applies on their behalf.

    looking_for is which side of the market you are on: "offers" (the default) finds someone who
    provides the thing, "needs" finds someone who wants what you provide, "any" finds both.

    Returns matches with a score breakdown, and the near-misses with why they missed. Every result
    says whether it is `claimed` by its subject and whether it is `bookable`: an unclaimed card is
    a lead compiled from public information, and no caller may treat one as a business that agreed.

    Matching is not only literal. Beside the terms a card really contains, each entity's offers and needs are
    compared with the query by `semantic.py`, so "haircut" finds *"Cut, wash and finish"* and "web developer"
    finds *"builds user interfaces in React"*. That is one score component with its own reason, never a
    replacement: a literal hit still wins, and nothing under `semantic.SIMILARITY_FLOOR` counts at all. Pass
    semantic_search=False for the literal baseline (what `tools/eval_search.py` measures against).

    radius is the hop limit across peer Hives: 0, the default, is this Hive only; 1 adds its direct peers, 2
    theirs, up to federation.MAX_RADIUS. budget_ms is the whole query's time budget and seen lists the hubs it
    has already visited (loop prevention); both only matter above radius 0. See federation.py.

    This returns every entity that failed no *hard* constraint, ranked, including the ones the query earned
    nothing from — deliberately, because the ranking, the answer key in `testdata/` and the app all want the
    whole list, and a core that quietly returned fewer matches than it found would make every measurement
    taken over it a different measurement. Deciding which of them is worth showing is a door's job:
    `relevance` and `only_relevant` are the test and the filter, and `main.py` and `mcp_server.py` apply
    them. See `only_relevant` for why `score > 0` is not that test.
    """
    if looking_for not in LOOKING_FOR:
        raise HiveError(f"looking_for must be one of {', '.join(LOOKING_FOR)}, not {looking_for!r}")
    if int(radius or 0) > 0:
        from . import federation  # imported here: federation builds on discover, so it imports this module

        ask = {
            "query": query,
            "kind": kind,
            "near": near,
            "max_price_chf": max_price_chf,
            "features": features,
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "looking_for": looking_for,
        }
        return federation.run(ask, int(radius), budget_ms, seen)
    forwarded = bool(seen)  # a non-empty `seen` means a peer hub forwarded this, not a local client
    features = [f.lower().strip() for f in (features or [])[:20] if f.strip()]
    query = query[:500]
    # What gets logged: the structured ask only. The free-text query can hold a name, so it is never stored.
    asked = ", ".join(
        [*features]
        + ([f"near {near}"] if near else [])
        + ([f"under CHF {max_price_chf:g}"] if max_price_chf else [])
        + ([f"{guests} guests"] if guests > 1 else [])
    )
    terms = query_terms(query)
    matches, excluded, events = [], [], []
    # How close each match's semantic hit actually was, kept beside the matches to break ties with.
    # The points are a whole number of points per query word covered, so ties are common and the sort
    # was settling them by the order `list_cards` happened to return — a hairdresser's "Flechtfrisur für
    # ein Fest" came before a caterer for "catering for a wedding of fifty people" on nothing but that.
    closeness: dict[str, float] = {}
    # Every entity, whatever it is. A hub carries hotels, developers and hairdressers together,
    # so the search is over what they offer and what they need; `kind` is a filter a caller may
    # apply, not a gate the hub applies for them.
    cards = list_cards(kind) if kind else list_cards()
    # An admin block has to bite here, on the path the API actually calls. Enforcing it only in
    # the hub façade left a blocked business still listed in every ordinary search, which is a
    # block that does nothing — found by blocking one and watching it come back.
    from . import blocklist

    blocked = blocklist.blocked_entities()
    for card in cards:
        if card["kind"] in NOT_DISCOVERABLE or card["id"] in blocked:
            continue
        found = fit(card, features, near, max_price_chf, check_in, check_out, guests)
        reasons, misses, price, dist = found["reasons"], found["misses"], found["price"], found["distance_m"]

        # Folded for the same reason `_side_hits` folds: `terms` is folded, so this has to be.
        text = semantic.fold(
            " ".join(
                [
                    card.get("name", ""),
                    card.get("tagline", ""),
                    card.get("description", ""),
                    " ".join(card.get("features", [])),
                ]
            )
        )
        hits = [t for t in terms if t in text]

        # The two sides of the market, and the reason one query can find a room, a developer or a
        # hairdresser. `looking_for` says which side the caller is on: "offers" to find someone who
        # provides, "needs" to find someone who wants what you provide, "any" for both.
        offer_hits = _side_hits(card, "offers", terms) if looking_for in ("offers", "any") else []
        need_hits = _side_hits(card, "needs", terms) if looking_for in ("needs", "any") else []
        side_hits = offer_hits + need_hits

        # And the same two sides read for *meaning* rather than for the exact word, which is what makes a
        # hairdresser findable by "haircut". `looking_for` gates it exactly as it gates the literal hits.
        sides = {"offers": offer_hits, "needs": need_hits} if looking_for == "any" else {looking_for: side_hits}
        close = _close_hit(card, query, sides) if semantic_search else None
        if semantic_search and close is None and not side_hits:
            # Nothing on the market side, exactly or closely. Only then is what the entity says about itself
            # worth reading, at half the rate: last resort, lowest rate, and never on top of a side that
            # already answered.
            close = _close_hit(card, query, {"describes": hits})

        trust = card["trust"]
        score = {
            # Earned, not granted: the weight is paid for constraints the ask carried and this card
            # met, and an ask that carried none pays nobody. Relevance — what the entity offers,
            # needs or says — is then free to decide a query that has nothing to verify.
            "constraints": CONSTRAINT_POINTS if found["checked"] and not misses else 0,
            "text_relevance": min(20, 5 * len(hits)),
            # An entity that literally offers (or needs) the thing asked for beats one that merely
            # mentions it in its prose, so this outweighs text relevance.
            "offers_needs": min(30, 10 * len(side_hits)),
            # Close, counted per word of the question it covers, and worth less per word than really
            # having the thing. `semantic.SIMILARITY_FLOOR` decides what counts as close at all.
            "semantic": close[2] if close else 0,
            "proximity": 0 if dist is None else max(0, 15 - dist // 150),
            # What this one business earned: verified reviews, attestations, a valid signature (reputation.py).
            **reputation.business_points(trust),
        }
        summary = {
            "id": card["id"],
            "slug": card["slug"],
            "name": card["name"],
            "kind": card["kind"],
            "tagline": card.get("tagline"),
            # The three fields every entity in the protocol carries, hub or business. The rating is the
            # verified-review average and stays None until a signed receipt produces one: no stay, no rating.
            "description": card.get("description") or "",
            "rating": trust["verified_reviews"]["average"],
            "rating_count": trust["verified_reviews"]["count"],
            # How to reach them, on the result itself. An agent that found someone should not have
            # to fetch the whole card to know whether there is an address to write to, and a
            # federated result has no cheap way to fetch it at all.
            "contact": (card.get("contact") or {}),
            "contact_sharing": (card.get("contact_sharing") or {}),
            # An unclaimed card was compiled from public information and the business never
            # published it, so it is a lead, not a presence: findable, never bookable, and a
            # hand-off to the business's own site only after a human says yes (domains/explore.py).
            "claimed": trust["claimed"],
            "bookable": bool(card.get("units")) and trust["claimed"],
            "from_price_chf": price,
            "distance_m": dist,
            "score": round(sum(score.values()), 1),
            "score_breakdown": score,
            "why": reasons
            + ([f"offers {', '.join(offer_hits)}"] if offer_hits else [])
            + ([f"needs {', '.join(need_hits)}"] if need_hits else [])
            + _close_reason(close)
            + ([f"mentions {', '.join(hits)}"] if hits else [])
            + ([] if trust["claimed"] else ["unclaimed: compiled from public information, hand-off only"]),
            "signature_valid": trust["signature_valid"],
        }
        if misses:
            excluded.append({**summary, "why_not": misses})
            if card["kind"] not in NO_MISSED_DEMAND:
                events.append(
                    (card["id"], "missed_demand", "; ".join(misses) + (f" (asked: {asked})" if asked else ""))
                )
        else:
            matches.append(summary)
            closeness[card["id"]] = close[1].score if close else 0.0
            events.append((card["id"], "shown", asked or "open search"))
    events.append(
        (
            "*",
            "search",
            json.dumps(
                {
                    "features": features,
                    "near": near,
                    "max_price_chf": max_price_chf,
                    "guests": guests,
                    "matched": len(matches),
                }
            ),
        )
    )
    _log_many(events)
    # Points first, and a tie on points goes to the closer match. `_close_hit` already prefers the closer
    # of two sides worth the same; this is the same rule one level up, and for the same reason: when the
    # points cannot separate two entities, the one that is actually more like the question should win.
    # Nothing here changes a score — closeness only orders entities the score has already tied.
    matches.sort(key=lambda m: (m["score"], closeness.get(m["id"], 0.0)), reverse=True)
    if forwarded:
        # A peer asked this, and it will verify every card against our key registry before showing
        # it to anyone. It can only do that if the signed card travels with the match, so attach it.
        # A direct caller gets the answer unchanged — backward compatibility is about them, not
        # about hops. Without this a federated search rejects every remote result with "no card to
        # check against the owner's key", which is what two real hubs showed the moment they met.
        matches = [{**m, "card": get_card(m["id"])} for m in matches]
    return {
        "matches": matches,
        "excluded": excluded,
        "ranking_policy": RANKING_POLICY,
    }


def check_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    """Return the units free for the whole stay and their totals. Refused for a withdrawn entity."""
    card = get_card(card_id)
    carried(card["id"])
    return {
        "card_id": card["id"],
        "name": card["name"],
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "available_units": _units_free(card, check_in, check_out, guests),
        "policies": card.get("policies", {}),
    }


# ---------------------------------------------------------------- transactions


def book(
    card_id: str,
    unit_id: str,
    check_in: str,
    check_out: str,
    guest_name: str,
    guests: int = 1,
    notes: str = "",
    agent: str = "unknown agent",
) -> dict[str, Any]:
    """Book a unit and return the confirmation with a signed receipt.

    Raises HiveError when the dates are invalid, the unit is unknown or sold out, the guest name is
    missing, or this hub has withdrawn the entity.
    """
    if not guest_name.strip() or len(guest_name) > MAX_NAME:
        raise HiveError(f"guest_name is required, at most {MAX_NAME} characters.")
    if not 1 <= guests <= MAX_GUESTS or len(notes) > MAX_TEXT:
        raise HiveError(f"guests must be 1 to {MAX_GUESTS}; notes at most {MAX_TEXT} characters.")
    card = get_card(card_id)
    # An entity the hub withdrew is not bookable. Checked here rather than at the REST door only,
    # so MCP, the card page and the agent all get the same answer.
    carried(card["id"])
    free = {u["id"]: u for u in _units_free(card, check_in, check_out, guests)}
    if unit_id not in free:
        raise HiveError(f"{unit_id} is not available for {guests} guest(s) from {check_in} to {check_out}.")
    unit = free[unit_id]
    booking_id = "bk_" + db.new_id()
    payload = {
        "booking_id": booking_id,
        "card_id": card["id"],
        "unit_id": unit_id,
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "total_chf": unit["total_chf"],
        "card_version": card["version"],
        "card_digest": card_digest(card),
    }
    receipt = _sign_receipt(card["id"], payload)
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hive_bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?)",
            [
                booking_id,
                card["id"],
                unit_id,
                guest_name,
                guests,
                check_in,
                check_out,
                unit["total_chf"],
                agent,
                notes,
                receipt,
                db.now(),
            ],
        )
    _log(card["id"], "booked", f"{unit['name']} {check_in}..{check_out} via {agent}")
    return {
        "status": "confirmed",
        **payload,
        "unit_name": unit["name"],
        "business": card["name"],
        "receipt": receipt,
        "payment": card.get("policies", {}).get("payment", "Pay at the property"),
        "cancellation": card.get("policies", {}).get("cancellation"),
        "human_contact": card.get("contact"),
    }


def cancel(booking_id: str, receipt: str) -> dict[str, Any]:
    """Cancel a booking; the signed receipt proves the caller made it."""
    with db.cursor() as cur:
        found = db.rows(cur.execute("SELECT * FROM hive_bookings WHERE id = ?", [booking_id]))
    if not found:
        raise HiveError("Unknown booking.")
    bk = found[0]
    if _check_receipt(bk["card_id"], receipt)["booking_id"] != booking_id:
        raise HiveError("Receipt does not belong to this booking.")
    if bk["status"] == "cancelled":
        raise HiveError("This booking is already cancelled.")
    with db.write() as cur:
        cur.execute("UPDATE hive_bookings SET status = 'cancelled' WHERE id = ?", [booking_id])
    _log(bk["card_id"], "cancelled", booking_id)
    return {"booking_id": booking_id, "status": "cancelled"}


def review(receipt: str, rating: int, text: str) -> dict[str, Any]:
    """Store a review for a completed booking. Each signed receipt can review once."""
    if len(text) > MAX_TEXT:
        raise HiveError(f"Review text is at most {MAX_TEXT} characters.")
    try:
        body = json.loads(base64.urlsafe_b64decode(receipt.split(".")[0]))
    except (ValueError, IndexError) as err:
        raise HiveError("Malformed receipt.") from err
    payload = _check_receipt(body.get("card_id", ""), receipt)
    if not 1 <= rating <= 5:
        raise HiveError("rating must be 1..5")
    with db.cursor() as cur:
        status = cur.execute("SELECT status FROM hive_bookings WHERE id = ?", [payload["booking_id"]]).fetchone()
        dup = cur.execute("SELECT 1 FROM hive_reviews WHERE booking_id = ?", [payload["booking_id"]]).fetchone()
    if not status or status[0] != "confirmed":
        raise HiveError("Only confirmed stays can be reviewed.")
    if dup:
        raise HiveError("This stay was already reviewed.")
    rid = "rv_" + db.new_id()
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hive_reviews VALUES (?, ?, ?, ?, ?, ?)",
            [rid, payload["card_id"], payload["booking_id"], rating, text[:1000], db.now()],
        )
    return {"review_id": rid, "card_id": payload["card_id"], "verified_stay": True}


# ---------------------------------------------------------------- owner side


def demand_map(days: int = 7) -> dict[str, Any]:
    """City-wide view of what agents asked for, and what nobody could offer.

    The unexpected use of the Hive: agents' unmet requests tell local businesses what to become.
    """
    with db.cursor() as cur:
        searches = [
            json.loads(r[0])
            for r in cur.execute(
                "SELECT detail FROM hive_events WHERE kind = 'search' AND created_at > ?",
                [db.now() - timedelta(days=days)],
            ).fetchall()
        ]
    asked: dict[str, dict[str, int]] = {}
    for search in searches:
        for feature in search["features"] or []:
            row = asked.setdefault(feature, {"asked": 0, "unserved": 0})
            row["asked"] += 1
            row["unserved"] += search["matched"] == 0
    features = sorted(
        ({"feature": f, **v, "unserved_share": round(v["unserved"] / v["asked"], 2)} for f, v in asked.items()),
        key=lambda r: (r["unserved"], r["asked"]),
        reverse=True,
    )
    return {
        "days": days,
        "searches": len(searches),
        "unserved_searches": sum(1 for s in searches if s["matched"] == 0),
        "features": features,
    }


def mask_name(name: str) -> str:
    """Reduce a guest name to initials, for anyone who is not the owner: "Mara Keller" -> "M. K."."""
    return " ".join(part[0] + "." for part in name.split() if part) or "Guest"


def owner_overview(card_id: str) -> dict[str, Any]:
    """Return what the owner studio shows: the card, its bookings or hand-offs and the demand it missed."""
    card = get_card(card_id)
    with db.cursor() as cur:
        bookings = db.rows(
            cur.execute(
                "SELECT id, unit_id, guest_name, guests, check_in, check_out, total_chf, status, agent, created_at "
                "FROM hive_bookings WHERE card_id = ? ORDER BY created_at DESC LIMIT 50",
                [card["id"]],
            )
        )
        missed = db.rows(
            cur.execute(
                "SELECT detail, count(*) AS times FROM hive_events WHERE card_id = ? AND kind = 'missed_demand' "
                "GROUP BY detail ORDER BY times DESC LIMIT 10",
                [card["id"]],
            )
        )
        counts = dict(
            cur.execute(
                "SELECT kind, count(*) FROM hive_events WHERE card_id = ? AND created_at > ? GROUP BY kind",
                [card["id"], db.now() - timedelta(days=7)],
            ).fetchall()
        )
        # A card without rooms is never booked here: its yes-moment is a hand-off to the business's own site.
        handed = cur.execute(
            "SELECT detail, created_at FROM hive_events WHERE card_id = ? AND kind = 'explore_handoff' "
            "ORDER BY created_at DESC LIMIT 50",
            [card["id"]],
        ).fetchall()
    titles = {i["id"]: i["title"] for i in card.get("offers", []) + card.get("events", [])}
    handoffs = [{"item": titles.get(item_id, item_id), "created_at": at} for item_id, at in handed]
    return {
        "card": card,
        "bookings": bookings,
        "handoffs": handoffs,
        "missed_demand": missed,
        "last_7_days": counts,
    }


def attest(card_id: str, claim: str, attested_by: str) -> None:
    """Record a third party vouching for one claim on a card."""
    with db.write() as cur:
        cur.execute("INSERT INTO hive_attestations VALUES (?, ?, ?, ?)", [card_id, claim, attested_by, db.now()])


def card_digest(card: dict[str, Any]) -> str:
    """Return a short hash of a card's content, without its trust block."""
    return hashlib.sha256(canonical({k: v for k, v in card.items() if k != "trust"})).hexdigest()[:16]


def what_was_promised(receipt: str) -> dict[str, Any]:
    """Return the signed card version a booking was made against, and which fields changed since.

    The receipt is checked first, so only the business's own signature can open its history. In a dispute the
    guest's agent can show the owner's signed words from the day of booking, not today's card.
    """
    payload = _check_receipt(read_statement(receipt).get("card_id", ""), receipt)
    if "card_version" not in payload:
        raise HiveError("This receipt is older than card history and names no card version.")
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT data, signature, public_key FROM hive_card_history WHERE card_id = ? AND version = ?",
            [payload["card_id"], payload["card_version"]],
        ).fetchone()
    if not row:
        raise HiveError("That card version is not in this Hive's history.")
    then = json.loads(row[0])
    now = {k: v for k, v in get_card(payload["card_id"]).items() if k != "trust"}
    return {
        "booking_id": payload["booking_id"],
        "card": {**then, "trust": {"signature": row[1], "public_key": row[2]}},
        "digest_matches": card_digest(then) == payload["card_digest"],
        "changed_since": sorted(
            k for k in set(then) | set(now) if k not in ("version", "published_at") and then.get(k) != now.get(k)
        ),
    }
