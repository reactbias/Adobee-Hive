"""The live activity feed: what the agents do behind the scenes, one line per step, for presenters and curious guests.

The feed reads the results the agents already return (a run, a hold, a hand-off, a scout pass) and keeps the steps,
never the conversation. A line names an agent, a step, a business and an outcome, all from fixed lists, so no
guest name, question or card text can reach it. The business is a card's public name.

`source` says where an answer came from: `partner` is a business's own signed card in the Hive (priority 1), `web`
is an unclaimed card compiled from the public web (hand-off only, never booked automatically). For the relevance
check it says who judged: `model` or `rules`.

Lines live in DuckDB (`hive_activity`), so they are part of the Postgres snapshot and survive a redeploy. The
newest MAX_EVENTS are kept.
"""

import logging
from collections.abc import Callable
from typing import Any

from . import db

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hive_activity (
    n INTEGER PRIMARY KEY,
    run VARCHAR,
    created_at TIMESTAMP,
    agent VARCHAR,
    step VARCHAR,
    business VARCHAR,
    outcome VARCHAR,
    source VARCHAR,
    hits INTEGER
);
"""
TABLE = "hive_activity"
COLUMNS = "n, run, created_at AS at, agent, step, business, outcome, source, hits AS count"
MAX_EVENTS = 300
MAX_NAME = 80
PAGE = 100

AGENTS = ("traveller", "verifier", "critic", "concierge", "scout", "hive")
STEPS = (
    "clarify",  # the request misses dates, a name, a route or a time: the agent asks first
    "discover",  # cards that fit, ranked
    "relevance",  # which cards genuinely cover the request
    "verify",  # a card's signature, or a web page that has to confirm the business
    "availability",  # free units for the dates
    "guard",  # text aimed at agents or a forged copy, withheld
    "hold",  # the action waits for the person's Approve
    "review",  # the verifier and the critic weigh the pick
    "confirm",  # the booking is sent and a signed receipt comes back
    "handoff",  # the person is sent on to the business's own site
    "scout",  # nothing in the Hive covers it: the public web is searched
)
OUTCOMES = (
    "asked",
    "matched",
    "none",
    "refused",
    "covered",
    "valid",
    "invalid",
    "unchecked",
    "free",
    "blocked",
    "held",
    "handoff_only",
    "agree",
    "object",
    "confirmed",
    "failed",
    "handed_off",
    "requested",
    "found",
    "unavailable",
    "added",
    "rejected",
)
SOURCES = ("partner", "web", "model", "rules")


def init() -> None:
    """Create the activity table if it doesn't exist."""
    with db.cursor() as cur:
        cur.execute(SCHEMA_SQL)


def event(
    agent: str,
    step: str,
    business: str | None = None,
    outcome: str = "",
    source: str | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    """One feed line, checked against the fixed lists; anything else is refused."""
    if agent not in AGENTS or step not in STEPS:
        raise ValueError(f"unknown agent or step: {agent} {step}")
    if outcome and outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome: {outcome}")
    if source is not None and source not in SOURCES:
        raise ValueError(f"unknown source: {source}")
    name = " ".join(str(business).split())[:MAX_NAME] if business else None
    return {
        "agent": agent,
        "step": step,
        "business": name,
        "outcome": outcome or None,
        "source": source,
        "count": int(count) if count is not None else None,
    }


def record(lines: list[dict[str, Any]]) -> None:
    """Store one run's lines in one write, under one run id, and drop the oldest past MAX_EVENTS."""
    if not lines:
        return
    run, at = db.new_id(), db.now()
    with db.write() as cur:
        first = cur.execute(f"SELECT coalesce(max(n), 0) + 1 FROM {TABLE}").fetchone()[0]
        cur.executemany(
            f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [first + i, run, at, e["agent"], e["step"], e["business"], e["outcome"], e["source"], e["count"]]
                for i, e in enumerate(lines)
            ],
        )
        cur.execute(f"DELETE FROM {TABLE} WHERE n <= ?", [first + len(lines) - 1 - MAX_EVENTS])


def recent(after: int = 0, limit: int = PAGE) -> dict[str, Any]:
    """Lines newer than `after`, oldest first; with after=0 the newest `limit`. `last` is the cursor for next time."""
    with db.cursor() as cur:
        if after:
            found = cur.execute(f"SELECT {COLUMNS} FROM {TABLE} WHERE n > ? ORDER BY n LIMIT ?", [after, limit])
        else:
            newest = f"SELECT {COLUMNS} FROM {TABLE} ORDER BY n DESC LIMIT ?"
            found = cur.execute(f"SELECT * FROM ({newest}) ORDER BY n", [limit])
        events = db.rows(found)
        last = cur.execute(f"SELECT coalesce(max(n), 0) FROM {TABLE}").fetchone()[0]
    for e in events:
        e["at"] = e["at"].isoformat() + "Z"
    return {"events": events, "last": last}


