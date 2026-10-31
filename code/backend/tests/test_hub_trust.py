"""The hub's own machinery: what may be shared, who is blocked, who was introduced, and whose
ratings turned out to be honest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import blocklist, calibration, connections, db, sharing


@pytest.fixture(autouse=True)
def clean_slate(client):
    """Each test starts with an empty log and an empty blocklist; these tables are append-only."""
    blocklist.init()
    connections.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_connections")
        cur.execute("DELETE FROM hub_blocklist")
    yield


# ---------------------------------------------------------------- item-level sharing flags


def test_the_stricter_of_the_two_flags_always_wins():
    """Opening an account default must never unseal an item the person closed by hand."""
    assert sharing.resolve(sharing.PUBLIC, sharing.NEVER) == sharing.NEVER
    assert sharing.resolve(sharing.NEVER, sharing.PUBLIC) == sharing.NEVER
    assert sharing.resolve(sharing.PUBLIC, sharing.CONFIRM) == sharing.CONFIRM
    assert sharing.resolve(sharing.CONFIRM, sharing.PUBLIC) == sharing.CONFIRM


def test_an_item_that_says_nothing_is_not_public():
    assert sharing.resolve(None, None) == sharing.CONFIRM
    assert sharing.resolve(None, sharing.PUBLIC) == sharing.PUBLIC


def test_a_push_item_is_invisible_to_search_and_cannot_be_asked_for():
    """The point of push: it exists, the hub holds it, and only the owner can move it."""
    assert not sharing.searchable(None, sharing.PUSH)
    assert not sharing.connectable(None, sharing.PUSH)
    assert sharing.pushable(None, sharing.PUSH), "the owner can still send it to someone they chose"


def test_a_never_item_cannot_even_be_pushed():
    assert not sharing.searchable(None, sharing.NEVER)
    assert not sharing.connectable(None, sharing.NEVER)
    assert not sharing.pushable(None, sharing.NEVER)


def test_redact_hides_closed_items_and_marks_the_ones_that_need_a_yes():
    assert sharing.redact({"v": "x", "sharing": sharing.NEVER}, None) is None
    assert sharing.redact({"v": "x", "sharing": sharing.PUSH}, None) is None
    public = sharing.redact({"v": "x", "sharing": sharing.PUBLIC}, None)
    assert public == {"v": "x", "sharing": sharing.PUBLIC, "needs_confirmation": False}
    assert sharing.redact({"v": "x", "sharing": sharing.CONFIRM}, None)["needs_confirmation"] is True


def test_an_unknown_flag_is_refused_rather_than_guessed():
    with pytest.raises(sharing.SharingError):
        sharing.resolve(None, "sorta-public")


# ---------------------------------------------------------------- the blocklist


def test_a_block_needs_a_reason():
    """Someone has to be able to read this list in six months and tell spam from a legal order."""
    with pytest.raises(blocklist.BlockError):
        blocklist.block(blocklist.HUB, "spam.example", "")


def test_blocking_a_hub_then_lifting_it(client):
    blocklist.block(blocklist.HUB, "spam.example", "sends forged cards", added_by="ole")
    assert blocklist.is_blocked(blocklist.HUB, "spam.example")
    assert "spam.example" in blocklist.blocked_hubs()
    assert blocklist.entries(blocklist.HUB)[0]["reason"] == "sends forged cards"

    assert blocklist.unblock(blocklist.HUB, "spam.example") is True
    assert not blocklist.is_blocked(blocklist.HUB, "spam.example")
    assert blocklist.unblock(blocklist.HUB, "spam.example") is False, "lifting twice is not an error"


def test_blocking_a_hub_drops_anything_it_merely_relayed(client):
    """Blocking only the handing-over hub would be trivially routed around."""
    blocklist.block(blocklist.HUB, "spam.example", "forgery")

    assert blocklist.filter_path(["spam.example", "zurich", "basel"]) == "spam.example"
    assert blocklist.filter_path(["zurich", "spam.example", "basel"]) == "spam.example"
    assert blocklist.filter_path(["zurich", "basel"]) is None


def test_hubs_and_entities_are_blocked_separately(client):
    blocklist.block(blocklist.ENTITY, "hotel-dodgy", "fabricated reviews")
    assert blocklist.is_blocked(blocklist.ENTITY, "hotel-dodgy")
    assert not blocklist.is_blocked(blocklist.HUB, "hotel-dodgy"), "a kind is part of the identity"


# ---------------------------------------------------------------- the connection log


def _introduce(client, published=50, confirm=False) -> dict:
    row = connections.request(
        "mara@example.com",
        "hotel-limmat",
        requester_hub="basel",
        target_hub="zurich",
        via_hub="zurich",
        published_rating=published,
        needs_confirmation=confirm,
    )
    return connections.confirm(row["id"]) if confirm else row


def test_a_public_item_opens_at_once_and_a_confirm_item_waits(client):
    straight = connections.request("mara@example.com", "cafe-open", needs_confirmation=False)
    assert straight["state"] == connections.OPEN

    waiting = connections.request("mara@example.com", "lena", needs_confirmation=True)
    assert waiting["state"] == connections.REQUESTED
    assert connections.pending_confirmation("lena")[0]["id"] == waiting["id"]

    assert connections.confirm(waiting["id"])["state"] == connections.OPEN


def test_a_rating_is_given_once_and_only_on_an_open_connection(client):
    row = _introduce(client)
    rated = connections.rate(row["id"], 43, note="pleasant, slow breakfast")

    assert rated["state"] == connections.RATED
    assert rated["rating"] == 43 and rated["rating_stars"] == 4.3, "tenths of a star, shown as 4.3"

    with pytest.raises(connections.ConnectionError_, match="already been scored"):
        connections.rate(row["id"], 50)


def test_a_declined_introduction_can_never_become_a_rating(client):
    row = connections.request("mara@example.com", "lena", needs_confirmation=True)
    connections.decline(row["id"], "not taking new clients")

    with pytest.raises(connections.ConnectionError_):
        connections.rate(row["id"], 50)


def test_a_rating_outside_the_scale_is_refused(client):
    row = _introduce(client)
    for bad in (-1, 51, 4.3, True):
        with pytest.raises(connections.ConnectionError_):
            connections.rate(row["id"], bad)


def test_an_unscored_introduction_goes_stale_and_cannot_be_scored_afterwards(client):
    """The honest ending. Scoring a meeting a year later is score-settling, not evidence."""
    row = _introduce(client)
    long_past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=connections.STALE_AFTER_DAYS + 1)
    with db.write() as cur:
        cur.execute("UPDATE hub_connections SET stale_at = ? WHERE id = ?", [long_past, row["id"]])

    assert connections.expire_stale() == 1
    assert connections.get(row["id"])["state"] == connections.STALE

    with pytest.raises(connections.ConnectionError_, match="closed"):
        connections.rate(row["id"], 50)
    assert connections.awaiting_rating("mara@example.com") == [], "a stale row stops nagging the human"


# ---------------------------------------------------------------- hub calibration


def _scored(published: int, realised: int, days_ago: float = 0.0) -> dict:
    when = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago)).isoformat()
    return {"published_rating": published, "rating": realised, "rated_at": when}


def test_the_worked_example_a_hub_that_promised_five_stars_and_delivered_two_and_a_half():
    """Published 5.0, our user reports 2.5, so the hub is two and a half stars adrift. Worse."""
    rows = [_scored(50, 25) for _ in range(3)]
    s = calibration.score("hub2", rows)

    assert s["error"] == 25.0, "delta is published minus realised, in tenths of a star"
    assert s["error_stars"] == 2.5
    assert s["verdict"] == "over-promises"
    assert s["over_promised"] == 3 and s["under_promised"] == 0


def test_under_promising_earns_credit_and_a_better_score():
    """Lower is better and the sign carries meaning: a modest hub that over-delivers goes negative."""
    modest = calibration.score("modest", [_scored(25, 50) for _ in range(3)])
    honest = calibration.score("honest", [_scored(40, 40) for _ in range(3)])
    boastful = calibration.score("boastful", [_scored(50, 25) for _ in range(3)])

    assert modest["error"] == -25.0 and modest["verdict"] == "under-promises"
    assert honest["error"] == 0.0 and honest["verdict"] == "calibrated"
    assert modest["error"] < honest["error"] < boastful["error"], "lower is better, end to end"


def test_a_hub_is_unproven_until_enough_introductions_have_been_scored():
    """A mean over two meetings is noise wearing a number's clothes."""
    thin = calibration.score("new", [_scored(50, 10), _scored(50, 10)])

    assert thin["verdict"] == "unproven" and thin["error"] is None
    assert thin["evidence"] == 2
    assert calibration.trust("new", [_scored(50, 10)])["factor"] == calibration.UNPROVEN_TRUST


