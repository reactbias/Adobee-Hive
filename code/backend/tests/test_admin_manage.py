"""Running a hub, not only reading it: what it carries, one entity in detail, and taking one out.

The complaint this answers was an operator's: "I cannot edit the connected hubs, nor can I kick out
users, I cannot see their details." Every test here is one of those three sentences.
"""

from __future__ import annotations

import pytest

from app import blocklist, config, db, hive, removals

TOKEN = "s3cret-for-tests"
ADMIN = {"X-Admin-Token": TOKEN}


@pytest.fixture
def admin(monkeypatch):
    """A hub with an admin token configured, so a write can be tried with it and without it."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")


@pytest.fixture(autouse=True)
def nothing_withdrawn(client):
    """Every test starts with a hub that carries everything, and leaves one behind it."""
    removals.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_removals")
        cur.execute("DELETE FROM hub_admin_log")
    yield
    with db.write() as cur:
        cur.execute("DELETE FROM hub_removals")
        cur.execute("DELETE FROM hub_admin_log")


def _an_entity(client) -> dict:
    return client.get("/api/admin/entities", headers=ADMIN).json()["entities"][0]


# ---------------------------------------------------------------- the list


def test_the_entity_list_says_what_this_hub_carries(client, admin):
    """An operator could see a count and nothing else. This is the list behind the count."""
    out = client.get("/api/admin/entities", headers=ADMIN).json()

    assert out["count"] == len(out["entities"]) > 0
    for row in out["entities"]:
        assert {"id", "name", "kind", "claimed", "rating", "rating_count", "published_at"} <= set(row)
        assert row["name"], "a row an operator cannot read is not a row"
        assert isinstance(row["claimed"], bool), "claimed or unclaimed, never unstated"
        assert row["rating_count"] >= 0


def test_the_entity_list_counts_what_the_overview_counts(client, admin):
    """One number in two places has to come from one list, or the panel contradicts itself."""
    counted = client.get("/api/admin/overview").json()["index"]["entities"]
    assert client.get("/api/admin/entities", headers=ADMIN).json()["count"] == counted


def test_an_unrated_entity_reports_no_rating_rather_than_zero(client, admin):
    """No stay, no rating. Zero would read as a bad business instead of a new one."""
    rows = client.get("/api/admin/entities", headers=ADMIN).json()["entities"]
    unrated = [r for r in rows if r["rating_count"] == 0]
    assert unrated, "the seed has entities nobody has reviewed"
    assert all(r["rating"] is None for r in unrated)


# ---------------------------------------------------------------- the detail


def test_the_detail_view_shows_the_card_its_contact_flags_and_its_signature(client, admin):
    """The operator's third sentence: "I cannot see their details"."""
    entity_id = _an_entity(client)["id"]
    out = client.get(f"/api/admin/entities/{entity_id}", headers=ADMIN).json()

    assert out["entity"]["id"] == entity_id
    assert out["card"]["id"] == entity_id, "the full card, not a summary of it"
    assert isinstance(out["offers"], list) and isinstance(out["needs"], list)
    assert "contact" in out and "contact_sharing" in out
    assert out["trust"]["algorithm"].startswith("Ed25519")
    assert out["signature"]["valid"] is True
    assert out["signature"]["public_key"], "an operator checking a signature needs the key it was checked against"
    assert out["blocked"] is False


def test_the_detail_view_of_an_unknown_entity_is_a_bad_request_not_a_crash(client, admin):
    res = client.get("/api/admin/entities/nothing-here", headers=ADMIN)
    assert res.status_code == 400 and "nothing-here" in res.json()["detail"]


