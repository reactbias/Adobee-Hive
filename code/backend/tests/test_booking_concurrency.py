"""Callers racing for the last room: the availability check and the insert are one operation (#103).

The stays are in 2031 because the database is shared across the session, and no other test books that far ahead.
"""

import contextlib
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import pytest

from app import db, hive

HOTEL = "hotel-rheinblick"
ROOM = "river"
OTHER_ROOM = "double"
SOLD_OUT = "is not available"


def _book(unit_id: str, check_in: str, check_out: str, guest: str = "Racing Guest") -> dict:
    return hive.book(HOTEL, unit_id, check_in, check_out, guest_name=guest)


def _quantity(unit_id: str) -> int:
    return next(u["quantity"] for u in hive.get_card(HOTEL)["units"] if u["id"] == unit_id)


def _confirmed(unit_id: str, check_in: str) -> int:
    with db.cursor() as cur:
        return cur.execute(
            "SELECT count(*) FROM hive_bookings WHERE card_id = ? AND unit_id = ? AND check_in = ? "
            "AND status = 'confirmed'",
            [HOTEL, unit_id, check_in],
        ).fetchone()[0]


def _leave_one_room(unit_id: str, check_in: str, check_out: str) -> None:
    for n in range(_quantity(unit_id) - 1):
        _book(unit_id, check_in, check_out, guest=f"Earlier Guest {n}")


def _race(calls: list[Callable[[], Any]]) -> list[Any]:
    """Run every call at once, each from its own thread. A refused booking comes back as its `HiveError`."""
    lined_up = threading.Barrier(len(calls))

    def run(call: Callable[[], Any]) -> Any:
        lined_up.wait(timeout=10)
        try:
            return call()
        except hive.HiveError as err:
            return err

    with ThreadPoolExecutor(len(calls)) as pool:
        return list(pool.map(run, calls))


def _sold(results: list[Any]) -> list[dict]:
    return [r for r in results if isinstance(r, dict)]


def test_two_callers_who_both_saw_the_last_room_cannot_both_book_it(client, monkeypatch):
    """The race with the luck taken out: each caller finishes its check, then waits for its rival to finish too.

    With the check and the insert apart, both get through and both book, every run. With them held as one operation
    the rival cannot reach its check, so the wait simply runs out and it then finds the room taken. No timing can make
    the second case fail, because the wait only ever delays a caller.
    """
    check_in, check_out = "2031-03-01", "2031-03-03"
    _leave_one_room(ROOM, check_in, check_out)
    both_checked = threading.Barrier(2)
    real_check = hive._units_free

    def check_then_wait_for_the_rival(*args):
        free = real_check(*args)
        with contextlib.suppress(threading.BrokenBarrierError):
            both_checked.wait(timeout=0.5)
        return free

    monkeypatch.setattr(hive, "_units_free", check_then_wait_for_the_rival)
    results = _race([partial(_book, ROOM, check_in, check_out, guest=f"Rival {n}") for n in range(2)])

    assert len(_sold(results)) == 1
    refused = [r for r in results if isinstance(r, hive.HiveError)]
    assert len(refused) == 1 and SOLD_OUT in str(refused[0])
    assert _confirmed(ROOM, check_in) == _quantity(ROOM)


def test_eight_callers_through_the_rest_door_get_the_last_room_once(client):
    """The issue's own shape, with nothing patched: the REST route is synchronous, so it runs in a thread pool."""
    check_in, check_out = "2031-04-01", "2031-04-03"
    _leave_one_room(ROOM, check_in, check_out)
    body = {"unit_id": ROOM, "check_in": check_in, "check_out": check_out}

    def post(n: int):
        return client.post(f"/api/hive/cards/{HOTEL}/book", json={**body, "guest_name": f"Rest Guest {n}"})

    responses = _race([partial(post, n) for n in range(8)])

    assert [r.status_code for r in responses].count(200) == 1
    refused = [r for r in responses if r.status_code != 200]
    assert len(refused) == 7
    assert all(r.status_code == 400 and SOLD_OUT in r.json()["detail"] for r in refused)
    assert _confirmed(ROOM, check_in) == _quantity(ROOM)


def test_other_dates_and_other_rooms_keep_their_own_last_room(client):
    """Serialising the check must not make one sold-out room refuse anyone else. The two stays are back to back."""
    stay, next_stay = ("2031-05-01", "2031-05-03"), ("2031-05-03", "2031-05-05")
    wanted = [(ROOM, *stay), (ROOM, *next_stay), (OTHER_ROOM, *stay)]
    for unit_id, check_in, check_out in wanted:
        _leave_one_room(unit_id, check_in, check_out)

    results = _race([partial(_book, *want, guest=f"Guest {n}") for n in range(4) for want in wanted])

    assert len(_sold(results)) == len(wanted), "each of the three had exactly one room left"
    assert {(b["unit_id"], b["check_in"]) for b in _sold(results)} == {(u, i) for u, i, _ in wanted}
    assert all(_confirmed(unit_id, check_in) == _quantity(unit_id) for unit_id, check_in, _ in wanted)


def test_a_booking_that_fails_partway_leaves_no_record_and_no_lock(client, monkeypatch):
    check_in, check_out = "2031-06-01", "2031-06-03"
    _leave_one_room(ROOM, check_in, check_out)
    before = _confirmed(ROOM, check_in)

    def no_key(*args):
        raise RuntimeError("signing failed")

    with monkeypatch.context() as patch:
        patch.setattr(hive, "_sign_receipt", no_key)
        with pytest.raises(RuntimeError, match="signing failed"):
            _book(ROOM, check_in, check_out)
    assert _confirmed(ROOM, check_in) == before, "the failed attempt wrote nothing"

    # From another thread, because the lock is reentrant: this one would get back in even if it had never been let go.
    booked = []
    next_caller = threading.Thread(target=lambda: booked.append(_book(ROOM, check_in, check_out)), daemon=True)
    next_caller.start()
    next_caller.join(timeout=10)
    assert booked, "the failed attempt kept the lock, or took the room with it"
    assert _confirmed(ROOM, check_in) == _quantity(ROOM)
