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

from . import db

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


def _sign_receipt(card_id: str, payload: dict[str, Any]) -> str:
    sig = _key_for(card_id).sign(canonical(payload))
    return base64.urlsafe_b64encode(canonical(payload)).decode() + "." + base64.urlsafe_b64encode(sig).decode()


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
    """Sign and publish a new version of a card. `card` must carry id, slug, kind."""
    card = json.loads(json.dumps(card, default=str))
    card.pop("trust", None)
    existing = get_record(card["id"])
    card["version"] = (existing["version"] + 1) if existing else 1
    card["published_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    key = _key_for(card["id"])
    signature = base64.b64encode(key.sign(canonical(card))).decode()
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
                _public_b64(key),
                db.now(),
            ],
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
    age_days = (datetime.now() - published).days if isinstance(published, datetime) else None
    return {
        "signature_valid": verify(rec["data"], rec["signature"], rec["public_key"]),
        "signature": rec["signature"],
        "public_key": rec["public_key"],
        "algorithm": "Ed25519 over canonical JSON (sorted keys, no spaces)",
        "attestations": att,
        "verified_reviews": {
            "count": stats[0],
            "average": round(stats[1], 2) if stats[1] else None,
            "recent": recent,
            "rule": "only guests with a signed booking receipt can review",
        },
        "freshness_days": age_days,
    }


def get_card(card_id_or_slug: str) -> dict[str, Any]:
    """Return the latest card with its trust block (signature, public key, attestations, reviews)."""
    rec = get_record(card_id_or_slug)
    if not rec:
        raise HiveError(f"No Hive card '{card_id_or_slug}'.")
    return {**rec["data"], "trust": _trust(rec)}


def list_cards(kind: str | None = None) -> list[dict[str, Any]]:
    """Return every card, optionally only one kind, ordered by slug."""
    with db.cursor() as cur:
        sql = "SELECT id FROM hive_cards" + (" WHERE kind = ?" if kind else "") + " ORDER BY slug"
        ids = [r[0] for r in cur.execute(sql, [kind] if kind else []).fetchall()]
    return [get_card(i) for i in ids]


def _log(card_id: str, kind: str, detail: str) -> None:
    _log_many([(card_id, kind, detail)])


def _log_many(events: list[tuple[str, str, str]]) -> None:
    if not events:
        return
    with db.write() as cur:
        cur.executemany("INSERT INTO hive_events VALUES (?, ?, ?, ?)", [[*e, db.now()] for e in events])


# ---------------------------------------------------------------- discovery


def _nights(check_in: str, check_out: str) -> int:
    n = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    if n <= 0:
        raise HiveError("check_out must be after check_in.")
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
    nights = _nights(check_in, check_out)
    free = []
    for unit in card.get("units", []):
        left = unit["quantity"] - booked.get(unit["id"], 0)
        if left > 0 and unit["max_guests"] >= guests:
            free.append({**unit, "left": left, "nights": nights, "total_chf": round(unit["price_chf"] * nights, 2)})
    return sorted(free, key=lambda u: u["total_chf"])


RANKING_POLICY = "Constraints first, then relevance, proximity, verified reviews, attestations. No paid placement."


