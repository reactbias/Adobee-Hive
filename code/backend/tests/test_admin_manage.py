"""Running a hub, not only reading it: what it carries, one entity in detail, and taking one out.

The complaint this answers was an operator's: "I cannot edit the connected hubs, nor can I kick out
users, I cannot see their details." Every test here is one of those three sentences.
"""

from __future__ import annotations

import pytest

from app import config, hive

TOKEN = "s3cret-for-tests"
ADMIN = {"X-Admin-Token": TOKEN}


@pytest.fixture
def admin(monkeypatch):
    """A hub with an admin token configured, so a write can be tried with it and without it."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")


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


# ---------------------------------------------------------------- the door


@pytest.mark.parametrize("path", ["/api/admin/entities", "/api/admin/entities/hotel-rheinblick"])
def test_every_new_endpoint_refuses_without_the_admin_token(client, admin, path):
    assert client.get(path).status_code == 403
    assert client.get(path, headers={"X-Admin-Token": "wrong"}).status_code == 403


@pytest.mark.parametrize("path", ["/api/admin/entities", "/api/admin/entities/hotel-rheinblick"])
def test_administration_fails_closed_when_this_hub_has_no_credential(client, monkeypatch, path):
    """Unset means shut, not open, exactly as the blocklist already behaves."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert client.get(path).status_code == 503


def test_the_entity_rows_carry_nothing_the_card_does_not_already_publish(client, admin):
    """An admin list is not a side channel: every field here is on the public card too."""
    row = _an_entity(client)
    card = hive.get_card(row["id"])
    assert row["name"] == card["name"] and row["kind"] == card["kind"]
