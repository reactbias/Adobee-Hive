"""Facts expire: a signed card says until when it holds, so a stale copy goes out of date on its own."""

from datetime import UTC, date, datetime, timedelta

from app import hive


def test_publish_signs_an_expiry_into_the_card(client):
    card = hive.get_card("hotel-rheinblick")
    until = datetime.fromisoformat(card["valid_until"])
    assert until - datetime.fromisoformat(card["published_at"]) == timedelta(days=hive.FRESH_DAYS)
    assert card["trust"]["fresh"] is True and card["trust"]["signature_valid"]


def test_an_expired_card_is_left_out_with_the_reason(client):
    card = hive.get_card("hotel-rheinblick")
    stale = {**card, "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")}
    found = hive.fit(
        stale, [], check_in=str(date.today() + timedelta(days=30)), check_out=str(date.today() + timedelta(days=31))
    )
    assert any(m.startswith("signed facts expired") for m in found["misses"])
    assert not hive.fit(card, [])["misses"]


def test_a_card_without_expiry_still_counts(client):
    legacy = {k: v for k, v in hive.get_card("hotel-gare").items() if k != "valid_until"}
    assert not hive.fit(legacy, [])["misses"]