def test_the_detail_view_says_whether_the_entity_is_blocked(client, admin):
    """Removing and blocking are different acts; the view an operator decides from has to say which."""
    entity_id = _an_entity(client)["id"]
    client.post(
        "/api/admin/blocklist",
        json={"kind": "entity", "subject": entity_id, "reason": "fabricated reviews"},
        headers=ADMIN,
    )
    try:
        out = client.get(f"/api/admin/entities/{entity_id}", headers=ADMIN).json()
        assert out["blocked"] is True
        assert out["block"]["reason"] == "fabricated reviews"
    finally:
        client.delete(f"/api/admin/blocklist/entity/{entity_id}", headers=ADMIN)


# ---------------------------------------------------------------- removing one


def test_a_removed_entity_disappears_from_discovery(client, admin):
    """Not in the matches, and not in the excluded list either: being excluded still names it."""
    before = hive.discover(query="")["matches"]
    target = before[0]["id"]

    res = client.post(
        f"/api/admin/entities/{target}/remove", json={"reason": "asked to be taken off the hub"}, headers=ADMIN
    )
    assert res.status_code == 200 and res.json()["carried"] is False

    after = hive.discover(query="")
    assert all(m["id"] != target for m in after["matches"]), "a removed entity is still being found"
    assert all(m["id"] != target for m in after["excluded"]), "named as excluded is still named"
    assert target not in {c["id"] for c in hive.list_cards()}


def test_a_removed_entity_cannot_be_booked(client, admin):
    """Gone from search is half of it. An agent holding the id must not be able to book it either."""
    target = "hotel-rheinblick"
    client.post(f"/api/admin/entities/{target}/remove", json={"reason": "closed for the season"}, headers=ADMIN)

    res = client.post(
        f"/api/hive/cards/{target}/book",
        json={
            "unit_id": "double",
            "check_in": "2027-03-10",
            "check_out": "2027-03-12",
            "guest_name": "Mara Keller",
            "guests": 2,
        },
    )
    assert res.status_code == 400 and "no longer carries" in res.json()["detail"]
    assert (
        client.get(
            f"/api/hive/cards/{target}/availability",
            params={"check_in": "2027-03-10", "check_out": "2027-03-12"},
        ).status_code
        == 400
    )


def test_the_signed_history_of_a_removed_entity_survives(client, admin):
    """The whole argument for a withdrawal: a receipt must still prove what the card said."""
    target = "hotel-rheinblick"
    booking = hive.book(target, "single", "2027-04-01", "2027-04-03", "Mara Keller", 1)

    client.post(f"/api/admin/entities/{target}/remove", json={"reason": "a front for something else"}, headers=ADMIN)

    promised = hive.what_was_promised(booking["receipt"])
    assert promised["card"]["id"] == target
    assert promised["card"]["version"] == booking["card_version"]
    assert promised["digest_matches"] is True, "the signed version a guest booked against is still provable"
    assert hive.get_card(target)["trust"]["signature_valid"] is True


def test_a_removal_without_a_reason_is_refused(client, admin):
    """Exactly as the blocklist refuses one: this list has to be readable in six months."""
    target = "hotel-gare"
    res = client.post(f"/api/admin/entities/{target}/remove", json={"reason": "   "}, headers=ADMIN)

    assert res.status_code == 400 and "reason" in res.json()["detail"]
    assert not removals.is_withdrawn(target), "a refused removal leaves nothing behind"
    assert target in {c["id"] for c in hive.list_cards()}


def test_removing_an_entity_this_hub_never_carried_is_a_bad_request(client, admin):
    res = client.post("/api/admin/entities/nothing-here/remove", json={"reason": "typo"}, headers=ADMIN)
    assert res.status_code == 400


def test_removing_is_not_blocking(client, admin):
    """Two different acts. Removal says 'not ours to carry'; a block says 'refuse it anywhere'."""
    target = "hotel-dreirosen"
    client.post(f"/api/admin/entities/{target}/remove", json={"reason": "left the hub"}, headers=ADMIN)

    assert removals.is_withdrawn(target) is True
    assert blocklist.is_blocked(blocklist.ENTITY, target) is False
    out = client.get(f"/api/admin/entities/{target}", headers=ADMIN).json()
    assert out["carried"] is False and out["blocked"] is False
    assert out["removal"]["reason"] == "left the hub"