def test_old_evidence_fades():
    """A hub careless in spring and careful since should not be condemned for ever."""
    recent = calibration.score("h", [_scored(50, 25, days_ago=0) for _ in range(3)])
    ancient = calibration.score("h", [_scored(50, 25, days_ago=calibration.HALF_LIFE_DAYS * 6) for _ in range(3)])

    assert recent["error"] == ancient["error"], "the mean is unchanged; it is the confidence that decays"
    assert ancient["weight"] < recent["weight"] / 10, "six half-lives is worth almost nothing"


def test_a_mixed_history_averages_out_rather_than_being_decided_by_the_worst_day():
    s = calibration.score("mixed", [_scored(50, 25), _scored(40, 40), _scored(25, 50)])
    assert s["error"] == pytest.approx(0.0, abs=0.5), "one bad and one modest introduction cancel"
    assert s["over_promised"] == 1 and s["under_promised"] == 1 and s["exact"] == 1


def test_calibration_becomes_the_ranking_weight_only_for_over_promising():
    """Being modest is its own reward; it must not buy extra ranking weight above 1.0."""
    assert calibration.trust("h", [_scored(40, 40) for _ in range(3)])["factor"] == 1.0
    assert calibration.trust("h", [_scored(25, 50) for _ in range(3)])["factor"] == 1.0
    adrift = calibration.trust("h", [_scored(50, 25) for _ in range(3)])["factor"]
    assert adrift == 0.0, "two and a half stars of exaggeration is a hub whose word is worth nothing"
    assert 0.0 < calibration.trust("h", [_scored(50, 38) for _ in range(3)])["factor"] < 1.0


def test_the_under_rating_game_is_damped_by_one_constant(monkeypatch):
    """Signed credit invites a hub to under-rate its own members. The brake is one named number."""
    rows = [_scored(10, 40) for _ in range(3)]
    assert calibration.score("farmer", rows)["error"] == -30.0

    monkeypatch.setattr(calibration, "UNDER_PROMISE_WEIGHT", 0.0)
    assert calibration.score("farmer", rows)["error"] == 0.0, "credit can be switched off without touching the maths"


def test_hubs_rank_best_calibrated_first_with_the_unproven_last():
    ranked = calibration.ranked(["a", "b"])
    assert [r["hub"] for r in ranked] == ["a", "b"], "no evidence either way keeps a stable order"
    assert all(r["verdict"] == "unproven" for r in ranked)