STOPWORDS = {
    "book",
    "basel",
    "hotel",
    "near",
    "under",
    "with",
    "from",
    "that",
    "this",
    "please",
    "find",
    "name",
    "night",
    "nights",
    "friendly",
    "check",
    "late",
    "room",
    "rooms",
    "want",
    "need",
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
) -> dict[str, Any]:
    """Find businesses for an agent. Returns matches with score breakdown and the near-misses."""
    features = [f.lower().strip() for f in (features or []) if f.strip()]
    terms = sorted({t for t in re.findall(r"[a-zäöü]+", query.lower()) if len(t) > 3} - STOPWORDS)
    matches, excluded, events = [], [], []
    for card in list_cards(kind):
        reasons, misses = [], []
        card_feats = {f.lower() for f in card.get("features", [])}
        missing = [f for f in features if f not in card_feats]
        if missing:
            misses.append(f"missing {', '.join(missing)}")
        elif features:
            reasons.append(f"has {', '.join(features)}")

        price = None
        if check_in and check_out and not card.get("units"):
            misses.append("takes no stay bookings")
        elif check_in and check_out:
            free = _units_free(card, check_in, check_out, guests)
            if not free:
                misses.append(f"no room for {guests} from {check_in} to {check_out}")
            else:
                price = free[0]["price_chf"]
                reasons.append(f"{free[0]['name']} free at CHF {price}/night")
        elif card.get("units"):
            price = min(u["price_chf"] for u in card["units"])
        if max_price_chf is not None and price is not None and price > max_price_chf:
            misses.append(f"cheapest fit CHF {price} > budget CHF {max_price_chf}")

        dist = None
        if near:
            dist = (card.get("distances_m") or {}).get(near.lower())
            if dist is not None:
                reasons.append(f"{dist} m from {near}")

        text = " ".join(
            [
                card.get("name", ""),
                card.get("tagline", ""),
                card.get("description", ""),
                " ".join(card.get("features", [])),
            ]
        ).lower()
        hits = [t for t in terms if t in text]

        trust = card["trust"]
        score = {
            "constraints": 0 if misses else 50,
            "text_relevance": min(20, 5 * len(hits)),
            "proximity": 0 if dist is None else max(0, 15 - dist // 150),
            "verified_reviews": round((trust["verified_reviews"]["average"] or 0) * 2, 1),
            "attestations": min(5, len(trust["attestations"])),
            "signature": 0 if trust["signature_valid"] else -100,
        }
        summary = {
            "id": card["id"],
            "slug": card["slug"],
            "name": card["name"],
            "kind": card["kind"],
            "tagline": card.get("tagline"),
            "from_price_chf": price,
            "distance_m": dist,
            "score": round(sum(score.values()), 1),
            "score_breakdown": score,
            "why": reasons + ([f"mentions {', '.join(hits)}"] if hits else []),
            "signature_valid": trust["signature_valid"],
        }
        if misses:
            excluded.append({**summary, "why_not": misses})
            events.append((card["id"], "missed_demand", "; ".join(misses) + (f" (asked: {query})" if query else "")))
        else:
            matches.append(summary)
            events.append((card["id"], "shown", query or "structured search"))
    events.append(
        (
            "*",
            "search",
            json.dumps(
                {
                    "query": query,
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
    matches.sort(key=lambda m: m["score"], reverse=True)
    return {
        "matches": matches,
        "excluded": excluded,
        "ranking_policy": RANKING_POLICY,
    }


def check_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    """Return the units free for the whole stay and their totals."""
    card = get_card(card_id)
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

    Raises HiveError when the dates are invalid, the unit is unknown or sold out, or the guest name is missing.
    """
    card = get_card(card_id)
    free = {u["id"]: u for u in _units_free(card, check_in, check_out, guests)}
    if unit_id not in free:
        raise HiveError(f"{unit_id} is not available for {guests} guest(s) from {check_in} to {check_out}.")
    if not guest_name.strip():
        raise HiveError("guest_name is required.")
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
    with db.write() as cur:
        cur.execute("UPDATE hive_bookings SET status = 'cancelled' WHERE id = ?", [booking_id])
    _log(bk["card_id"], "cancelled", booking_id)
    return {"booking_id": booking_id, "status": "cancelled"}


def review(receipt: str, rating: int, text: str) -> dict[str, Any]:
    """Store a review for a completed booking. Each signed receipt can review once."""
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


def owner_overview(card_id: str) -> dict[str, Any]:
    """Return what the owner studio shows: the card, its bookings and the demand it missed."""
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
    return {"card": card, "bookings": bookings, "missed_demand": missed, "last_7_days": counts}


def attest(card_id: str, claim: str, attested_by: str) -> None:
    """Record a third party vouching for one claim on a card."""
    with db.write() as cur:
        cur.execute("INSERT INTO hive_attestations VALUES (?, ?, ?, ?)", [card_id, claim, attested_by, db.now()])


def card_digest(card: dict[str, Any]) -> str:
    """Return a short hash of a card's content, without its trust block."""
    return hashlib.sha256(canonical({k: v for k, v in card.items() if k != "trust"})).hexdigest()[:16]
