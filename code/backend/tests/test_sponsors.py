"""BaselHack 2026 challenge sponsors are in the Hive as unclaimed cards, and new seed cards reach a persisted Hive."""

import copy
from datetime import date

from app import hive, hive_seed
from app.domains import examples, explore

NOV = date(2026, 11, 2)


def test_pax_is_an_unclaimed_card_built_from_its_public_site(client):
    card = hive.get_card("x-pax")
    assert card["name"] == "Pax"
    assert card["trust"]["claimed"] is False
    assert card["provenance"]["url"] == "https://www.pax.ch"
    assert card["provenance"]["verified_by_owner"] is False


def test_a_pension_question_finds_pax(client):
    out = explore.ask("Who can help me with my pillar 3a?", today=NOV)
    assert "x-pax" in {r["card_id"] for r in out["replies"]}


def test_every_sponsored_challenge_has_a_card(client):
    ids = {c["id"] for c in hive.list_cards()}
    assert {"x-adobe", "x-endress", "x-pax", "x-baselhack"} <= ids


def test_a_new_seed_card_reaches_a_hive_that_already_has_data(client, monkeypatch):
    # A persisted Hive is not empty, so it never seeds again; a card added to the seed later must still arrive,
    # and the cards already there (owner edits included) must stay as they are.
    before = hive.get_card("hotel-rheinblick")["version"]
    extra = copy.deepcopy(examples.CARDS[0])
    extra.update(id="x-later", slug="later", name="Later Example")
    monkeypatch.setattr(examples, "CARDS", [*examples.CARDS, extra])
    hive_seed.seed_if_empty()
    assert hive.get_card("x-later")["name"] == "Later Example"
    assert hive.get_card("hotel-rheinblick")["version"] == before


def test_the_owner_view_lists_hand_offs_for_a_card_without_rooms(client):
    out = client.post("/api/ask", json={"question": "Book an advice meeting with Pax"}).json()
    pending = out["pending"]
    assert pending["business"] == "Pax"
    client.post("/api/ask/approve", json={"id": pending["id"]})
    handoffs = client.get("/api/owner/x-pax").json()["handoffs"]
    assert handoffs and handoffs[0]["item"] == pending["item"]
    assert set(handoffs[0]) == {"item", "created_at"}  # what was asked and when, never who