# ---------------------------------------------------------------- reading the agents' results


def _name_of(steps: list[dict[str, Any]], card_id: Any) -> str | None:
    for s in steps:
        out = s.get("output") or {}
        if out.get("card_id", out.get("id")) == card_id and out.get("name"):
            return out["name"]
        for m in out.get("matches", []):
            if m.get("id") == card_id:
                return m.get("name")
    return None


def from_agent_run(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The traveller agent's run: discover, check the signature and the dates, hold, and two agents weigh it."""
    if result.get("needs"):
        return [event("traveller", "clarify", outcome="asked", count=len(result["needs"]))]
    lines = []
    steps = result.get("steps") or []
    for s in steps:
        out = s.get("output") or {}
        if s.get("tool") == "hive_discover":
            matches = out.get("matches") or []
            outcome = "matched" if matches else "refused" if out.get("errors") else "none"
            top = matches[0].get("name") if matches else None
            lines.append(event("traveller", "discover", top, outcome, "partner", len(matches)))
        elif s.get("tool") == "hive_get_card":
            lines.append(event("traveller", "verify", out.get("name"), s.get("signature", "unchecked"), "partner"))
        elif s.get("tool") == "hive_check_availability":
            units = out.get("available_units") or []
            outcome = "free" if units else "none"
            lines.append(event("traveller", "availability", out.get("name"), outcome, None, len(units)))
    for g in result.get("guard") or []:
        lines.append(event("traveller", "guard", g.get("business"), "blocked", None, len(g.get("codes") or [])))
    pending = result.get("pending")
    if pending:
        business = _name_of(steps, (pending.get("input") or {}).get("card_id"))
        lines.append(event("traveller", "hold", business, "held", "partner"))
        for agent, key in (("verifier", "second_opinion"), ("critic", "critic")):
            verdict = (result.get(key) or {}).get("verdict")
            if verdict:
                lines.append(event(agent, "review", business, "agree" if verdict == "agree" else "object"))
    return lines


def from_approve(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The person's Approve: the held booking is sent, a signed receipt comes back, or it failed."""
    booking = result.get("booking")
    if booking:
        return [event("traveller", "confirm", booking.get("business"), "confirmed", "partner")]
    return [event("traveller", "confirm", None, "failed", "partner")]


def from_ask(result: dict[str, Any], agent: str = "concierge") -> list[dict[str, Any]]:
    """A question about any business: which cards cover it, what they answer, and a hold that can only hand off."""
    if result.get("clarify"):
        return [event(agent, "clarify", outcome="asked", count=len(result["clarify"]))]
    replies = result.get("replies") or []
    by = "model" if (result.get("relevance") or {}).get("by") == "model" else "rules"
    lines = [event(agent, "relevance", None, "covered" if replies else "none", by, len(replies))]
    for r in replies:
        source = "partner" if r.get("claimed") else "web"
        lines.append(event(agent, "discover", r.get("name"), "matched", source, len(r.get("items") or [])))
    pending = result.get("pending")
    if pending:
        claimed = pending.get("claimed")
        outcome = "held" if claimed else "handoff_only"
        lines.append(event(agent, "hold", pending.get("business"), outcome, "partner" if claimed else "web"))
    return lines


def from_ask_approve(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The person's yes on a held action: it goes to the business's own site, nothing is booked here."""
    status = result.get("status")
    outcome = status if status in ("handed_off", "requested") else "failed"
    source = "web" if status == "handed_off" else "partner"
    return [event("concierge", "handoff", result.get("business"), outcome, source)]


def from_scout(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The scout's pass: search the web, verify each business on its own site, add the ones that hold up."""
    added, rejected = result.get("added") or [], result.get("rejected") or []
    status = result.get("status")
    outcome = "unavailable" if status == "unavailable" else "found" if added or rejected else "none"
    lines = [event("scout", "scout", None, outcome, "web", len(added) + len(rejected))]
    lines += [event("scout", "verify", a.get("name"), "added", "web") for a in added]
    lines += [event("scout", "verify", r.get("name"), "rejected", "web") for r in rejected]
    if result.get("result"):
        lines += from_ask(result["result"], agent="scout")
    return lines


def track(read: Callable[[dict[str, Any]], list[dict[str, Any]]], result: dict[str, Any]) -> dict[str, Any]:
    """Record what `read` finds in `result` and return the result unchanged; the feed never breaks a request."""
    try:
        record(read(result))
    except Exception:  # the feed is a window, not part of the transaction
        log.exception("activity feed write failed")
    return result
