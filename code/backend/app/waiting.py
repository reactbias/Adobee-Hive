"""Demand that waits: when no business fits, a traveller's agent can leave a standing request and be told when one does.

Missed demand shows an owner what agents asked for. A standing request is a guest still at the door: the owner
sees how many agents are waiting and what they would spend, and the moment a re-signed card fits, each waiting
agent gets an offer signed with the business's own key.

Rules that keep this from becoming spam or profiling (keep them):
- Opt-in. Only an agent whose traveller asked to be told leaves a request; businesses never see a request list.
- Anonymous. A request holds the structured ask (the same fields as the search log), never a name or free text.
  The agent keeps a secret token; the Hive stores only its hash.
- Bounded. A request ends at check-in or after MAX_DAYS, at most MAX_OPEN are open, one offer per business each.
- Signed. An offer is a statement signed by the business, checked against the key pinned in /.well-known/hive.json.
- Nothing is booked. An offer holds no room; the traveller's agent still asks its human before hive_book.
"""

import hashlib
import json
import secrets
from datetime import date, datetime, time, timedelta
from typing import Any

from . import db, hive

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hive_waiting (
    id VARCHAR PRIMARY KEY,
    token_hash VARCHAR,
    kind VARCHAR,
    ask JSON,
    status VARCHAR,
    created_at TIMESTAMP,
    expires_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hive_offers (
    request_id VARCHAR,
    card_id VARCHAR,
    offer VARCHAR,
    created_at TIMESTAMP,
    PRIMARY KEY (request_id, card_id)
);
"""
TABLES = ("hive_offers", "hive_waiting")
MAX_DAYS = 30
MAX_OPEN = 500


def init() -> None:
    """Create the standing-request tables if they don't exist."""
    with db.cursor() as cur:
        cur.execute(SCHEMA_SQL)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _open(kind: str | None = None) -> list[dict[str, Any]]:
    with db.cursor() as cur:
        found = db.rows(
            cur.execute(
                "SELECT id, kind, ask FROM hive_waiting WHERE status = 'waiting' AND expires_at > ?"
                + (" AND kind = ?" if kind else "")
                + " ORDER BY created_at",
                [db.now(), kind] if kind else [db.now()],
            )
        )
    return [{**r, "ask": json.loads(r["ask"])} for r in found]


def _fits(card: dict[str, Any], ask: dict[str, Any]) -> dict[str, Any]:
    return hive.fit(card, **ask)


def leave(
    features: list[str] | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    check_in: str = "",
    check_out: str = "",
    guests: int = 1,
    kind: str = "hotel",
) -> dict[str, Any]:
    """Leave a standing request for a stay nobody offers yet. Returns the request id and the agent's secret token.

    Refused when a business already fits: then the agent should book, not wait.
    """
    ask = {
        "features": sorted({f.lower().strip() for f in (features or [])[:10] if f.strip()}),
        "near": near.lower().strip()[:60] if near else None,
        "max_price_chf": max_price_chf,
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
    }
    nights = hive.stay_nights(check_in, check_out)  # validates the dates
    if not 1 <= guests <= hive.MAX_GUESTS:
        raise hive.HiveError(f"guests must be 1 to {hive.MAX_GUESTS}.")
    if not ask["features"] and max_price_chf is None:
        raise hive.HiveError("Say what is missing: at least one feature or a budget.")
    arrival = datetime.combine(date.fromisoformat(check_in), time(), tzinfo=db.now().tzinfo)
    expires = min(arrival, db.now() + timedelta(days=MAX_DAYS))
    if expires <= db.now():
        raise hive.HiveError("This stay starts too soon to wait for.")
    fitting = [c["name"] for c in hive.list_cards(kind) if not _fits(c, ask)["misses"]]
    if fitting:
        raise hive.HiveError(f"Already offered by {', '.join(fitting)}. Book instead of waiting.")
    if len(_open()) >= MAX_OPEN:
        raise hive.HiveError("The Hive holds too many standing requests right now. Try again later.")
    request_id, token = "wr_" + db.new_id(), secrets.token_urlsafe(16)
    with db.write() as cur:
        cur.execute(
            "INSERT INTO hive_waiting VALUES (?, ?, ?, ?, 'waiting', ?, ?)",
            [request_id, _hash(token), kind, json.dumps(ask), db.now(), expires],
        )
    return {
        "request_id": request_id,
        "token": token,
        "expires_at": expires.isoformat(timespec="minutes"),
        "nights": nights,
        "note": "Keep the token. Ask hive_check_waiting later; an offer is signed by the business and books nothing.",
    }


def check(request_id: str, token: str) -> dict[str, Any]:
    """Return a standing request's status and any signed offers. Only the holder of the token may ask."""
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT token_hash, status, expires_at FROM hive_waiting WHERE id = ?", [request_id]
        ).fetchone()
        offers = cur.execute(
            "SELECT card_id, offer FROM hive_offers WHERE request_id = ? ORDER BY created_at", [request_id]
        ).fetchall()
    if not row or not secrets.compare_digest(row[0], _hash(token)):
        raise hive.HiveError("Unknown request or wrong token.")
    status = row[1] if row[1] != "waiting" or row[2] > db.now().replace(tzinfo=None) else "expired"
    return {
        "request_id": request_id,
        "status": status,
        "offers": [{"card_id": card_id, "offer": offer, **hive.read_statement(offer)} for card_id, offer in offers],
    }


