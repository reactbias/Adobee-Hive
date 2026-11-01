"""A yes is a yes to the terms the traveller saw (#104): a changed price or policy never books on an old approval."""

import asyncio

import pytest

from app import agent, db, hive, owner

HOTEL = "hotel-terms-fixture"
ROOM = "std"
FREE = "Free until 48 h before arrival"
STRICT = "No cancellation refund"
STAY = {"check_in": "2031-07-01", "check_out": "2031-07-03"}


def _card() -> dict:
    return {
        "id": HOTEL,
        "slug": HOTEL,
        "kind": "hotel",
        "name": "Hotel Bedingung (fictional)",
        "tagline": "Fictional, invented for this test",
        "description": "Quiet rooms.",
        "features": ["quiet"],
        "units": [{"id": ROOM, "name": "Standard", "max_guests": 2, "price_chf": 100.0, "quantity": 4}],
        "policies": {"cancellation": FREE, "payment": "Pay at the property"},
    }


@pytest.fixture(autouse=True)
def hotel(client):
    """A hotel of this file's own, gone afterwards: other files rank and count the hotels in the shared database."""
    hive.publish(_card())
    yield
    with db.write() as cur:
        for table, column in (
            ("hive_bookings", "card_id"),
            ("hive_events", "card_id"),
            ("hive_card_history", "card_id"),
            ("hive_keys", "card_id"),
            ("hive_cards", "id"),
        ):
            cur.execute(f"DELETE FROM {table} WHERE {column} = ?", [HOTEL])


def _edit(price: float | None = None, cancellation: str | None = None, description: str | None = None) -> None:
    """The owner changes the card, the only way an owner can."""
    card = {k: v for k, v in hive.get_card(HOTEL).items() if k != "trust"}
    if price is not None:
        card["units"] = [{**card["units"][0], "price_chf": price}]
    if cancellation is not None:
        card["policies"] = {**card["policies"], "cancellation": cancellation}
    if description is not None:
        card["description"] = description
    owner.apply(HOTEL, card)


def _propose(hotel_id: str = HOTEL, unit_id: str = ROOM, stay: dict = STAY) -> tuple[dict | None, dict]:
    """What a model agent's hive_book call becomes: the planner path, over the real in-process MCP server."""

    async def go():
        async with agent.HiveConnections() as hives:
            args = {"card_id": hotel_id, "unit_id": unit_id, "guest_name": "Terms Guest", "guests": 1} | stay
            return await agent._call_tool("hive_book", args, hives, [])

    return asyncio.run(go())


def _approve(client, pending: dict) -> dict:
    return client.post("/api/agent/approve", json={"pending": pending}).json()


def _bookings() -> int:
    with db.cursor() as cur:
        return cur.execute("SELECT count(*) FROM hive_bookings WHERE card_id = ?", [HOTEL]).fetchone()[0]


# ---------------------------------------------------------------- what the proposal carries


def test_a_proposal_carries_the_terms_the_traveller_is_shown(client):
    pending, output = _propose()

    assert output == agent.HELD
    assert pending["quote"]["total_chf"] == 200.0
    assert pending["quote"]["policies"]["cancellation"] == FREE


def test_the_scripted_planner_holds_its_proposal_with_terms_too(client):
    ask = (
        "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, "
        "2031-08-13 to 2031-08-15, my name is Mara Keller"
    )
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": ask}]}).json()
    shown = next(s for s in out["steps"] if s["tool"] == "hive_check_availability")["output"]
    unit = next(u for u in shown["available_units"] if u["id"] == out["pending"]["input"]["unit_id"])

    assert out["pending"]["quote"]["total_chf"] == unit["total_chf"]
    assert out["pending"]["quote"]["policies"] == shown["policies"]
    assert _approve(client, out["pending"])["booking"]["total_chf"] == unit["total_chf"]


def test_a_room_that_is_not_free_is_not_held_and_not_booked(client):
    """The agent asks before it holds, and a refusal must not fall through to the real hive_book."""
    pending, output = _propose(unit_id="no-such-room")

    assert pending is None
    assert "error" in output
    assert _bookings() == 0


def test_a_hold_with_no_terms_cannot_be_approved(client):
    """Nothing the traveller was shown means nothing they can have agreed to, so this fails closed."""
    pending = agent._hold({"card_id": HOTEL, "unit_id": ROOM, "guest_name": "Terms Guest", "guests": 1} | STAY)

    done = _approve(client, pending)

    assert done["booking"] is None
    assert _bookings() == 0


# ---------------------------------------------------------------- a change between proposal and approval


@pytest.mark.parametrize(
    "change",
    [{"price": 900.0}, {"cancellation": STRICT}, {"price": 50.0}],
    ids=["a higher price", "a stricter cancellation policy", "a lower price"],
)
def test_changed_terms_book_nothing_and_ask_again(client, change):
    pending, _ = _propose()
    _edit(**change)

    done = _approve(client, pending)

    assert done["booking"] is None
    assert _bookings() == 0, "the old yes must not reach a booking"
    assert done["pending"]["id"] != pending["id"], "a new yes needs a new hold"
    assert done["terms_changed"]["approved"]["total_chf"] == 200.0
    assert done["terms_changed"]["current"] == done["pending"]["quote"]
    assert any(s["tool"] == "hive_book" for s in done["steps"]), "the server refused it; the agent did not guess"


