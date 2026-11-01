"""An introduction to one of this hub's own members has to be able to teach it something (#164).

`calibration.py` measures one thing: what a hub *claimed* an entity was worth against what a person
found weeks later. The claim is frozen onto the connection row as `published_rating` at the moment
of introduction, and `connections.rated_via` drops any row that has none — a row with no claim is
not evidence, it is a blank.

For an entity on a peer that worked. For an entity *this* hub carries it could not, because
`hub.connect` read the stored card **body** and a body carries no `trust` block: a signature cannot
cover a number that changes every time somebody reviews the place, so the trust block is computed
per read. Both of `_published_rating`'s lookups therefore missed, every local introduction was
written with `published_rating NULL`, and the hub's own row in its own directory stayed `unproven`
for ever however much it was used. The hub standing on this disk was the only hub it could never
say anything about.

The fix is small and its risk is not. `hub.connect` now reads `hive.get_card`, so what
`_entity_default` and `sharing.resolve` receive on **every** local connect is a different dict than
before — and those two decide who may be connected to at all. So the second half of this file is
the regression that patch needs: the trust block must change no sharing decision, for any card this
hub carries, now or later.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app import admin, calibration, config, connections, db, folder_keys, folders, hive, hub, sharing
from app.domains import hr

#: A hotel with units to book, so a review can be earned the only way a review can be: with the
#: signed receipt of a stay that happened.
STAYS = "hotel-messe"
GUEST = "mara@example.com"


@pytest.fixture(autouse=True)
def clean_slate(client):
    """No connections, no folder links, and no reviews left behind for the next file to find.

    The suite shares one database, so a review earned here would otherwise show up as a rating on a
    corpus card in every test that runs after this one.
    """
    connections.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_connections")
        cur.execute("DELETE FROM folder_links")
        cur.execute("DELETE FROM folder_grants")
    folders.reset()
    yield
    with db.write() as cur:
        cur.execute("DELETE FROM hive_reviews WHERE card_id = ?", [STAYS])
        cur.execute("DELETE FROM hub_connections")


def _reviewed(stars: int, night: date) -> None:
    """Give `STAYS` one verified review, through a real booking and its signed receipt.

    The only way a rating gets onto a card at all: `hive.review` takes the signed receipt of a stay
    that happened, so this is the claim the hub goes on to publish rather than one a test wrote in.
    """
    unit = hive.get_card(STAYS)["units"][0]["id"]
    booking = hive.book(STAYS, unit, night.isoformat(), (night + timedelta(days=1)).isoformat(), "Test Guest")
    hive.review(booking["receipt"], stars, "as described")


def _connect(entity_id: str = STAYS, requester: str = GUEST, **kw) -> dict:
    return hub.connect(requester, entity_id, **kw)


def _secret(row: dict) -> str:
    """The requester's own credential for this introduction, which scoring takes (#107)."""
    return row["folder_key"]["secret"]


# ---------------------------------------------------------------- the claim is recorded


def test_a_local_introduction_freezes_what_this_hub_claimed_about_its_own_member(client):
    """The bug, in one assertion: this was `None` for every local introduction ever made."""
    _reviewed(4, date(2027, 6, 1))
    assert hive.get_card(STAYS)["trust"]["verified_reviews"]["average"] == 4.0

    row = _connect()

    assert row["published_rating"] == 40, "4.0 stars, in tenths, frozen at the introduction"
    assert row["published_rating_stars"] == 4.0


def test_a_local_introduction_names_this_hub_as_the_one_that_carried_it(client):
    """A claim belongs to whoever made it. A row attributed to nobody is counted by nobody."""
    _reviewed(4, date(2027, 6, 3))

    row = _connect()

    assert row["target_hub"] == config.HIVE_HUB_ID
    assert row["via_hub"] == config.HIVE_HUB_ID
    assert connections.get(row["id"])["target_hub"] == config.HIVE_HUB_ID


def test_an_unreviewed_local_entity_still_records_no_claim(client):
    """The fix must not invent a number. Nothing was claimed, so there is nothing to measure."""
    row = _connect()

    assert row["published_rating"] is None
    connections.rate(row["id"], 40)
    assert connections.rated_via(config.HIVE_HUB_ID) == [], "a row with no claim is a blank, not evidence"


def test_an_explicit_target_hub_is_never_overwritten(client):
    """The default fills a blank; it does not correct a caller who named a hub."""
    _reviewed(4, date(2027, 6, 5))
    row = _connect(target_hub=config.HIVE_HUB_ID, via_hub="somewhere-else")
    assert row["via_hub"] == "somewhere-else"


# ---------------------------------------------------------------- and reaches calibration