def on_publish(card: dict[str, Any]) -> int:
    """Offer a newly signed card to every waiting agent it now fits. Returns how many offers went out."""
    with db.cursor() as cur:
        rows = cur.execute("SELECT request_id FROM hive_offers WHERE card_id = ?", [card["id"]]).fetchall()
    told = {r[0] for r in rows}
    sent = []
    for req in _open(card["kind"]):
        if req["id"] in told:
            continue
        found = _fits(card, req["ask"])
        if found["misses"] or not found["unit"]:
            continue
        unit, ask = found["unit"], req["ask"]
        payload = {
            "type": "offer",
            "request_id": req["id"],
            "card_id": card["id"],
            "card_version": card["version"],
            "business": card["name"],
            "unit_id": unit["id"],
            "unit_name": unit["name"],
            "check_in": ask["check_in"],
            "check_out": ask["check_out"],
            "guests": ask["guests"],
            "total_chf": unit["total_chf"],
            "why": found["reasons"],
        }
        sent.append([req["id"], card["id"], hive.sign_statement(card["id"], payload), db.now()])
    if sent:
        with db.write() as cur:
            cur.executemany("INSERT INTO hive_offers VALUES (?, ?, ?, ?)", sent)
            cur.executemany("UPDATE hive_waiting SET status = 'offered' WHERE id = ?", [[s[0]] for s in sent])
        hive.record_event(
            card["id"], "offers_sent", f"{len(sent)} waiting agent(s) told about version {card['version']}"
        )
    return len(sent)


def owner_view(card_id: str) -> dict[str, Any]:
    """What one owner may see: agents waiting for a change this card could make, grouped by the change, with budgets.

    A group is the edit that would win those agents: tags to add, and whether the price must come down. Requests
    this card cannot serve by an edit (it is full) are left out. Counts and sums only: the owner never sees a single
    request, its token or when it was made.
    """
    card = hive.get_card(card_id)
    groups: dict[tuple, dict[str, Any]] = {}
    for req in _open(card["kind"]):
        found = _fits(card, req["ask"])
        cheaper = any(m.startswith("cheapest fit") for m in found["misses"])
        if not found["misses"] or len(found["misses"]) > bool(found["missing"]) + cheaper:
            continue  # fits already (an offer went out), or no edit can make room
        key = (tuple(found["missing"]), cheaper)
        empty = {"missing": found["missing"], "cheaper": cheaper, "agents": 0, "budget_chf": 0.0}
        group = groups.setdefault(key, empty)
        group["agents"] += 1
        if req["ask"]["max_price_chf"]:
            nights = hive.stay_nights(req["ask"]["check_in"], req["ask"]["check_out"])
            group["budget_chf"] += req["ask"]["max_price_chf"] * nights
    with db.cursor() as cur:
        offered = cur.execute("SELECT count(*) FROM hive_offers WHERE card_id = ?", [card["id"]]).fetchone()[0]
    asks = sorted(groups.values(), key=lambda g: (-g["agents"], g["cheaper"], g["missing"]))[:10]
    return {
        "agents": sum(g["agents"] for g in groups.values()),
        "budget_chf": round(sum(g["budget_chf"] for g in groups.values())),
        "asks": [{**g, "budget_chf": round(g["budget_chf"])} for g in asks],
        "offers_sent": offered,
    }