def test_a_removed_entity_is_still_visible_to_administration(client, admin):
    """An operator has to be able to see what they removed in order to put it back."""
    target = "hotel-gare"
    client.post(f"/api/admin/entities/{target}/remove", json={"reason": "duplicate card"}, headers=ADMIN)

    rows = {r["id"]: r for r in client.get("/api/admin/entities", headers=ADMIN).json()["entities"]}
    assert rows[target]["carried"] is False
    assert rows[target]["removal"]["reason"] == "duplicate card"
    assert client.get("/api/admin/overview").json()["index"]["entities"] == len(
        [r for r in rows.values() if r["carried"]]
    )


def test_an_entity_can_be_carried_again_and_both_decisions_stay_in_the_ledger(client, admin):
    target = "hotel-gare"
    client.post(f"/api/admin/entities/{target}/remove", json={"reason": "reported as a front"}, headers=ADMIN)
    res = client.post(f"/api/admin/entities/{target}/restore", json={"reason": "the report was wrong"}, headers=ADMIN)

    assert res.status_code == 200 and res.json()["carried"] is True
    assert target in {c["id"] for c in hive.list_cards()}
    actions = [row["action"] for row in client.get("/api/admin/audit", headers=ADMIN).json()["entries"]]
    assert "entity.remove" in actions and "entity.restore" in actions


def test_the_ledger_records_when_why_and_which_credential_not_a_name(client, admin):
    """One shared password, so "who" is thin. Record what can be recorded and say what cannot."""
    target = "hotel-gare"
    client.post(f"/api/admin/entities/{target}/remove", json={"reason": "fabricated attestations"}, headers=ADMIN)

    out = client.get("/api/admin/audit", headers=ADMIN).json()
    row = next(r for r in out["entries"] if r["subject"] == target)
    assert row["action"] == "entity.remove"
    assert row["reason"] == "fabricated attestations"
    assert row["at"], "a ledger row without a time proves nothing"
    assert row["actor"] == "admin", "the hub cannot tell two operators apart, and must not pretend to"
    assert row["credential"] in ("static token", "session")
    assert "password" in out["who_limit"] or "shared" in out["who_limit"]


# ---------------------------------------------------------------- the door


READS = ["/api/admin/entities", "/api/admin/entities/hotel-rheinblick", "/api/admin/audit"]
WRITES = [
    ("/api/admin/entities/hotel-rheinblick/remove", {"reason": "x"}),
    ("/api/admin/entities/hotel-rheinblick/restore", {"reason": "x"}),
]


@pytest.mark.parametrize("path", READS)
def test_every_new_read_refuses_without_the_admin_token(client, admin, path):
    assert client.get(path).status_code == 403
    assert client.get(path, headers={"X-Admin-Token": "wrong"}).status_code == 403


@pytest.mark.parametrize("path,body", WRITES)
def test_every_new_write_refuses_without_the_admin_token(client, admin, path, body):
    assert client.post(path, json=body).status_code == 403
    assert client.post(path, json=body, headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert not removals.is_withdrawn("hotel-rheinblick"), "a refused write changes nothing"


@pytest.mark.parametrize("path", READS)
def test_administration_fails_closed_when_this_hub_has_no_credential(client, monkeypatch, path):
    """Unset means shut, not open, exactly as the blocklist already behaves."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert client.get(path).status_code == 503


@pytest.mark.parametrize("path,body", WRITES)
def test_a_write_fails_closed_when_this_hub_has_no_credential(client, monkeypatch, path, body):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert client.post(path, json=body).status_code == 503


def test_the_entity_rows_carry_nothing_the_card_does_not_already_publish(client, admin):
    """An admin list is not a side channel: every field here is on the public card too."""
    row = _an_entity(client)
    card = hive.get_card(row["id"])
    assert row["name"] == card["name"] and row["kind"] == card["kind"]