def test_scoring_a_local_introduction_reaches_calibration(client):
    """End to end: the claim, the real meeting, and the gap between them."""
    _reviewed(4, date(2027, 6, 7))
    row = _connect()

    out = hub.score(row["id"], 25, "not as described", secret=_secret(row))

    assert out["hub"] == config.HIVE_HUB_ID
    assert out["gap"] == 15, "claimed 4.0, found 2.5"
    assert out["gap_stars"] == 1.5
    assert "4.0" in out["says"] and "2.5" in out["says"]
    assert out["hub_standing"]["hub"] == config.HIVE_HUB_ID
    assert [r["id"] for r in connections.rated_via(config.HIVE_HUB_ID)] == [row["id"]]
    assert config.HIVE_HUB_ID in connections.hubs_with_ratings()


def test_this_hubs_own_directory_row_can_finally_carry_a_number(client):
    """`admin._standing_of`'s docstring says the home row is fillable. Now it is.

    Three scored introductions, which is `calibration.MIN_EVIDENCE`: below that the verdict stays
    `unproven` on purpose, because a mean over two meetings is noise wearing a number's clothes.
    """
    for n in range(calibration.MIN_EVIDENCE):
        _reviewed(4, date(2027, 7, n + 1))
        row = _connect()
        hub.score(row["id"], 30, secret=_secret(row))

    home = next(r for r in admin.directory()["hubs"] if r["home"])

    assert home["hub"] == config.HIVE_HUB_ID
    assert home["evidence"] == calibration.MIN_EVIDENCE
    assert home["error"] == 10.0, "claimed 4.0 each time, found 3.0 each time"
    assert home["verdict"] != "unproven"
    assert home["why"] != "no introductions through this hub yet", "the sentence that was simply false"


# ---------------------------------------------------------------- the regression the fix risks
#
# `hub.connect` hands `_entity_default` a dict with a trust block on it now. These pin that this
# changes nothing about who may be connected to — the one failure that would be worse than the bug.


def test_the_trust_block_changes_no_sharing_decision_for_any_card_this_hub_carries(client):
    """Over the whole index, so a card added later is covered without anybody remembering to.

    The body and the card are the same dict plus `trust`, and `_entity_default` reads `kind` and
    `sharing` out of it. This asserts that, rather than trusting it.
    """
    for card in hive.list_cards():
        body = hive.get_record(card["id"])["data"]
        full = hive.get_card(card["id"])
        assert hub._entity_default(body) == hub._entity_default(full), card["id"]
        assert sharing.resolve(hub._entity_default(body), None) == sharing.resolve(
            hub._entity_default(full), None
        ), card["id"]
        assert sharing.connectable(hub._entity_default(full), None) == sharing.connectable(
            hub._entity_default(body), None
        ), card["id"]


@pytest.mark.parametrize(
    ("card", "expected"),
    [
        ({"kind": "hotel"}, sharing.PUBLIC),
        ({"kind": "person"}, sharing.CONFIRM),
        ({"kind": "hotel", "sharing": sharing.CONFIRM}, sharing.CONFIRM),
        ({"kind": "hotel", "sharing": sharing.PUSH}, sharing.PUSH),
        ({"kind": "person", "sharing": sharing.PUBLIC}, sharing.PUBLIC),
    ],
)
def test_entity_default_reads_kind_and_sharing_and_a_trust_block_changes_nothing(card, expected):
    """No database: the rule itself, with and without the block the fix started passing in."""
    assert hub._entity_default(card) == expected
    assert hub._entity_default({**card, "trust": {"verified_reviews": {"average": 5.0, "count": 9}}}) == expected


def test_a_person_this_hub_carries_still_waits_for_their_own_yes(client):
    """The consent-first default, through the real local branch rather than through `_entity_default`."""
    hive.publish(dict(hr.EXAMPLE_CARD))

    row = _connect(hr.EXAMPLE_CARD["id"])

    assert row["state"] == connections.REQUESTED, "a person is asked, never assumed"
    assert row["sharing"] == sharing.CONFIRM
    # The requester is handed its own credential even here, and it opens nothing: the link is still
    # `requested`, so `folder_keys.resolve` refuses it until the owner says yes. What it is for is
    # proving which side of this introduction the holder is, later (#107).
    assert row["folder_key"]["secret"], "the requester's one chance to be given a credential"
    assert folder_keys.resolve(_secret(row)) is None, "and it reads nothing while the owner is silent"


def test_a_local_public_card_still_opens_at_once(client):
    row = _connect()
    assert row["state"] == connections.OPEN
    assert row["sharing"] == sharing.PUBLIC
    assert row["folder_key"]["secret"], "the requester's own side of the link, handed over once"


def test_a_local_entity_its_owner_only_pushes_is_still_refused(client):
    """`push` is the owner's to send and nobody's to request, trust block or no trust block."""
    hive.publish({**hr.EXAMPLE_CARD, "id": "person-pushonly", "slug": "pushonly", "sharing": sharing.PUSH})

    with pytest.raises(hub.HubError, match="their own initiative"):
        _connect("person-pushonly")

    assert connections.pending_confirmation("person-pushonly") == [], "and nothing was written"