def test_the_new_terms_book_only_on_a_new_yes(client):
    pending, _ = _propose()
    _edit(price=900.0, cancellation=STRICT)

    asked_again = _approve(client, pending)
    assert asked_again["pending"]["quote"]["total_chf"] == 1800.0
    assert asked_again["pending"]["quote"]["policies"]["cancellation"] == STRICT

    booked = _approve(client, asked_again["pending"])["booking"]
    assert booked["total_chf"] == 1800.0
    assert booked["cancellation"] == STRICT


def test_the_old_approval_is_spent_when_the_terms_changed(client):
    pending, _ = _propose()
    _edit(price=900.0)
    _approve(client, pending)

    again = client.post("/api/agent/approve", json={"pending": pending})

    assert again.status_code == 400 and "already approved" in again.json()["detail"]
    assert _bookings() == 0


def test_terms_the_client_sends_back_count_for_nothing(client):
    """The quote is the server's. A client that rewrites it cannot talk a changed price through."""
    pending, _ = _propose()
    _edit(price=900.0)
    forged = pending | {"quote": {"total_chf": 1800.0, "policies": {"cancellation": FREE}, "terms": "forged"}}

    assert _approve(client, forged)["booking"] is None
    assert _bookings() == 0


def test_a_harmless_edit_still_books(client):
    """Telling material from harmless is the point: a new description is not a new deal."""
    pending, _ = _propose()
    _edit(description="Quiet rooms, and now a better photo.")

    booked = _approve(client, pending)["booking"]

    assert booked["status"] == "confirmed"
    assert booked["total_chf"] == 200.0
    assert booked["cancellation"] == FREE
    assert booked["card_version"] == 2


# ---------------------------------------------------------------- what the receipt says


def test_the_receipt_keeps_the_approved_terms_after_a_later_change(client):
    pending, _ = _propose()
    booked = _approve(client, pending)["booking"]
    _edit(price=900.0, cancellation=STRICT)

    promised = hive.what_was_promised(booked["receipt"])

    assert promised["card"]["units"][0]["price_chf"] == 100.0
    assert promised["card"]["policies"]["cancellation"] == FREE
    assert hive.read_statement(booked["receipt"])["total_chf"] == 200.0


# ---------------------------------------------------------------- the check itself, at the booking


def test_the_booking_refuses_terms_older_than_the_card(client):
    """The check is where the insert is, so a change in the last moment cannot slip past a check made earlier."""
    terms = hive.check_availability(HOTEL, **STAY)["available_units"][0]["terms"]
    _edit(cancellation=STRICT)

    with pytest.raises(hive.HiveError, match="terms"):
        hive.book(HOTEL, ROOM, guest_name="Terms Guest", expected_terms=terms, **STAY)

    assert _bookings() == 0


def test_terms_cover_the_price_and_policies_and_nothing_else(client):
    def terms() -> str:
        return hive.check_availability(HOTEL, **STAY)["available_units"][0]["terms"]

    first = terms()
    _edit(description="A new description.")
    assert terms() == first
    _edit(price=101.0)
    assert terms() != first


def test_a_booking_that_names_no_terms_still_works(client):
    """Existing clients of hive_book and the card page's booking keep working: the new argument is optional."""
    assert hive.book(HOTEL, ROOM, guest_name="Terms Guest", **STAY)["status"] == "confirmed"


# ---------------------------------------------------------------- a source that does not check


def _source(monkeypatch, cancelled: bool) -> list[str]:
    """A source on older software: it ignores expected_terms, and books at whatever its card says today."""
    calls: list[str] = []

    async def ask(source, pin, name, args, steps):
        calls.append(name)
        if name == "hive_book":
            return {
                "status": "confirmed",
                "booking_id": "bk_other",
                "receipt": "signed",
                "business": "Hotel Bedingung (fictional)",
                "unit_name": "Standard",
                "total_chf": 1800.0,
                "cancellation": FREE,
                "payment": "Pay at the property",
            }
        if name == "hive_cancel":
            return {"status": "cancelled"} if cancelled else {"error": "unreachable"}
        return {
            "available_units": [{"id": ROOM, "name": "Standard", "total_chf": 1800.0, "terms": "new"}],
            "policies": {"cancellation": FREE, "payment": "Pay at the property"},
        }

    monkeypatch.setattr(agent, "_ask_source", ask)
    return calls


def test_a_booking_on_other_terms_is_cancelled_and_asked_again(client, monkeypatch):
    pending, _ = _propose()
    calls = _source(monkeypatch, cancelled=True)

    done = _approve(client, pending)

    assert "hive_cancel" in calls
    assert done["booking"] is None
    assert done["pending"]["quote"]["total_chf"] == 1800.0


def test_a_booking_on_other_terms_that_cannot_be_cancelled_is_told_not_hidden(client, monkeypatch):
    """A real booking the traveller did not agree to: they need its receipt and its reference."""
    pending, _ = _propose()
    _source(monkeypatch, cancelled=False)

    done = _approve(client, pending)

    assert done["booking"]["booking_id"] == "bk_other"
    assert "bk_other" in done["reply"]
    assert "1800" in done["reply"]
    assert done.get("pending") is None
