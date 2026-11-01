"""A signed receipt proves a booking, not a stay (#122), so a review may only claim the booking.

Nothing on the hub can tell that a guest arrived. These run through the doors a person and an agent use.
"""

import asyncio
from datetime import date, timedelta

import pytest
from mcp import Client

from app import db, hive
from app.mcp_server import server

HOTEL = "hotel-dreirosen"
ROOM = "dorm"
GUEST = "Review Guest"


@pytest.fixture(autouse=True)
def no_reviews_left_behind(client):
    """The database is shared across the session, and a review adds reputation to every later search in it."""
    yield
    with db.write() as cur:
        cur.execute(
            "DELETE FROM hive_reviews WHERE booking_id IN (SELECT id FROM hive_bookings WHERE guest_name = ?)", [GUEST]
        )


def _book(check_in: date, nights: int = 1) -> dict:
    check_out = check_in + timedelta(days=nights)
    return hive.book(HOTEL, ROOM, check_in.isoformat(), check_out.isoformat(), guest_name=GUEST)


def _post_review(client, receipt: str, rating: int = 5):
    return client.post("/api/hive/reviews", json={"receipt": receipt, "rating": rating, "text": "Quiet."})


def _review_count() -> int:
    return hive.get_card(HOTEL)["trust"]["verified_reviews"]["count"]


def test_a_review_of_a_booking_next_month_claims_the_booking_and_not_a_stay(client):
    booking = _book(date.today() + timedelta(days=30))

    answer = _post_review(client, booking["receipt"])

    assert answer.status_code == 200
    assert answer.json()["verified_booking"] is True
    assert answer.json()["verified_stay"] is False, "this guest has not arrived yet"


def test_a_check_out_date_in_the_past_does_not_make_a_completed_stay(client):
    """A date passing says nothing about whether anyone came, so it earns no more than a future booking does."""
    booking = _book(date(2020, 3, 1))

    answer = _post_review(client, booking["receipt"]).json()

    assert answer["verified_booking"] is True
    assert answer["verified_stay"] is False


def test_an_agent_is_told_the_same_as_a_person(client):
    booking = _book(date(2032, 1, 10))

    async def go():
        async with Client(server) as mcp:
            return await mcp.call_tool("hive_review", {"receipt": booking["receipt"], "rating": 4, "text": "Quiet."})

    answer = asyncio.run(go()).structured_content

    assert answer["verified_booking"] is True
    assert answer["verified_stay"] is False


def test_a_cancelled_booking_cannot_leave_a_review(client):
    booking = _book(date(2032, 2, 10))
    hive.cancel(booking["booking_id"], booking["receipt"])
    before = _review_count()

    answer = _post_review(client, booking["receipt"])

    assert answer.status_code == 400
    assert _review_count() == before


def test_a_receipt_leaves_one_review(client):
    booking = _book(date(2032, 3, 10))
    assert _post_review(client, booking["receipt"]).status_code == 200
    before = _review_count()

    again = _post_review(client, booking["receipt"], rating=1)

    assert again.status_code == 400
    assert _review_count() == before
